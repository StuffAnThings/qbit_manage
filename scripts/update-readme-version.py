import json
import re
import subprocess
import sys

try:
    from qbittorrentapi import Version
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "qbittorrent-api"])
    from qbittorrentapi import Version

# Check if a branch name was provided
if len(sys.argv) != 2:
    print("Usage: python update_versions.py <branch_name>")
    sys.exit(1)

branch_name = sys.argv[1]
print(f"Branch name: {branch_name}")

# Load or initialize the SUPPORTED_VERSIONS.json file
versions_file_path = "SUPPORTED_VERSIONS.json"
try:
    with open(versions_file_path, encoding="utf-8") as file:
        supported_versions = json.load(file)
except FileNotFoundError:
    supported_versions = {}

# Extract the current qbittorrent-api version from pyproject.toml
print("Reading pyproject.toml...")
with open("pyproject.toml", encoding="utf-8") as file:
    content = file.read()
    match = re.search(r"qbittorrent-api==([\d.]+)", content)
    if match:
        qbittorrent_api_version = match.group(1)
    else:
        raise ValueError("qbittorrent-api version not found in pyproject.toml")

print(f"Current qbittorrent-api version: {qbittorrent_api_version}")

# Fetch the latest supported qBittorrent version
supported_version = Version.latest_supported_app_version()
print(f"Latest supported qBittorrent version: {supported_version}")

# Ensure the branch is initialized in the dictionary
if branch_name not in supported_versions:
    supported_versions[branch_name] = {}

# Update the versions in the dictionary
supported_versions[branch_name]["qbit"] = supported_version
supported_versions[branch_name]["qbitapi"] = qbittorrent_api_version

print("Writing updated versions to SUPPORTED_VERSIONS.json...")
# Write the updated versions back to SUPPORTED_VERSIONS.json
with open(versions_file_path, "w", encoding="utf-8") as file:
    json.dump(supported_versions, file, indent=4)
    file.write("\n")
