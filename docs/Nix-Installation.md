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
#!/bin/bash

qbmPath="/home/bakerboy448/QbitManage"
qbmVenvPath="$qbmPath"/"qbit-venv/"
qbmServiceName="qbm"
cd "$qbmPath" || exit
currentVersion=$(cat VERSION)
branch=$(git rev-parse --abbrev-ref HEAD)
git fetch
if [ "$(git rev-parse HEAD)" = "$(git rev-parse @'{u}')" ]; then
    echo "=== Already up to date $currentVersion on $branch ==="
    exit 0
fi
git pull
newVersion=$(cat VERSION)
"$qbmVenvPath"/bin/python -m pip install .
echo "=== Updated from $currentVersion to $newVersion on $branch ==="
echo "=== Restarting qbm Service ==="
sudo systemctl restart "$qbmServiceName"
exit 0
```

* Make the update script executable

```bash
chmod +x qbm-update.sh
```

* Run the update script

```bash
./qbm-update.sh
```
