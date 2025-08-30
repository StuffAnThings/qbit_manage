# Unraid Installation

## Docker Installation (Recommended)

The easiest way to run qbit_manage on Unraid is using the Docker container from Docker Hub.

### Prerequisites

Install [Community Applications](https://forums.unraid.net/topic/38582-plug-in-community-applications/) plugin if you haven't already.

### Installation Steps

1. **Install the Container**
   - Go to the **Apps** tab in Unraid
   - Search for "qbit_manage" in the search box
   - Select the qbit_manage container and click **Install**

2. **Configure Path Mapping**

> [!IMPORTANT]
> qbit_manage must have the same path mappings as your qBittorrent container to properly access your torrents.

   **Example:** If qBittorrent is mapped as `/mnt/user/data/:/data`, then qbit_manage must also be mapped the same way.

   - Set the `Root_Dir` variable to match your qBittorrent download path
   - Ensure both containers can see torrents at the same paths

3. **Configure Environment Variables**
   - Set `QBT_WEB_SERVER=true` to enable the Web UI (recommended)
   - Configure other QBT environment options as needed

4. **Apply and Download**
   - Click **Apply** to download and create the container
   - The container may auto-start - stop it if needed

5. **Create Configuration File**
   - Navigate to `/mnt/user/appdata/qbit_manage/` on your Unraid server
   - Download the [sample config file](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample)
   - Rename it to `config.yml` (remove the `.sample` extension)
   - Edit the file according to the [Config Setup guide](Config-Setup)

 > [!TIP]
 > Make sure the `root_dir` in your config matches how qBittorrent sees your torrents (e.g., `/data/torrents`)

6. **Start the Container**
   - Start the qbit_manage container from the Docker tab
   - Check logs at `/mnt/user/appdata/qbit_manage/logs/`

### Web UI Access

If you enabled the web server, access the Web UI at:
```
http://[UNRAID-IP]:8080
```

## Alternative: User Scripts Installation

> [!WARNING]
> This method is more complex and not recommended for most users. Use the Docker method above instead.

<details>
<summary>Click to expand User Scripts installation method</summary>

### Requirements
- [Nerd Pack](https://forums.unraid.net/topic/35866-unraid-6-nerdpack-cli-tools-iftop-iotop-screen-kbd-etc/) plugin
- Python packages: `python-pip`, `python3`, `python-setuptools`

### Installation
1. Install required Python packages via Nerd Pack
2. Download qbit_manage source to your server (e.g., `/mnt/user/data/scripts/qbit/`)
3. Create a User Script to install requirements:
   ```bash
   #!/bin/bash
   echo "Installing required packages"
   python3 -m pip install /mnt/user/data/scripts/qbit/
   echo "Required packages installed"
   ```
4. Set the script to run "At First Array Start Only"
5. Create another User Script to run qbit_manage:
   ```bash
   #!/bin/bash
   echo "Running qBitTorrent Management"
   python3 /mnt/user/data/scripts/qbit/qbit_manage.py \
     --config-dir /mnt/user/data/scripts/qbit/ \
     --log-file /mnt/user/data/scripts/qbit/activity.log \
     --run
   echo "qBitTorrent Management Completed"
   ```
6. Set a cron schedule (e.g., `*/30 * * * *` for every 30 minutes)

> [!TIP]
> Use `--dry-run` flag first to test your configuration before running live.

</details>

## Troubleshooting

### Common Issues

**Path Mapping Problems:**
- Ensure qbit_manage and qBittorrent have identical path mappings
- Check that the `root_dir` in config.yml matches the container's view of torrents

**Permission Issues:**
- Verify the qbit_manage container has read/write access to your download directories
- Check Unraid user/group permissions

**Container Won't Start:**
- Review container logs in the Docker tab
- Verify config.yml syntax is correct
- Ensure all required path mappings exist
