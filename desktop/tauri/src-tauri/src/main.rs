#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use once_cell::sync::Lazy;
use std::{
  process::{Child, Command, Stdio},
  sync::{Arc, Mutex},
  time::Duration,
};
use tauri::{
  AppHandle,
  Manager,
  WindowEvent,
  Emitter,
  menu::{MenuBuilder, MenuItemBuilder, CheckMenuItemBuilder},
  tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState, TrayIcon},
  RunEvent,
};
use tauri_plugin_single_instance::init as single_instance;
use tokio::time::sleep;
#[cfg(target_os = "windows")]
use windows::Win32::System::Registry::*;

static SERVER_STATE: Lazy<Arc<Mutex<Option<ServerProcess>>>> = Lazy::new(|| Arc::new(Mutex::new(None)));
static SHOULD_EXIT: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));
static MINIMIZE_TO_TRAY: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));
static STARTUP_ENABLED: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));
static TRAY_HANDLE: Lazy<Arc<Mutex<Option<TrayIcon>>>> = Lazy::new(|| Arc::new(Mutex::new(None)));

struct ServerProcess {
  child: Child,
  #[cfg(all(windows, feature = "winjob"))]
  job: Option<windows::Win32::Foundation::HANDLE>,
}

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

fn load_minimize_setting(app: &AppHandle) -> bool {
  if let Ok(data_dir) = app.path().app_data_dir() {
    let file = data_dir.join("minimize_to_tray.txt");
    if file.exists() {
      std::fs::read_to_string(&file).map(|s| s.trim() == "true").unwrap_or(false)
    } else {
      false
    }
  } else {
    false
  }
}

fn save_minimize_setting(app: &AppHandle, value: bool) {
  if let Ok(data_dir) = app.path().app_data_dir() {
    let file = data_dir.join("minimize_to_tray.txt");
    let _ = std::fs::write(&file, if value { "true" } else { "false" });
  }
}

#[cfg(target_os = "windows")]
fn is_startup_enabled() -> bool {
  unsafe {
    use windows::Win32::System::Registry::*;
    let mut hkey = HKEY::default();
    if RegOpenKeyExW(HKEY_CURRENT_USER, w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run"), 0, KEY_READ, &mut hkey).is_ok() {
      let mut buffer = [0u16; 260];
      let mut size = (buffer.len() * 2) as u32;
      let result = RegQueryValueExW(hkey, w!("qbit-manage-desktop"), None, None, Some(buffer.as_mut_ptr() as *mut _), Some(&mut size));
      let _ = RegCloseKey(hkey);
      result.is_ok()
    } else {
      false
    }
  }
}

#[cfg(target_os = "windows")]
fn set_startup_enabled(enabled: bool) {
  unsafe {
    use windows::Win32::System::Registry::*;
    let mut hkey = HKEY::default();
    if RegOpenKeyExW(HKEY_CURRENT_USER, w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run"), 0, KEY_SET_VALUE, &mut hkey).is_ok() {
      if enabled {
        if let Ok(exe_path) = std::env::current_exe() {
          if let Some(path_str) = exe_path.to_str() {
            let wide_path: Vec<u16> = path_str.encode_utf16().chain(std::iter::once(0)).collect();
            let _ = RegSetValueExW(hkey, w!("qbit-manage-desktop"), 0, REG_SZ, Some(&wide_path));
          }
        }
      } else {
        let _ = RegDeleteValueW(hkey, w!("qbit-manage-desktop"));
      }
      let _ = RegCloseKey(hkey);
    }
  }
}

#[cfg(target_os = "macos")]
fn is_startup_enabled() -> bool {
  if let Ok(home) = std::env::var("HOME") {
    let plist_path = format!("{}/Library/LaunchAgents/com.qbit-manage.desktop.plist", home);
    std::path::Path::new(&plist_path).exists()
  } else {
    false
  }
}

