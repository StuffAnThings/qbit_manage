#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use once_cell::sync::Lazy;
use std::{
  process::{Child, Command, Stdio},
  sync::{Arc, Mutex},
  time::Duration,
  io::{BufRead, BufReader},
  thread,
};
use tauri::{
  AppHandle,
  Manager,
  WindowEvent,
  Emitter,
  menu::{MenuBuilder, MenuItemBuilder},
  tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState},
  RunEvent,
};
use tauri_plugin_single_instance::init as single_instance;
use tauri_plugin_opener::OpenerExt;
use tokio::time::sleep;

static SERVER_STATE: Lazy<Arc<Mutex<Option<Child>>>> = Lazy::new(|| Arc::new(Mutex::new(None)));
static SHOULD_EXIT: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));

#[derive(Debug, Clone)]
struct AppConfig {
  port: u16,
  base_url: Option<String>,
  no_browser: bool,
}

fn app_config(app: &AppHandle) -> AppConfig {
  // simple env-based configuration; could be read from a file later
  let port = std::env::var("QBT_PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(8080);
  let base_url = std::env::var("QBT_BASE_URL").ok().and_then(|v| {
    let s = v.trim().to_string();
    if s.is_empty() { None } else { Some(s) }
  });
  let no_browser = std::env::var("QBT_NO_BROWSER")
    .map(|v| v.eq_ignore_ascii_case("true"))
    .unwrap_or(false);

  // log for debug
  let _ = app.emit("app-config", format!("port={port}, base_url={base_url:?}, no_browser={no_browser}"));

  AppConfig { port, base_url, no_browser }
}

fn resolve_server_binary(app: &AppHandle) -> Option<std::path::PathBuf> {
  // Priority:
  // 1) QBM_SERVER_PATH env override
  if let Ok(p) = std::env::var("QBM_SERVER_PATH") {
    let candidate = std::path::PathBuf::from(p);
    if candidate.exists() {
      return Some(candidate);
    }
  }

  // 2) resources/bin/{platform}/qbit-manage*
  // 3) resources/ (same dir) qbit-manage*
  // 4) current executable dir siblings
  let bin_names = if cfg!(target_os = "windows") {
    vec!["qbit-manage.exe", "qbit-manage-windows-amd64.exe"]
  } else {
    vec![
      "qbit-manage",
      "qbit-manage-linux-amd64",
      "qbit-manage-macos-x86_64",
      "qbit-manage-macos-arm64"
    ]
  };

  // resource dir (Tauri 2 path resolver)
  if let Ok(resource_dir) = app.path().resource_dir() {
    for name in &bin_names {
      let p = resource_dir.join("bin").join(name);
      if p.exists() {
        return Some(p);
      }
    }
    for name in &bin_names {
      let p = resource_dir.join(name);
      if p.exists() {
        return Some(p);
      }
    }
  }

  // executable dir
  if let Ok(exe) = std::env::current_exe() {
    if let Some(mut exe_dir) = exe.parent().map(|p| p.to_path_buf()) {
      for name in &bin_names {
        let p = exe_dir.join(name);
        if p.exists() {
          return Some(p);
        }
      }
      // try ../Resources
      exe_dir = exe_dir.join("..");
      for name in &bin_names {
        let p = exe_dir.join(name);
        if p.exists() {
          return Some(p);
        }
      }
    }
  }

  None
}

fn start_server(app: &AppHandle, cfg: &AppConfig) -> tauri::Result<()> {
  let mut guard = SERVER_STATE.lock().unwrap();

  // if already running, do nothing
  if let Some(child) = guard.as_mut() {
    if child.try_wait().ok().flatten().is_none() {
      return Ok(());
    }
  }

  let server_path = resolve_server_binary(app).unwrap_or_else(|| {
    // fall back to expecting binary on PATH
    if cfg!(target_os = "windows") {
      std::path::PathBuf::from("qbit-manage.exe")
    } else {
      std::path::PathBuf::from("qbit-manage")
    }
  });

  // build command
  let mut cmd = Command::new(server_path);
  cmd.env("QBT_WEB_SERVER", "true")
    .env("QBT_PORT", cfg.port.to_string())
    .env("QBT_DESKTOP_APP", "true")  // Indicate running in desktop app to prevent browser opening
    .stdin(Stdio::null())
    // Pipe stdout/stderr so we can forward logs to the app & (optionally) browser
    .stdout(Stdio::piped())
    .stderr(Stdio::piped());

  if let Some(base) = &cfg.base_url {
    cmd.env("QBT_BASE_URL", base);
  }

  // On Windows, make sure process does not open a console window
  #[cfg(target_os = "windows")]
  {
    use std::os::windows::process::CommandExt;
    cmd.creation_flags(0x08000000);
  }

  let mut child = cmd.spawn()?;

  // Log streaming (optional disable via QBT_DISABLE_LOG_STREAM=1)
  if std::env::var("QBT_DISABLE_LOG_STREAM").unwrap_or_default() != "1" {
    let app_handle_clone = app.clone();

    if let Some(stdout) = child.stdout.take() {
      thread::spawn({
        let app_handle = app_handle_clone.clone();
        move || {
          let reader = BufReader::new(stdout);
          for line in reader.lines().flatten() {
            let _ = app_handle.emit("server-log", &line);
          }
        }
      });
    }
    if let Some(stderr) = child.stderr.take() {
      thread::spawn({
        let app_handle = app_handle_clone.clone();
        move || {
          let reader = BufReader::new(stderr);
          for line in reader.lines().flatten() {
            let _ = app_handle.emit("server-error", &line);
          }
        }
      });
    }
  }

  *guard = Some(child);
  let _ = app.emit("server-status", "Server Running");
  Ok(())
}

fn stop_server() {
  if let Some(mut child) = SERVER_STATE.lock().unwrap().take() {
    let pid = child.id();

    // Try graceful shutdown first
    #[cfg(unix)]
    {
      // Send SIGTERM for graceful shutdown
      unsafe {
        libc::kill(pid as i32, libc::SIGTERM);
      }

      // Wait a bit for graceful shutdown
      std::thread::sleep(Duration::from_millis(500));

      // Check if process is still alive
      if child.try_wait().ok().flatten().is_none() {
        // Force kill if still running
        let _ = child.kill();
      }
    }

    #[cfg(windows)]
    {
      // On Windows, kill the entire process tree to ensure all child processes are terminated
      kill_process_tree_windows(pid);

      // Also kill the direct child process
      let _ = child.kill();
    }

    // Wait for process to fully terminate
    let _ = child.wait();
  }
}

#[cfg(windows)]
fn kill_process_tree_windows(pid: u32) {
  use std::process::Command;

  // Use taskkill to kill the process tree
  // /F = Force termination
  // /T = Terminate all child processes along with the parent process (process tree)
  // /PID = Process ID to terminate
  let _ = Command::new("taskkill")
    .args(&["/F", "/T", "/PID", &pid.to_string()])
    .output();

  // Also try to kill by process name as a backup
  let _ = Command::new("taskkill")
    .args(&["/F", "/IM", "qbit-manage-windows-amd64.exe"])
    .output();

  let _ = Command::new("taskkill")
    .args(&["/F", "/IM", "qbit-manage.exe"])
    .output();
}


fn cleanup_and_exit() {
  *SHOULD_EXIT.lock().unwrap() = true;
  stop_server();
  std::process::exit(0);
}

async fn wait_until_ready(port: u16, base_url: &Option<String>, timeout: Duration) -> bool {
  let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().ok();
  if client.is_none() {
    return false;
  }
  let client = client.unwrap();

  let url = match base_url {
    Some(b) if !b.trim().is_empty() => format!("http://127.0.0.1:{}/{}", port, b.trim().trim_start_matches('/')),
    _ => format!("http://127.0.0.1:{}", port),
  };

  let start = std::time::Instant::now();
  while start.elapsed() < timeout {
    if let Ok(resp) = client.get(&url).send().await {
      if resp.status().as_u16() < 500 {
        return true;
      }
    }
    sleep(Duration::from_millis(250)).await;
  }
  false
}

fn open_app_window(app: &AppHandle) {
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.show();
    let _ = win.set_focus();
  }
}

