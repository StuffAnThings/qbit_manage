// Build script required for tauri::generate_context! macro (generates code into OUT_DIR)
use std::fs;
use std::path::Path;

fn main() {
    // Check which binaries exist for debugging
    let bin_dir = std::path::Path::new("bin");
    if bin_dir.exists() {
        println!("cargo:rerun-if-changed=bin");
    }

    // Read version from VERSION file and update both Cargo.toml and tauri.conf.json
    let version_file_path = Path::new("../../../VERSION");
    let cargo_toml_path = Path::new("Cargo.toml");
    let config_path = Path::new("tauri.conf.json");

    if let Ok(version_content) = fs::read_to_string(version_file_path) {
        let version = version_content.trim();

        // Update Cargo.toml with the version
        if let Ok(cargo_content) = fs::read_to_string(cargo_toml_path) {
            if let Ok(mut cargo_toml) = cargo_content.parse::<toml::Value>() {
                // Update the version field in [package] section
                if let Some(package) = cargo_toml.get_mut("package") {
                    if let Some(package_table) = package.as_table_mut() {
                        package_table.insert("version".to_string(), toml::Value::String(version.to_string()));

                        // Write back the updated Cargo.toml
                        if let Ok(updated_cargo) = toml::to_string(&cargo_toml) {
                            let _ = fs::write(cargo_toml_path, updated_cargo);
                        }
                    }
                }
            }
        }

        // Update tauri.conf.json with the version
        if let Ok(config_content) = fs::read_to_string(config_path) {
            // Parse as JSON value
            if let Ok(mut config_json) = serde_json::from_str::<serde_json::Value>(&config_content) {
                // Update the version field
                config_json["version"] = serde_json::Value::String(version.to_string());

                // Write back the updated configuration
                if let Ok(updated_config) = serde_json::to_string_pretty(&config_json) {
                    let _ = fs::write(config_path, updated_config);
                }
            }
        }

        println!("cargo:rustc-env=TAURI_APP_VERSION={}", version);
    } else {
        // Fallback to default version if VERSION file not found
        println!("cargo:rustc-env=TAURI_APP_VERSION=0.1.0");
    }

    // Tell cargo to rerun this script if VERSION file changes
    println!("cargo:rerun-if-changed=../../../VERSION");
    // Also rerun if Cargo.toml changes to prevent infinite loops
    println!("cargo:rerun-if-changed=Cargo.toml");

    tauri_build::build();
}