#[cfg(target_os = "macos")]
fn set_startup_enabled(enabled: bool) {
  if let Ok(home) = std::env::var("HOME") {
    let plist_path = format!("{}/Library/LaunchAgents/com.qbit-manage.desktop.plist", home);
    if enabled {
      if let Ok(exe_path) = std::env::current_exe() {
        if let Some(path_str) = exe_path.to_str() {
          let plist_content = format!(r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.qbit-manage.desktop</string>
    <key>ProgramArguments</key>
    <array>
        <string>{}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"#, path_str);
          let _ = std::fs::write(&plist_path, plist_content);
        }
      }
    } else {
      let _ = std::fs::remove_file(&plist_path);
    }
  }
}

#[cfg(target_os = "linux")]
fn is_startup_enabled() -> bool {
  if let Ok(home) = std::env::var("HOME") {
    let desktop_path = format!("{}/.config/autostart/qbit-manage.desktop", home);
    std::path::Path::new(&desktop_path).exists()
  } else {
    false
  }
}

#[cfg(target_os = "linux")]
fn set_startup_enabled(enabled: bool) {
  if let Ok(home) = std::env::var("HOME") {
    let desktop_path = format!("{}/.config/autostart/qbit-manage.desktop", home);
    if enabled {
      if let Ok(exe_path) = std::env::current_exe() {
        if let Some(path_str) = exe_path.to_str() {
          let desktop_content = format!(r#"[Desktop Entry]
Type=Application
Exec={}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=qbit-manage
Comment=Start qbit-manage on login"#, path_str);
          let dir = format!("{}/.config/autostart", home);
          let _ = std::fs::create_dir_all(&dir);
          let _ = std::fs::write(&desktop_path, desktop_content);
        }
      }
    } else {
      let _ = std::fs::remove_file(&desktop_path);
    }
  }
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
  if let Some(server_process) = SERVER_STATE.lock().unwrap().take() {
    let mut child = server_process.child;
    let pid = child.id();

    // On Windows, use immediate process tree termination for faster cleanup
    #[cfg(all(windows, feature = "winjob"))]
    {
      if let Some(job) = server_process.job {
        unsafe {
          use windows::Win32::System::JobObjects::TerminateJobObject;
          let _ = TerminateJobObject(job, 1);
        }
      } else {
        terminate_process_tree_windows(pid);
      }
    }

    #[cfg(all(windows, not(feature = "winjob")))]
    {
      terminate_process_tree_windows(pid);
    }

    // On Unix, try graceful shutdown first but with minimal delay
    #[cfg(unix)]
    {
      unsafe { libc::kill(pid as i32, libc::SIGTERM); }
      // Very brief wait for graceful shutdown
      std::thread::sleep(Duration::from_millis(50));
      if child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
      }
    }

    // Brief wait to ensure process termination, but don't wait too long
    let start = std::time::Instant::now();
    while start.elapsed() < Duration::from_millis(200) {
      match child.try_wait() {
        Ok(Some(_)) => break, // Process has exited
        Ok(None) => {
          // Process still running, wait a bit more
          std::thread::sleep(Duration::from_millis(10));
        }
        Err(_) => break, // Error occurred, assume process is gone
      }
    }

    // Force kill if still running
    let _ = child.kill();
    let _ = child.wait();
  }
}

#[cfg(windows)]
fn terminate_process_tree_windows(pid: u32) {
  use std::os::windows::process::CommandExt;

  // Kill the process tree on Windows using taskkill with hidden window
  let _ = std::process::Command::new("taskkill")
    .args(&["/F", "/T", "/PID", &pid.to_string()])
    .creation_flags(0x08000000) // CREATE_NO_WINDOW
    .stdin(std::process::Stdio::null())
    .stdout(std::process::Stdio::null())
    .stderr(std::process::Stdio::null())
    .output();

  // Also try direct process termination as backup with hidden window
  let _ = std::process::Command::new("taskkill")
    .args(&["/F", "/IM", "qbit-manage-windows-amd64.exe"])
    .creation_flags(0x08000000) // CREATE_NO_WINDOW
    .stdin(std::process::Stdio::null())
    .stdout(std::process::Stdio::null())
    .stderr(std::process::Stdio::null())
    .output();
}


fn cleanup_and_exit_with_app(app: &AppHandle) {
  *SHOULD_EXIT.lock().unwrap() = true;

  // Hide window immediately for instant visual feedback
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.hide();
    // Also minimize to ensure it's completely hidden
    let _ = win.minimize();
  }

  // Do cleanup and exit in background thread so UI doesn't freeze
  // The tray will disappear when the process exits
  std::thread::spawn(|| {
    stop_server();
    std::process::exit(0);
  });
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



fn redirect_to_server(app: &AppHandle, cfg: &AppConfig) {
  let url = match &cfg.base_url {
    Some(b) if !b.trim().is_empty() => format!("http://127.0.0.1:{}/{}", cfg.port, b.trim().trim_start_matches('/')),
    _ => format!("http://127.0.0.1:{}", cfg.port),
  };
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.eval(&format!("window.location.replace('{}')", url));
  }
}

