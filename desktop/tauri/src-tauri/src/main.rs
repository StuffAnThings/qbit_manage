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
  tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState},
  RunEvent,
};
use tauri_plugin_single_instance::init as single_instance;
use tokio::time::sleep;
#[cfg(target_os = "windows")]
use windows::{core::w, Win32::System::Registry::*};

// Constants
const DEFAULT_PORT: u16 = 8080;
const SERVER_READY_TIMEOUT_SECS: u64 = 20;
const SERVER_RESTART_TIMEOUT_SECS: u64 = 15;
const PROCESS_WAIT_TIMEOUT_MS: u64 = 200;
const GRACEFUL_SHUTDOWN_WAIT_MS: u64 = 50;
const POLL_INTERVAL_MS: u64 = 10;
const HTTP_POLL_INTERVAL_MS: u64 = 250;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

static SERVER_STATE: Lazy<Arc<Mutex<Option<ServerProcess>>>> = Lazy::new(|| Arc::new(Mutex::new(None)));
static SHOULD_EXIT: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));
static MINIMIZE_TO_TRAY: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));
static STARTUP_ENABLED: Lazy<Arc<Mutex<bool>>> = Lazy::new(|| Arc::new(Mutex::new(false)));

struct ServerProcess {
  child: Child,
  #[cfg(all(windows, feature = "winjob"))]
  job: Option<windows::Win32::Foundation::HANDLE>,
}

#[derive(Debug, Clone)]
struct AppConfig {
  args: Vec<String>,
}

fn get_fallback_binary_name() -> &'static str {
  if cfg!(target_os = "windows") { "qbit-manage.exe" } else { "qbit-manage" }
}

fn app_config(app: &AppHandle) -> AppConfig {
  // Collect command-line arguments (skip the first one which is the executable path)
  let args: Vec<String> = std::env::args().skip(1).collect();

  // log for debug
  let _ = app.emit("app-config", format!("args={args:?}"));

  AppConfig { args }
}

fn load_minimize_setting(app: &AppHandle) -> bool {
  match app.path().app_data_dir() {
    Ok(data_dir) => {
      let file = data_dir.join("minimize_to_tray.txt");
      println!("Loading minimize setting from: {:?}", file);

      if file.exists() {
        match std::fs::read_to_string(&file) {
          Ok(content) => {
            let value = content.trim() == "true";
            println!("Loaded minimize setting: {} (content: '{}')", value, content.trim());
            value
          }
          Err(e) => {
            eprintln!("Failed to read minimize setting file: {}", e);
            false
          }
        }
      } else {
        println!("Minimize setting file does not exist, defaulting to false");
        false
      }
    }
    Err(e) => {
      eprintln!("Failed to get app data directory: {}", e);
      false
    }
  }
}

fn save_minimize_setting(app: &AppHandle, value: bool) {
  if let Ok(data_dir) = app.path().app_data_dir() {
    // Ensure the directory exists
    if let Err(e) = std::fs::create_dir_all(&data_dir) {
      eprintln!("Failed to create app data directory: {}", e);
      return;
    }

    let file = data_dir.join("minimize_to_tray.txt");
    if let Err(e) = std::fs::write(&file, if value { "true" } else { "false" }) {
      eprintln!("Failed to save minimize setting to {:?}: {}", file, e);
    } else {
      println!("Successfully saved minimize setting: {} to {:?}", value, file);
    }
  } else {
    eprintln!("Failed to get app data directory");
  }
}

#[cfg(target_os = "windows")]
fn is_startup_enabled() -> bool {
  unsafe {
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
    let mut hkey = HKEY::default();
    if RegOpenKeyExW(HKEY_CURRENT_USER, w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run"), 0, KEY_SET_VALUE, &mut hkey).is_ok() {
      if enabled {
        if let Ok(exe_path) = std::env::current_exe() {
          if let Some(path_str) = exe_path.to_str() {
            let wide_path: Vec<u16> = path_str.encode_utf16().chain(std::iter::once(0)).collect();
            let data_bytes = std::slice::from_raw_parts(wide_path.as_ptr() as *const u8, wide_path.len() * 2);
            let _ = RegSetValueExW(hkey, w!("qbit-manage-desktop"), 0, REG_SZ, Some(data_bytes));
          }
        }
      } else {
        let _ = RegDeleteValueW(hkey, w!("qbit-manage-desktop"));
      }
      let _ = RegCloseKey(hkey);
    }
  }
}