fn open_logs_window(app: &AppHandle) {
  // Check if logs window already exists
  if let Some(win) = app.get_webview_window("logs") {
    let _ = win.show();
    let _ = win.set_focus();
    return;
  }

  // Create new logs window
  use tauri::{WebviewUrl, WebviewWindowBuilder};
  let _logs_window = WebviewWindowBuilder::new(app, "logs", WebviewUrl::App("logs.html".into()))
    .title("qBit Manage - Server Logs")
    .inner_size(800.0, 600.0)
    .min_inner_size(600.0, 400.0)
    .resizable(true)
    .visible(true)
    .build();
}

fn redirect_to_server(app: &AppHandle, cfg: &AppConfig) {
  let url = match &cfg.base_url {
    Some(b) if !b.trim().is_empty() => format!("http://127.0.0.1:{}/{}", cfg.port, b.trim().trim_start_matches('/')),
    _ => format!("http://127.0.0.1:{}", cfg.port),
  };
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.eval(&format!("window.location.replace('{}')", url));
  }
}



pub fn run() {
  tauri::Builder::default()
    // Single instance should be first (per docs)
    .plugin(single_instance(|app, _argv, _cwd| {
      if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
      }
    }))
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_opener::init())
    .setup(|app| {
      let app_handle = app.handle().clone();

      // Build tray menu (v2 API)
      let open_item = MenuItemBuilder::with_id("open", "Open").build(app)?;
      let logs_item = MenuItemBuilder::with_id("logs", "Show Server Logs").build(app)?;
      let start_item = MenuItemBuilder::with_id("start", "Start Server").build(app)?;
      let stop_item = MenuItemBuilder::with_id("stop", "Stop Server").build(app)?;
      let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
      let tray_menu = MenuBuilder::new(app)
        .items(&[&open_item, &logs_item, &start_item, &stop_item, &quit_item])
        .build()?;

      // Create tray icon with explicit icon
      let _tray_icon = TrayIconBuilder::new()
        .menu(&tray_menu)
        .icon(app.default_window_icon().unwrap().clone())
        .on_tray_icon_event(|tray, event| {
          if let TrayIconEvent::Click {
            button: MouseButton::Left,
            button_state: MouseButtonState::Up,
            ..
          } = event {
            let app = tray.app_handle();
            if let Some(win) = app.get_webview_window("main") {
              let _ = win.show();
              let _ = win.set_focus();
            }
          }
        })
        .on_menu_event(move |app, event| {
          match event.id().as_ref() {
            "open" => {
              open_app_window(app);
            }
            "logs" => {
              open_logs_window(app);
            }
            "start" => {
              let cfg = app_config(app);
              if start_server(app, &cfg).is_ok() {
                tauri::async_runtime::spawn(async move {
                  let _ = wait_until_ready(cfg.port, &cfg.base_url, Duration::from_secs(15)).await;
                });
              }
            }
            "stop" => {
              stop_server();
            }
            "quit" => {
              cleanup_and_exit();
            }
            _ => {}
          }
        })
        .build(app)?;

      // Intercept window close to hide instead (minimize to tray)
      if let Some(win) = app.get_webview_window("main") {
        let app_handle2 = app_handle.clone();
        win.on_window_event(move |e| {
          if let WindowEvent::CloseRequested { api, .. } = e {
            api.prevent_close();
            if let Some(w) = app_handle2.get_webview_window("main") {
              let _ = w.hide();
            }
          }
        });
      }

      // Show the window immediately with loading page
      open_app_window(&app_handle);

      // Start server automatically and redirect when ready
      let cfg = app_config(&app_handle);
      let app_handle3 = app_handle.clone();
      tauri::async_runtime::spawn(async move {
        let _ = start_server(&app_handle3, &cfg);
        // Wait for server to be ready, then redirect
        if wait_until_ready(cfg.port, &cfg.base_url, Duration::from_secs(20)).await {
          redirect_to_server(&app_handle3, &cfg);
          if !cfg.no_browser {
            let url = match &cfg.base_url {
              Some(b) if !b.trim().is_empty() => format!("http://127.0.0.1:{}/{}", cfg.port, b.trim().trim_start_matches('/')),
              _ => format!("http://127.0.0.1:{}", cfg.port),
            };
            let _ = app_handle3.opener().open_url(url, None::<String>);
          }
        }
      });

      Ok(())
    })
    .build(tauri::generate_context!())
    .expect("error while building tauri application")
    .run(move |_app, event| {
      match event {
        RunEvent::ExitRequested { api, .. } => {
          // Always allow exit, but clean up first
          stop_server();
          api.prevent_exit();
          // Give a moment for cleanup, then force exit
          std::thread::spawn(|| {
            std::thread::sleep(Duration::from_millis(100));
            std::process::exit(0);
          });
        }
        RunEvent::Exit => {
          // Final cleanup on actual exit
          stop_server();
        }
        _ => {}
      }
    });
}

fn main() {
  run();
}