fn start_server(app: &AppHandle, cfg: &AppConfig) -> tauri::Result<()> {
  let mut guard = SERVER_STATE.lock().unwrap();

  // Check if server is already running and clean up if needed
  if let Some(server_process) = guard.as_mut() {
    match server_process.child.try_wait() {
      Ok(Some(_)) => {
        // Process has exited, clean up the old entry
        *guard = None;
      }
      Ok(None) => {
        // Process is still running, don't start another
        return Ok(());
      }
      Err(_) => {
        // Error checking process status, assume it's dead and clean up
        *guard = None;
      }
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

  // Create Windows Job Object if feature is enabled
  #[cfg(all(windows, feature = "winjob"))]
  let job = unsafe {
    use windows::Win32::System::JobObjects::*;
    use windows::Win32::Foundation::*;

    let job = CreateJobObjectW(None, None).ok();
    if let Some(job) = job {
      // Configure job to kill all processes when the job handle is closed
      // and prevent processes from breaking out of the job
      let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
      info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION;

      let _ = SetInformationJobObject(
        job,
        JobObjectExtendedLimitInformation,
        &info as *const _ as *const _,
        std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
      );

      Some(job)
    } else {
      None
    }
  };

  // build command
  let mut cmd = Command::new(server_path);
  cmd.env("QBT_WEB_SERVER", "true")
    .env("QBT_PORT", cfg.port.to_string())
    .env("QBT_DESKTOP_APP", "true")  // Indicate running in desktop app to prevent browser opening
    .stdin(Stdio::null())
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

  let child = cmd.spawn()?;

  // Add process to job object on Windows
  #[cfg(all(windows, feature = "winjob"))]
  if let Some(job) = job {
    unsafe {
      use windows::Win32::System::JobObjects::AssignProcessToJobObject;
      use windows::Win32::Foundation::HANDLE;
      use windows::Win32::System::Threading::OpenProcess;
      use windows::Win32::System::Threading::PROCESS_ALL_ACCESS;

      // Get proper process handle from PID
      let process_handle = OpenProcess(PROCESS_ALL_ACCESS, false, child.id());
      if let Ok(handle) = process_handle {
        let result = AssignProcessToJobObject(job, handle);
        if result.is_err() {
          eprintln!("Failed to assign process to job object: {:?}", result);
        }
        // Don't close the handle here as it's managed by the system
      } else {
        eprintln!("Failed to open process handle for PID: {}", child.id());
      }
    }
  }

  *guard = Some(ServerProcess {
    child,
    #[cfg(all(windows, feature = "winjob"))]
    job,
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

      let minimize_to_tray = load_minimize_setting(&app_handle);
      *MINIMIZE_TO_TRAY.lock().unwrap() = minimize_to_tray;

      let startup_enabled = is_startup_enabled();
      *STARTUP_ENABLED.lock().unwrap() = startup_enabled;

      // Build tray menu (v2 API)
      let open_item = MenuItemBuilder::with_id("open", "Open").build(app)?;
      let restart_item = MenuItemBuilder::with_id("restart", "Restart Server").build(app)?;
      let minimize_item = CheckMenuItemBuilder::with_id("minimize_startup", "Minimize to Tray on Startup")
        .checked(minimize_to_tray)
        .build(app)?;
      let startup_item = CheckMenuItemBuilder::with_id("startup", "Start on System Startup")
        .checked(startup_enabled)
        .build(app)?;
      let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
      let tray_menu = MenuBuilder::new(app)
        .items(&[&open_item, &restart_item, &minimize_item, &startup_item, &quit_item])
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
            "restart" => {
              // Stop server first, then start it again with minimal delay
              stop_server();

              let cfg = app_config(app);
              let app_handle_restart = app.clone();

              // Start server in a separate thread to avoid blocking the UI
              std::thread::spawn(move || {
                // Brief delay to ensure process cleanup
                std::thread::sleep(Duration::from_millis(200));
                if start_server(&app_handle_restart, &cfg).is_ok() {
                  tauri::async_runtime::spawn(async move {
                    if wait_until_ready(cfg.port, &cfg.base_url, Duration::from_secs(15)).await {
                      redirect_to_server(&app_handle_restart, &cfg);
                    }
                  });
                }
              });
            }
            "minimize_startup" => {
              let mut current = MINIMIZE_TO_TRAY.lock().unwrap();
              *current = !*current;
              save_minimize_setting(app, *current);

              // Rebuild menu with updated checked state
              let minimize_to_tray = *current;
              let startup_enabled = *STARTUP_ENABLED.lock().unwrap();
              let open_item = MenuItemBuilder::with_id("open", "Open").build(app)?;
              let restart_item = MenuItemBuilder::with_id("restart", "Restart Server").build(app)?;
              let minimize_item = CheckMenuItemBuilder::with_id("minimize_startup", "Minimize to Tray on Startup")
                .checked(minimize_to_tray)
                .build(app)?;
              let startup_item = CheckMenuItemBuilder::with_id("startup", "Start on System Startup")
                .checked(startup_enabled)
                .build(app)?;
              let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
              let tray_menu = MenuBuilder::new(app)
                .items(&[&open_item, &restart_item, &minimize_item, &startup_item, &quit_item])
                .build()?;

              if let Some(tray) = TRAY_HANDLE.lock().unwrap().as_ref() {
                tray.set_menu(Some(tray_menu))?;
              }
            }
            "startup" => {
              let mut current = STARTUP_ENABLED.lock().unwrap();
              *current = !*current;
              set_startup_enabled(*current);

              // Rebuild menu with updated checked state
              let minimize_to_tray = *MINIMIZE_TO_TRAY.lock().unwrap();
              let startup_enabled = *current;
              let open_item = MenuItemBuilder::with_id("open", "Open").build(app)?;
              let restart_item = MenuItemBuilder::with_id("restart", "Restart Server").build(app)?;
              let minimize_item = CheckMenuItemBuilder::with_id("minimize_startup", "Minimize to Tray on Startup")
                .checked(minimize_to_tray)
                .build(app)?;
              let startup_item = CheckMenuItemBuilder::with_id("startup", "Start on System Startup")
                .checked(startup_enabled)
                .build(app)?;
              let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
              let tray_menu = MenuBuilder::new(app)
                .items(&[&open_item, &restart_item, &minimize_item, &startup_item, &quit_item])
                .build()?;

              if let Some(tray) = TRAY_HANDLE.lock().unwrap().as_ref() {
                tray.set_menu(Some(tray_menu))?;
              }
            }
            "quit" => {
              cleanup_and_exit_with_app(app);
            }
            _ => {}
          }
        })
        .build(app)?;

      *TRAY_HANDLE.lock().unwrap() = Some(_tray_icon);

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

      // Show the window immediately with loading page (unless minimize to tray is enabled)
      if !minimize_to_tray {
        open_app_window(&app_handle);
      }

      // Start server automatically and redirect when ready
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
        RunEvent::ExitRequested { .. } => {
          // Check if we should exit cleanly
          if *SHOULD_EXIT.lock().unwrap() {
            // Already in exit process, allow immediate exit
            return;
          }

          // Set exit flag immediately for responsive UI
          *SHOULD_EXIT.lock().unwrap() = true;

          // Do cleanup in background thread to avoid UI freeze
          std::thread::spawn(|| {
            stop_server();
            std::process::exit(0);
          });
        }
        RunEvent::Exit => {
          // Final cleanup on actual exit
          if !*SHOULD_EXIT.lock().unwrap() {
            stop_server();
          }
        }
        _ => {}
      }
    });
}

fn main() {
  run();
}