#[cfg(any(target_os = "macos", target_os = "linux"))]
fn get_startup_file_path() -> Option<std::path::PathBuf> {
  std::env::var("HOME").ok().map(|home| {
    #[cfg(target_os = "macos")]
    return std::path::PathBuf::from(format!("{}/Library/LaunchAgents/com.qbit-manage.desktop.plist", home));

    #[cfg(target_os = "linux")]
    return std::path::PathBuf::from(format!("{}/.config/autostart/qbit-manage.desktop", home));
  })
}

#[cfg(target_os = "macos")]
fn is_startup_enabled() -> bool {
  get_startup_file_path().map_or(false, |path| path.exists())
}

#[cfg(target_os = "macos")]
fn set_startup_enabled(enabled: bool) {
  if let Some(plist_path) = get_startup_file_path() {
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
  get_startup_file_path().map_or(false, |path| path.exists())
}

#[cfg(target_os = "linux")]
fn set_startup_enabled(enabled: bool) {
  if let Some(desktop_path) = get_startup_file_path() {
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
          if let Some(dir) = desktop_path.parent() {
            let _ = std::fs::create_dir_all(dir);
          }
          let _ = std::fs::write(&desktop_path, desktop_content);
        }
      }
    } else {
      let _ = std::fs::remove_file(&desktop_path);
    }
  }
}

fn wait_for_process_exit(child: &mut Child, timeout: Duration) {
  let start = std::time::Instant::now();
  while start.elapsed() < timeout {
    match child.try_wait() {
      Ok(Some(_)) => break, // Process has exited
      Ok(None) => {
        // Process still running, wait a bit more
        std::thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));
      }
      Err(_) => break, // Error occurred, assume process is gone
    }
  }
}

fn parse_port_from_args(args: &[String]) -> u16 {
  // CLI args take precedence
  let mut i = 0;
  while i < args.len() {
    let arg = &args[i];
    if arg == "--port" || arg == "-p" {
      if i + 1 < args.len() {
        if let Ok(p) = args[i + 1].parse::<u16>() {
          return p;
        }
      }
    } else if let Some(rest) = arg.strip_prefix("--port=") {
      if let Ok(p) = rest.parse::<u16>() {
        return p;
      }
    }
    i += 1;
  }
  // Fallback to environment variable
  if let Ok(val) = std::env::var("QBT_PORT") {
    if let Ok(p) = val.trim().parse::<u16>() {
      return p;
    }
  }
  // Default
  DEFAULT_PORT
}

fn parse_base_url_from_args(args: &[String]) -> Option<String> {
  // CLI args take precedence
  let mut i = 0;
  while i < args.len() {
    let arg = &args[i];
    if arg == "--base-url" || arg == "--base_url" || arg == "-b" {
      if i + 1 < args.len() {
        let s = args[i + 1].trim().trim_start_matches('/').to_string();
        if !s.is_empty() {
          return Some(s);
        } else {
          return None;
        }
      }
    } else if let Some(rest) = arg.strip_prefix("--base-url=")
      .or_else(|| arg.strip_prefix("--base_url="))
    {
      let s = rest.trim().trim_start_matches('/').to_string();
      if !s.is_empty() {
        return Some(s);
      } else {
        return None;
      }
    }
    i += 1;
  }
  // Fallback to environment variable
  if let Ok(val) = std::env::var("QBT_BASE_URL") {
    let s = val.trim().trim_start_matches('/').to_string();
    if !s.is_empty() {
      return Some(s);
    }
  }
  None
}

fn parse_host_from_args(args: &[String]) -> String {
  // CLI args take precedence
  let mut i = 0;
  while i < args.len() {
    let arg = &args[i];
    if arg == "--host" || arg == "-H" {
      if i + 1 < args.len() {
        let s = args[i + 1].trim().to_string();
        if !s.is_empty() {
          return s;
        }
      }
    } else if let Some(rest) = arg.strip_prefix("--host=") {
      let s = rest.trim().to_string();
      if !s.is_empty() {
        return s;
      }
    }
    i += 1;
  }
  // Fallback to environment variable
  if let Ok(val) = std::env::var("QBT_HOST") {
    let s = val.trim().to_string();
    if !s.is_empty() {
      return s;
    }
  }
  // Default host for desktop client to connect to local server
  "127.0.0.1".to_string()
}

