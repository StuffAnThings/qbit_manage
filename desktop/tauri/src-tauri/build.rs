// Build script required for tauri::generate_context! macro (generates code into OUT_DIR)
fn main() {
    // Check which binaries exist for debugging
    let bin_dir = std::path::Path::new("bin");
    if bin_dir.exists() {
        println!("cargo:rerun-if-changed=bin");
    }

    tauri_build::build();
}
