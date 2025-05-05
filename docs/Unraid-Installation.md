
# Unraid Installation - Docker (Recommended)

Thankfully, getting qbit_manager working on unRAID is a fairly simple task. unRAID works mostly with docker containers, so the pre-built container available on docker hub works perfectly with a little configuration. To install a container from docker hub, you will need community applications - a very popular plugin for unRAID servers. If you don't already have this installed, you can install it [here](https://forums.unraid.net/topic/38582-plug-in-community-applications/)

## Basic Installation

1. Head to the Apps tab of unRAID (Community Applications), and search qbit_manage in the upper left search box.
2. Once you have searched for qbit_manage you can simply select it from the list of containers and select install.
3. The template should show all variables that can be edited.
4. Fill out your location for your downloads downloads folder (`Root_Dir`).
   1. qbit_manage needs to be able to view all torrents the way that your qbittorrent views them.
      1. Example: If you have qbittorrent mapped to `/mnt/user/data/:/data` This means that you **MUST** have qbit_managed mapped the same way.
      2. Furthermore, the config file must map the root directory you wish to monitor. This means that in our example of `/data` (which is how qbittorrent views the torrents) that if in your `/data` directory you drill down to `/torrents` that you'll need to update your config file to `/data/torrents`
   2. This could be different depending on your specific setup.
   3. The key takeaways are
      1. Both qbit_manage needs to have the same mappings as qbittorrent
      2. The config file needs to drill down (if required) further to the desired root dir.
5. Select what QBT env options you want to enable or disable (true/false).
6. Hit Apply, and allow unRAID to download the docker container.
7. Navigate to the Docker tab in unRAID, and stop the qbit_manage container if it has auto-started.
8. Create the [config.yml](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample) file as-per the [config-setup documentation](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup) and place in the Appdata folder (`/mnt/user/appdata/qbit_manage/` in the example) **Remember to remove the .sample from the filename**
9. Once finished, run the container. Voila! Logs are located in `/mnt/user/appdata/qbit_manage/logs`.

# Unraid Installation - Localhost (Alternative)

We recommend using the Docker method to install qBit Manage but here is an alternative way to install it locally without the use of docker with the user of userscripts.

**qBit Management**
First, we are going to need [Nerd Pack](https://forums.unraid.net/topic/35866-unraid-6-nerdpack-cli-tools-iftop-iotop-screen-kbd-etc/). <br>
This can be also downloaded from the **Apps** store

Nerd pack will be located in the settings tab
When you open it up you'll see a bunch of packages that you can install. <br> We'll need:

* `python-pip`

* `python3`

* `python-setuptools`

To get this running in unRAID go ahead and download the repo to your computer.

Then take all the data from the zip file and place it somewhere on your server.

An example of this would be: `/mnt/user/data/scripts/qbit/`

Now we need to install the requirements for this script.

Head back over to **User Scripts**

Create a new script: An example of this would be `install-requirements`

In the new text field you'll need to place:

```bash
#!/bin/bash
echo "Installing required packages"
python3 -m pip install /mnt/user/path/to/qbit
echo "Required packages installed"
```

Replace `path/to/` with your path example mines `/data/scripts/qbit/`

Now click **Save Changes**

Now to set a schedule for this bash script to run.

Select **At First Array Start Only** This will run this script every time the array starts on every boot

Now we need to edit the config file that came with the zip file.
<br>The config file should be pretty self-explanatory.
<br>The only thing that must be followed is that **ALL** categories that you see in your qBit **MUST** be added to the config file with associated directories, each directory must be unique for each category.

> If you'd like a guide on setting up cross-seed on unRAID please visit [here](https://github.com/Drazzilb08/cross-seed-guide)

Now we need to go back to **User Scripts** and create our script to run this script

## Add a new script

  You can name yours something like `auto-manage-qbittorrent`
  Here is an example script:

  ```bash
  #!/bin/bash
echo "Running qBitTorrent Management"
python3 /mnt/user/data/scripts/qbit/qbit_manage.py -c /mnt/user/data/scripts/qbit/config.yml -l /mnt/user/data/scripts/qbit/activity.log -r -<list of commands>
echo "qBitTorrent Management Completed"
```

However, at the core, you'll want

```bash
python3 /<path to script>/qbit_manage.py -c /<path to config>/config.yml -l /<path to where you want log file>/activity.log -r -<list of commands>
```

if you want to change the arguments in the `<list of commands>`. The full list of arguments can be seen by using the `-h` command or on the README.

  Once you've got the config file set up you should be all set.
  Don't forget to set a cron schedule mines <br>`*/30 * * * *` <-- Runs every 30 min

**Final note:**<br>
If you're wanting to do a test run please use the `--dry-run` argument anywhere w/in the call to test how things will look. Please do this before running a full run.