fn build_server_url_effective(args: &[String]) -> String {
  let host = parse_host_from_args(args);
  let port = parse_port_from_args(args);
  match parse_base_url_from_args(args) {
    Some(b) => format!("http://{}:{}/{}", host, port, b),
    None => format!("http://{}:{}", host, port),
  }
}

fn build_tray_menu<R: tauri::Runtime, M: tauri::Manager<R>>(app: &M, minimize_to_tray: bool, startup_enabled: bool) -> Result<tauri::menu::Menu<R>, tauri::Error> {
  let open_item = MenuItemBuilder::with_id("open", "Open").build(app)?;
  let restart_item = MenuItemBuilder::with_id("restart", "Restart Server").build(app)?;
  let minimize_item = CheckMenuItemBuilder::with_id("minimize_startup", "Minimize to Tray on Startup")
    .checked(minimize_to_tray)
    .build(app)?;
  let startup_item = CheckMenuItemBuilder::with_id("startup", "Start on System Startup")
    .checked(startup_enabled)
    .build(app)?;
  let quit_item = MenuItemBuilder::with_id("quit", "Quit").build(app)?;

  MenuBuilder::new(app)
    .items(&[&open_item, &restart_item, &minimize_item, &startup_item, &quit_item])
    .build()
}

fn get_binary_names() -> Vec<&'static str> {
  if cfg!(target_os = "windows") {
    vec!["qbit-manage.exe", "qbit-manage-windows-amd64.exe"]
  } else {
    vec![
      "qbit-manage",
      "qbit-manage-linux-amd64",
      "qbit-manage-macos-x86_64",
      "qbit-manage-macos-arm64"
    ]
  }
}

fn find_binary_in_paths(paths: &[std::path::PathBuf], bin_names: &[&str]) -> Option<std::path::PathBuf> {
  for path in paths {
    for name in bin_names {
      let candidate = path.join(name);
      if candidate.exists() {
        return Some(candidate);
      }
    }
  }
  None
}

fn resolve_server_binary(app: &AppHandle) -> Option<std::path::PathBuf> {
  // Priority: 1) QBM_SERVER_PATH env override
  if let Ok(p) = std::env::var("QBM_SERVER_PATH") {
    let candidate = std::path::PathBuf::from(p);
    if candidate.exists() {
      return Some(candidate);
    }
  }

  let bin_names = get_binary_names();
  let mut search_paths = Vec::new();

  // Priority: 2) resource dir paths
  if let Ok(resource_dir) = app.path().resource_dir() {
    search_paths.push(resource_dir.join("bin"));
    search_paths.push(resource_dir);
  }

  // Priority: 3) executable dir and parent paths
  if let Ok(exe) = std::env::current_exe() {
    if let Some(exe_dir) = exe.parent() {
      search_paths.push(exe_dir.to_path_buf());
      search_paths.push(exe_dir.join(".."));
    }
  }

  find_binary_in_paths(&search_paths, &bin_names)
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
      std::thread::sleep(Duration::from_millis(GRACEFUL_SHUTDOWN_WAIT_MS));
      if child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
      }
    }

    // Brief wait to ensure process termination, but don't wait too long
    wait_for_process_exit(&mut child, Duration::from_millis(PROCESS_WAIT_TIMEOUT_MS));

    // Force kill if still running
    let _ = child.kill();
    let _ = child.wait();
  }
}

