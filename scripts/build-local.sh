#!/bin/bash
# Build the standalone qbit-manage binary (and, by default, the Tauri desktop
# bundle) locally for the current platform, mirroring the CI build in
# .github/workflows/build-binaries.yml. Useful for testing a release artifact
# without pushing or waiting on CI.
set -euo pipefail

readonly APP_NAME="qbit-manage"
readonly ENTRY="qbit_manage.py"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT
readonly TAURI_DIR="${REPO_ROOT}/desktop/tauri/src-tauri"

build_desktop=1
os=""
arch=""

usage() {
  cat <<'EOF'
Usage: scripts/build-local.sh [--skip-desktop] [--help]

Builds the standalone server binary with PyInstaller for the current OS/arch,
then (by default) the Tauri desktop bundle for this platform.

Options:
  --skip-desktop   Build only the PyInstaller server binary (no Rust/Tauri).
  --help           Show this help.

Outputs land in ./out/ (server binary) and the Tauri target bundle dir.
The desktop build requires the Rust toolchain plus the platform's Tauri
prerequisites (see https://tauri.app/start/prerequisites/).
EOF
}

detect_platform() {
  local uname_s uname_m
  uname_s="$(uname -s)"
  uname_m="$(uname -m)"

  case "${uname_s}" in
    Linux) os="linux" ;;
    Darwin) os="macos" ;;
    MINGW* | MSYS* | CYGWIN*) os="windows" ;;
    *)
      printf 'Unsupported OS: %s\n' "${uname_s}" >&2
      exit 1
      ;;
  esac

  case "${uname_m}" in
    x86_64 | amd64)
      arch=$([[ "${os}" == "macos" ]] && echo "x86_64" || echo "amd64")
      ;;
    arm64 | aarch64) arch="arm64" ;;
    *)
      printf 'Unsupported arch: %s\n' "${uname_m}" >&2
      exit 1
      ;;
  esac
}

build_server_binary() {
  command -v pyinstaller >/dev/null 2>&1 || {
    printf 'pyinstaller not found. Install it: pip install pyinstaller\n' >&2
    exit 1
  }

  # PyInstaller add-data uses ';' on native Windows, ':' elsewhere — match CI.
  local sep=":"
  [[ "${os}" == "windows" ]] && sep=";"
  local icon_arg=""
  if [[ "${os}" == "windows" ]]; then
    icon_arg="--icon=icons/qbm_logo.ico"
  elif [[ "${os}" == "macos" ]]; then
    icon_arg="--icon=icons/qbm_logo.icns"
  elif [[ -f "${REPO_ROOT}/icons/qbm_logo.png" ]]; then
    icon_arg="--icon=icons/qbm_logo.png"
  elif [[ -f "${REPO_ROOT}/icons/qbm_logo.ico" ]]; then
    icon_arg="--icon=icons/qbm_logo.ico"
  fi

  printf '==> Building server binary (%s-%s)\n' "${os}" "${arch}"
  (
    cd "${REPO_ROOT}"
    # shellcheck disable=SC2086  # icon_arg is intentionally word-split (may be empty)
    pyinstaller --noconfirm --clean --onefile \
      --name "${APP_NAME}" \
      --add-data "web-ui${sep}web-ui" \
      --add-data "config/config.yml.sample${sep}config" \
      --add-data "icons/qbm_logo.png${sep}." \
      --add-data "VERSION${sep}." \
      --add-data "docs${sep}docs" \
      ${icon_arg} \
      "${ENTRY}"

    mkdir -p out
    if [[ "${os}" == "windows" ]]; then
      mv "dist/${APP_NAME}.exe" "out/${APP_NAME}-windows-${arch}.exe"
    else
      mv "dist/${APP_NAME}" "out/${APP_NAME}-${os}-${arch}"
    fi
  )
  printf '==> Server binary written to out/\n'
}

build_desktop_bundle() {
  command -v cargo >/dev/null 2>&1 || {
    printf 'cargo (Rust) not found. Install Rust or re-run with --skip-desktop.\n' >&2
    printf 'See https://tauri.app/start/prerequisites/\n' >&2
    exit 1
  }

  printf '==> Preparing Tauri sidecar binary\n'
  mkdir -p "${TAURI_DIR}/bin"
  if [[ "${os}" == "windows" ]]; then
    cp "${REPO_ROOT}/out/${APP_NAME}-windows-${arch}.exe" "${TAURI_DIR}/bin/${APP_NAME}-windows-${arch}.exe"
  else
    cp "${REPO_ROOT}/out/${APP_NAME}-${os}-${arch}" "${TAURI_DIR}/bin/${APP_NAME}-${os}-${arch}"
    chmod +x "${TAURI_DIR}/bin/${APP_NAME}-${os}-${arch}"
  fi

  printf '==> Building Tauri desktop bundle (this can take a while)\n'
  (
    cd "${TAURI_DIR}"
    cargo check
    command -v cargo-tauri >/dev/null 2>&1 || cargo install tauri-cli --version "^2" --locked
    case "${os}" in
      windows) cargo tauri build --target x86_64-pc-windows-msvc --bundles nsis ;;
      macos) cargo tauri build --bundles app,dmg ;;
      *) cargo tauri build --bundles deb ;;
    esac
  )
  printf '==> Desktop bundle written under %s/target/release/bundle/\n' "${TAURI_DIR}"
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-desktop) build_desktop=0 ;;
      --help | -h)
        usage
        exit 0
        ;;
      *)
        printf 'Unknown argument: %s\n' "$1" >&2
        usage >&2
        exit 1
        ;;
    esac
    shift
  done

  detect_platform
  build_server_binary
  if [[ "${build_desktop}" -eq 1 ]]; then
    build_desktop_bundle
  fi
  printf '==> Done.\n'
}

main "$@"
