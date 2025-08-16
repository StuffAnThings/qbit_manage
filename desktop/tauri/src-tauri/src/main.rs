#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use once_cell::sync::Lazy;
use std::{
  process::{Child},
  sync::{Arc, Mutex},
  time::Duration,
  io::{Read, Write},
  thread,
};
use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use tauri::{
  AppHandle,
  Manager,
  Listener,
  WindowEvent,
  Emitter,
  menu::{MenuBuilder, MenuItemBuilder},
  tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState},
  RunEvent,
};
use tauri_plugin_single_instance::init as single_instance;
use tokio::time::sleep;

static SERVER_STATE: Lazy<Arc<Mutex<Option<Child>>>> = Lazy::new(|| Arc::new(Mutex::new(None)));
static SHOULD_EXIT: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));

// PTY-based console state (always-run-in-PTY mode)
struct PtyState {
  child: Box<dyn portable_pty::Child + Send>,
  // Keep master alive for the lifetime of the session
  master: Box<dyn portable_pty::MasterPty + Send>,
  // Writer to send user input from the console window
  writer: Arc<Mutex<Box<dyn Write + Send>>>,
}
static PTY_STATE: Lazy<Arc<Mutex<Option<PtyState>>>> = Lazy::new(|| Arc::new(Mutex::new(None)));

#[derive(Debug, Clone)]
struct AppConfig {
  port: u16,
  base_url: Option<String>,
}