#[cfg(windows)]
fn terminate_process_tree_windows(pid: u32) {
  use std::os::windows::process::CommandExt;

  let null_stdio = || (std::process::Stdio::null(), std::process::Stdio::null(), std::process::Stdio::null());

  // Kill the process tree on Windows using taskkill with hidden window
  let (stdin, stdout, stderr) = null_stdio();
  let _ = std::process::Command::new("taskkill")
    .args(&["/F", "/T", "/PID", &pid.to_string()])
    .creation_flags(CREATE_NO_WINDOW)
    .stdin(stdin)
    .stdout(stdout)
    .stderr(stderr)
    .output();

  // Also try direct process termination as backup with hidden window
  let (stdin, stdout, stderr) = null_stdio();
  let _ = std::process::Command::new("taskkill")
    .args(&["/F", "/IM", "qbit-manage-windows-amd64.exe"])
    .creation_flags(CREATE_NO_WINDOW)
    .stdin(stdin)
    .stdout(stdout)
    .stderr(stderr)
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


async fn wait_until_ready(args: &[String], timeout: Duration) -> bool {
  let client = match reqwest::Client::builder().danger_accept_invalid_certs(true).build() {
    Ok(client) => client,
    Err(_) => return false,
  };

  let url = build_server_url_effective(args);

  let start = std::time::Instant::now();
  while start.elapsed() < timeout {
    if let Ok(resp) = client.get(&url).send().await {
      if resp.status().as_u16() < 500 {
        return true;
      }
    }
    sleep(Duration::from_millis(HTTP_POLL_INTERVAL_MS)).await;
  }
  false
}

fn open_app_window(app: &AppHandle) {
  // Check if minimize to tray is enabled and respect it
  let minimize_to_tray = match MINIMIZE_TO_TRAY.lock() {
    Ok(guard) => *guard,
    Err(_) => {
      // If lock fails, load setting directly
      load_minimize_setting(app)
    }
  };

  // Only show window if minimize to tray is disabled, or if explicitly requested
  if !minimize_to_tray {
    if let Some(win) = app.get_webview_window("main") {
      let _ = win.show();
      let _ = win.set_focus();
    }
  }
}

fn force_open_app_window(app: &AppHandle) {
  // Force open window regardless of minimize to tray setting (for user-initiated actions)
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.show();
    let _ = win.set_focus();
  }
}



