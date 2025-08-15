// Build script required for tauri::generate_context! macro (generates code into OUT_DIR)
fn main() {
    // Only include external binaries that exist for the current target
    let target = std::env::var("TARGET").unwrap_or_else(|_| "unknown".to_string());

    // Check which binaries exist and only include those
    let bin_dir = std::path::Path::new("bin");
    if bin_dir.exists() {
        println!("cargo:rerun-if-changed=bin");

        // List all files in bin directory for debugging
        if let Ok(entries) = std::fs::read_dir(bin_dir) {
            for entry in entries.flatten() {
                if let Some(name) = entry.file_name().to_str() {
                    println!("cargo:warning=Found binary: {}", name);
                }
            }
        }
    }

    tauri_build::build();
}
