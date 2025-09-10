# qBit_manage Wiki

This wiki should tell you everything you need to know about the script to get it working.

## Getting Started

1. **Choose your installation method:**
   - **Desktop App** (Recommended): Download and install the GUI application for [Windows, macOS, or Linux](Installation#desktop-app-installation)
   - **Standalone Binary**: Download the command-line executable for [Windows, macOS, or Linux](Installation#standalone-binary-installation)
   - **Docker**: Follow the [Docker Installation](Docker-Installation) guide for containerized environments
   - **Python/Source**: Install from [PyPI or source code](Installation#pythonsource-installation) for development
   - **unRAID**: Follow the [unRAID Installation](Unraid-Installation) guide for unRAID systems

2. **Configure qbit_manage:**
   - Desktop app users: Configuration is handled through the GUI
   - Command-line users: [Set up your Configuration](Config-Setup) by creating a [Configuration File](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample) with your qBittorrent connection details

3. **Start using qbit_manage:**
   - Review the [Commands](Commands) documentation to understand available features
   - Try the [Web UI](Web-UI) for an intuitive configuration experience
   - Use the [Web API](Web-API) for automation and integration with API key authentication

## Support

* If you have any questions or require support please join the [Notifiarr Discord](https://discord.com/invite/AURf8Yz) and post your question under the `qbit-manage` channel.
* If you're getting an Error or have an Enhancement post in the [Issues](https://github.com/StuffAnThings/qbit_manage/issues/new).
* If you have a configuration question post in the [Discussions](https://github.com/StuffAnThings/qbit_manage/discussions/new).
* Pull Request are welcome but please submit them to the [develop branch](https://github.com/StuffAnThings/qbit_manage/tree/develop).

## Table of Contents

- [Home](Home)
    - [Installation](Installation)
        - [Desktop App](Installation#desktop-app-installation)
        - [Standalone Binary Installation](Installation#standalone-binary-installation)
        - [Python/Source Installation](Installation#pythonsource-installation)
        - [Docker Installation](Docker-Installation)
        - [unRAID Installation](Unraid-Installation)
    - [Config Setup](Config-Setup)
        - [Sample Config File](Config-Setup#config-file)
        - [List of variables](Config-Setup#list-of-variables)
          - [commands](Config-Setup#commands)
          - [qbt](Config-Setup#qbt)
          - [settings](Config-Setup#settings)
          - [directory](Config-Setup#directory)
          - [cat](Config-Setup#cat)
          - [cat_change](Config-Setup#cat_change)
          - [tracker](Config-Setup#tracker)
          - [nohardlinks](Config-Setup#nohardlinks)
          - [share_limits](Config-Setup#share_limits)
          - [recyclebin](Config-Setup#recyclebin)
          - [orphaned](Config-Setup#orphaned)
          - [apprise](Config-Setup#apprise)
          - [notifiarr](Config-Setup#notifiarr)
          - [webhooks](Config-Setup#webhooks)
    - [Commands](Commands)
    - [Web API](Web-API)
    - [Web UI](Web-UI)
    - Extras
       - [Standalone Scripts](Standalone-Scripts)
       - [V4 Migration Guide](v4-Migration-Guide)
