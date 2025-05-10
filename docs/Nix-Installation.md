# \*Nix Installation

* Download the script

```bash
wget -O - https://github.com/StuffAnThings/qbit_manage/archive/master.tar.gz | tar xz --strip=1 "qbit_manage-master"
```

* Make it executable

```bash
chmod +x qbit_manage.py
```

* Get & Install Requirements

```bash
pip install .
```

* Create Config

```bash
cd config
cp config.yml.sample config.yml
nano -e config.yml
```

* Create the update script

```bash
nano qbm-update.sh
```

* Paste the below into the update script and update the Paths and Service Name (if using systemd)

```bash
#!/usr/bin/env bash
set -e
set -o pipefail

force_update=${1:-false}

# Constants
QBM_PATH="/opt/qbit_manage"
QBM_VENV_PATH="/opt/.venv/qbm-venv"
QBM_SERVICE_NAME="qbmanage"
QBM_UPSTREAM_GIT_REMOTE="origin"
QBM_VERSION_FILE="$QBM_PATH/VERSION"
QBM_REQUIREMENTS_FILE="$QBM_PATH/pyproject.toml"
CURRENT_UID=$(id -un)

# Check if QBM is installed and if the current user owns it
check_qbm_installation() {
    if [ -d "$QBM_PATH" ]; then
        qbm_repo_owner=$(stat --format='%U' "$QBM_PATH")
        qbm_repo_group=$(stat --format='%G' "$QBM_PATH")
        if [ "$qbm_repo_owner" != "$CURRENT_UID" ]; then
            echo "You do not own the QbitManage repo. Please run this script as the user that owns the repo [$qbm_repo_owner]."
            echo "use 'sudo -u $qbm_repo_owner -g $qbm_repo_group /path/to/qbm-update.sh'"
            exit 1
        fi
    else
        echo "QbitManage folder does not exist. Please install QbitManage before running this script."
        exit 1
    fi
}

# Update QBM if necessary
update_qbm() {
    current_branch=$(git -C "$QBM_PATH" rev-parse --abbrev-ref HEAD)
    echo "Current Branch: $current_branch. Checking for updates..."
    git -C "$QBM_PATH" fetch
    if [ "$(git -C "$QBM_PATH" rev-parse HEAD)" = "$(git -C "$QBM_PATH" rev-parse @'{u}')" ] && [ "$force_update" != true ]; then
        current_version=$(cat "$QBM_VERSION_FILE")
        echo "=== Already up to date $current_version on $current_branch ==="
        exit 0
    fi
    current_requirements=$(sha1sum "$QBM_REQUIREMENTS_FILE" | awk '{print $1}')
    git -C "$QBM_PATH" reset --hard "$QBM_UPSTREAM_GIT_REMOTE/$current_branch"
}

# Update virtual environment if requirements have changed
update_venv() {
    new_requirements=$(sha1sum "$QBM_REQUIREMENTS_FILE" | awk '{print $1}')
    if [ "$current_requirements" != "$new_requirements" ] || [ "$force_update" = true ]; then
        echo "=== Requirements changed, updating venv ==="
        "$QBM_VENV_PATH/bin/python" -m pip  install --upgrade "$QBM_PATH"
    fi
}

# Restart the QBM service
restart_service() {
    echo "=== Restarting QBM Service ==="
    sudo systemctl restart "$QBM_SERVICE_NAME"
    new_version=$(cat "$QBM_VERSION_FILE")
    echo "=== Updated to $new_version on $current_branch"
}

# Main script execution
check_qbm_installation
update_qbm
update_venv
restart_service
```

* Make the update script executable

```bash
chmod +x qbm-update.sh
```

* Run the update script

```bash
./qbm-update.sh
```