fn redirect_to_server(app: &AppHandle, cfg: &AppConfig) {
  let url = build_server_url_effective(&cfg.args);
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
    std::path::PathBuf::from(get_fallback_binary_name())
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

  // Forward documented QBT_* environment variables to the server process if present.
  // The child process inherits the parent's environment by default, but we set these explicitly
  // to ensure they are available in packaged contexts as well.
  let qbt_env_keys = [
    "QBT_HOST",
    "QBT_PORT",
    "QBT_BASE_URL",
    "QBT_RUN",
    "QBT_SCHEDULE",
    "QBT_STARTUP_DELAY",
    "QBT_CONFIG_DIR",
    "QBT_LOGFILE",
    "QBT_RECHECK",
    "QBT_CAT_UPDATE",
    "QBT_TAG_UPDATE",
    "QBT_REM_UNREGISTERED",
    "QBT_TAG_TRACKER_ERROR",
    "QBT_REM_ORPHANED",
    "QBT_TAG_NOHARDLINKS",
    "QBT_SHARE_LIMITS",
    "QBT_SKIP_CLEANUP",
    "QBT_DRY_RUN",
    "QBT_LOG_LEVEL",
    "QBT_LOG_SIZE",
    "QBT_LOG_COUNT",
    "QBT_DEBUG",
    "QBT_TRACE",
    "QBT_DIVIDER",
    "QBT_WIDTH",
    "QBT_SKIP_QB_VERSION_CHECK",
  ];
  for key in qbt_env_keys {
    if let Ok(val) = std::env::var(key) {
      cmd.env(key, val);
    }
  }

  // Desktop defaults:
  // - Force web server enabled for the Tauri app, regardless of inherited environment.
  cmd.env("QBT_WEB_SERVER", "true")
    .env("QBT_DESKTOP_APP", "true")  // Indicate running in desktop app to prevent browser opening
    .args(&cfg.args)  // Pass command-line arguments to the binary
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::piped());

  // On Windows, make sure process does not open a console window
  #[cfg(target_os = "windows")]
  {
    use std::os::windows::process::CommandExt;
    cmd.creation_flags(CREATE_NO_WINDOW);
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
      // Load the minimize setting directly in case it hasn't been loaded yet
      let minimize_to_tray = load_minimize_setting(app);
      if !minimize_to_tray {
        if let Some(win) = app.get_webview_window("main") {
          let _ = win.show();
          let _ = win.set_focus();
        }
      }
    }))
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_opener::init())
    .setup(|app| {
      let app_handle = app.handle().clone();

      // Load settings first before any window operations
      let minimize_to_tray = load_minimize_setting(&app_handle);
      *MINIMIZE_TO_TRAY.lock().unwrap() = minimize_to_tray;

      let startup_enabled = is_startup_enabled();
      *STARTUP_ENABLED.lock().unwrap() = startup_enabled;

      // Build tray menu (v2 API)
      let tray_menu = build_tray_menu(app, minimize_to_tray, startup_enabled)?;

      // Create tray icon with explicit icon and ID
      let _tray_icon = TrayIconBuilder::with_id("main")
        .menu(&tray_menu)
        .icon(app.default_window_icon().unwrap().clone())
        .on_tray_icon_event(|tray, event| {
          if let TrayIconEvent::Click {
            button: MouseButton::Left,
            button_state: MouseButtonState::Up,
            ..
          } = event {
            let app = tray.app_handle();
            force_open_app_window(app);
          }
        })
        .on_menu_event(|app, event| {
          match event.id().as_ref() {
            "open" => {
              force_open_app_window(app);
            }
            "restart" => {
              // Stop server first, then start it again with minimal delay
              stop_server();

              let cfg = app_config(app);
              let app_handle_restart = app.clone();

              // Start server in a separate thread to avoid blocking the UI
              std::thread::spawn(move || {
                // Brief delay to ensure process cleanup
                std::thread::sleep(Duration::from_millis(PROCESS_WAIT_TIMEOUT_MS));
                if start_server(&app_handle_restart, &cfg).is_ok() {
                  tauri::async_runtime::spawn(async move {
                    if wait_until_ready(&cfg.args, Duration::from_secs(SERVER_RESTART_TIMEOUT_SECS)).await {
                      redirect_to_server(&app_handle_restart, &cfg);
                    }
                  });
                }
              });
            }
            "minimize_startup" => {
              let mut current = MINIMIZE_TO_TRAY.lock().unwrap();
              *current = !*current;
              let new_value = *current;
              drop(current); // Release the lock early

              save_minimize_setting(app, new_value);
              println!("Toggled minimize to tray setting to: {}", new_value);

              // Rebuild menu with updated checked state
              let startup_enabled = *STARTUP_ENABLED.lock().unwrap();

              if let Ok(tray_menu) = build_tray_menu(app, new_value, startup_enabled) {
                // Get all tray icons and update them
                let tray_icons = app.tray_by_id("main");
                if let Some(tray_icon) = tray_icons {
                  if let Err(e) = tray_icon.set_menu(Some(tray_menu)) {
                    eprintln!("Failed to update tray menu: {}", e);
                  } else {
                    println!("Successfully updated tray menu");
                  }
                } else {
                  eprintln!("Could not find tray icon to update menu");
                }
              } else {
                eprintln!("Failed to build tray menu");
              }
            }
            "startup" => {
              let mut current = STARTUP_ENABLED.lock().unwrap();
              *current = !*current;
              let new_value = *current;
              drop(current); // Release the lock early

              set_startup_enabled(new_value);
              println!("Toggled startup setting to: {}", new_value);

              // Rebuild menu with updated checked state
              let minimize_to_tray = *MINIMIZE_TO_TRAY.lock().unwrap();

              if let Ok(tray_menu) = build_tray_menu(app, minimize_to_tray, new_value) {
                // Get all tray icons and update them
                let tray_icons = app.tray_by_id("main");
                if let Some(tray_icon) = tray_icons {
                  if let Err(e) = tray_icon.set_menu(Some(tray_menu)) {
                    eprintln!("Failed to update tray menu: {}", e);
                  } else {
                    println!("Successfully updated tray menu");
                  }
                } else {
                  eprintln!("Could not find tray icon to update menu");
                }
              } else {
                eprintln!("Failed to build tray menu");
              }
            }
            "quit" => {
              cleanup_and_exit_with_app(app);
            }
            _ => {}
          }
        })
        .build(app)?;

      // Store the tray icon (no longer needed since we use ID-based lookup)
      // *TRAY_HANDLE.lock().unwrap() = Some(_tray_icon);

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
        if wait_until_ready(&cfg.args, Duration::from_secs(SERVER_READY_TIMEOUT_SECS)).await {
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