fn app_config(app: &AppHandle) -> AppConfig {
  // simple env-based configuration; could be read from a file later
  let port = std::env::var("QBT_PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(8080);
  let base_url = std::env::var("QBT_BASE_URL").ok().and_then(|v| {
    let s = v.trim().to_string();
    if s.is_empty() { None } else { Some(s) }
  });

  // log for debug
  let _ = app.emit("app-config", format!("port={port}, base_url={base_url:?}"));

  AppConfig { port, base_url }
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

fn stop_server() {
  // Prefer stopping PTY-managed process if running
  if let Some(mut state) = PTY_STATE.lock().unwrap().take() {
    // Attempt graceful termination of PTY child
    let _ = state.child.kill();

    // Drop writer/master to close streams, then wait a moment
    drop(state.writer);
    drop(state.master);

    // Nothing further to wait on; portable-pty Child.kill() requests termination.
    // Short sleep to allow OS cleanup.
    std::thread::sleep(Duration::from_millis(200));
    return;
  }

  // Fallback: legacy non-PTY child (shouldn't be used in "always PTY" mode)
  if let Some(mut child) = SERVER_STATE.lock().unwrap().take() {
    let pid = child.id();

    // Try graceful shutdown first
    #[cfg(unix)]
    {
      unsafe { libc::kill(pid as i32, libc::SIGTERM); }
      std::thread::sleep(Duration::from_millis(500));
      if child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
      }
    }

    #[cfg(windows)]
    {
      kill_process_tree_windows(pid);
      let _ = child.kill();
    }

    let _ = child.wait();
  }
}

#[cfg(windows)]
fn kill_process_tree_windows(pid: u32) {
  use std::mem::size_of;
  use std::process::Command;
  use windows::Win32::Foundation::CloseHandle;
  use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject, TerminateJobObject,
    JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
  };
  use windows::Win32::System::Threading::{
    OpenProcess, PROCESS_QUERY_INFORMATION, PROCESS_SET_INFORMATION, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
  };

  // Helper fallback using taskkill without /F (avoid force when possible)
  fn fallback_taskkill(pid: u32) {
    let _ = Command::new("taskkill")
      .args(&["/T", "/PID", &pid.to_string()])
      .output();
  }

  unsafe {
    // Create a Job Object and set "kill on close" so the entire tree terminates together.
    let job = CreateJobObjectW(None, None);
    if job.0 == 0 {
      fallback_taskkill(pid);
      return;
    }

    let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    // Ensure all associated processes are killed when the job is terminated/closed
    info.BasicLimitInformation.LimitFlags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

    if !SetInformationJobObject(
      job,
      JobObjectExtendedLimitInformation,
      &info as *const _ as *const _,
      size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
    )
    .as_bool()
    {
      let _ = CloseHandle(job);
      fallback_taskkill(pid);
      return;
    }

    // Open the target process and attach it to the job object. Its children will follow.
    let process = OpenProcess(
      PROCESS_TERMINATE | PROCESS_SET_QUOTA | PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION,
      false,
      pid,
    );
    if process.0 == 0 {
      let _ = CloseHandle(job);
      fallback_taskkill(pid);
      return;
    }

    if !AssignProcessToJobObject(job, process).as_bool() {
      let _ = CloseHandle(process);
      let _ = CloseHandle(job);
      fallback_taskkill(pid);
      return;
    }

    // Request termination of the entire job (process tree) without using the external taskkill tool.
    let _ = TerminateJobObject(job, 1);

    let _ = CloseHandle(process);
    let _ = CloseHandle(job);
  }
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

fn open_console_window(app: &AppHandle) {
  // Helper to attach input listener to a given window
  let attach_listener = |win: &tauri::WebviewWindow| {
    if let Some(state) = PTY_STATE.lock().unwrap().as_ref() {
      let writer_arc = Arc::clone(&state.writer);
      win.listen("console-input", move |event| {
        // Tauri v2 webview event payload is &str
        let data = event.payload();
        if let Ok(mut w) = writer_arc.lock() {
          let _ = w.write_all(data.as_bytes());
          let _ = w.flush();
        }
      });
    }
  };

  if let Some(win) = app.get_webview_window("console") {
    attach_listener(&win);
    let _ = win.show();
    let _ = win.set_focus();
    return;
  }

  use tauri::{WebviewUrl, WebviewWindowBuilder};
  if let Ok(win) = WebviewWindowBuilder::new(app, "console", WebviewUrl::App("terminal.html".into()))
    .title("qBit Manage - Console")
    .inner_size(900.0, 600.0)
    .min_inner_size(600.0, 400.0)
    .resizable(true)
    .visible(true)
    .build()
  {
    attach_listener(&win);
  }
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

// Always-run-in-PTY: start qbit-manage inside a pseudo terminal and stream I/O via events.
fn start_server(app: &AppHandle, cfg: &AppConfig) -> anyhow::Result<()> {
  // If already running, do nothing
  if PTY_STATE.lock().unwrap().is_some() {
    return Ok(());
  }

  let server_path = resolve_server_binary(app).unwrap_or_else(|| {
    if cfg!(target_os = "windows") {
      std::path::PathBuf::from("qbit-manage.exe")
    } else {
      std::path::PathBuf::from("qbit-manage")
    }
  });

  // Create PTY and spawn process inside it
  let pty_system = native_pty_system();
  let pair = pty_system
    .openpty(PtySize {
      rows: 30,
      cols: 120,
      pixel_width: 0,
      pixel_height: 0,
    })
    .map_err(|e| anyhow::anyhow!("openpty failed: {e}"))?;

  // Build command
  let mut cmd = CommandBuilder::new(server_path.to_string_lossy().to_string());
  // Env
  cmd.env("QBT_WEB_SERVER", "true");
  cmd.env("QBT_PORT", cfg.port.to_string());
  cmd.env("QBT_DESKTOP_APP", "true");
  if let Some(base) = &cfg.base_url {
    cmd.env("QBT_BASE_URL", base);
  }

  // Spawn
  let child = pair
    .slave
    .spawn_command(cmd)
    .map_err(|e| anyhow::anyhow!("spawn_command failed: {e}"))?;

  // Keep master endpoints
  let mut reader = pair
    .master
    .try_clone_reader()
    .map_err(|e| anyhow::anyhow!("clone reader failed: {e}"))?;
  let writer = pair
    .master
    .take_writer()
    .map_err(|e| anyhow::anyhow!("take writer failed: {e}"))?;

  let writer = Arc::new(Mutex::new(writer));
  {
    // Stream PTY output to the console window only
    let app_handle = app.clone();
    thread::spawn(move || {
      let mut buf = [0u8; 4096];
      loop {
        match reader.read(&mut buf) {
          Ok(0) => break, // EOF
          Ok(n) => {
            let chunk = String::from_utf8_lossy(&buf[..n]).to_string();
            let _ = app_handle.emit_to("console", "console-data", chunk);
          }
          Err(_) => break,
        }
      }
    });
  }

  // Console input listener is registered on the console window when it opens.

  // Save PTY state so we can stop later
  *PTY_STATE.lock().unwrap() = Some(PtyState {
    child,
    master: pair.master,
    writer,
  });

  Ok(())
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
      let console_item = MenuItemBuilder::with_id("console", "Open Console").build(app)?;
      let restart_item = MenuItemBuilder::with_id("restart", "Restart Server").build(app)?;
      let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
      let tray_menu = MenuBuilder::new(app)
        .items(&[&open_item, &console_item, &restart_item, &quit_item])
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
            "console" => {
              open_console_window(app);
            }
            "restart" => {
              // Stop server first, then start it again (in PTY)
              stop_server();
              let cfg = app_config(app);
              if start_server(app, &cfg).is_ok() {
                tauri::async_runtime::spawn(async move {
                  let _ = wait_until_ready(cfg.port, &cfg.base_url, Duration::from_secs(15)).await;
                });
              }
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

      // Start server automatically (in PTY) and redirect when ready
      let cfg = app_config(&app_handle);
      let app_handle3 = app_handle.clone();
      tauri::async_runtime::spawn(async move {
        let _ = start_server(&app_handle3, &cfg);
        if wait_until_ready(cfg.port, &cfg.base_url, Duration::from_secs(20)).await {
          redirect_to_server(&app_handle3, &cfg);
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
