from pathlib import Path

# Define an empty version_info tuple
__version_info__ = ()

# Try to resolve VERSION in a PyInstaller-safe way first, then fall back to repo-relative
version_str = "0.0.0"
try:
    # Prefer runtime-extracted path when bundled
    try:
        from .util import runtime_path  # Safe relative import within package

        version_path = runtime_path("VERSION")
        if version_path.exists():
            version_str = version_path.read_text(encoding="utf-8").strip()
        else:
            raise FileNotFoundError
    except Exception:
        # Fallback to repository structure: modules/../VERSION
        project_dir = Path(__file__).resolve().parent
        version_file_path = (project_dir / ".." / "VERSION").resolve()
        with open(version_file_path, encoding="utf-8") as f:
            version_str = f.read().strip()
except Exception:
    # Last resort default (keeps package importable even if VERSION missing)
    version_str = "0.0.0"

# Get only the first 3 digits
version_str_split = version_str.rsplit("-", 1)[0]
# Convert the version string to a tuple of integers
try:
    __version_info__ = tuple(map(int, version_str_split.split(".")))
except Exception:
    __version_info__ = (0, 0, 0)

# Define the version string using the version_info tuple
__version__ = ".".join(str(i) for i in __version_info__)
