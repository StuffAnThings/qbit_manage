# qBit_manage Wiki

This wiki should tell you everything you need to know about the script to get it working.

## Getting Started

1. Install qbit_manage either by installing Python3.8.1+ on the localhost and following the [Local Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Local-Installations) Guide or by installing Docker and following the [Docker Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Docker-Installation) Guide or the [unRAID Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Unraid-Installation) Guide.<br>
2. Once installed, you have to [set up your Configuration](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup) by create a [Configuration File](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample) filled with all your values to connect to your qBittorrent instance.
3. Please refer to the list of [Commands](https://github.com/StuffAnThings/qbit_manage/wiki/Commands) that can be used with this tool.

## Support

* If you have any questions or require support please join the [Notifiarr Discord](https://discord.com/invite/AURf8Yz) and post your question under the `qbit-manage` channel.
* If you're getting an Error or have an Enhancement post in the [Issues](https://github.com/StuffAnThings/qbit_manage/issues/new).
* If you have a configuration question post in the [Discussions](https://github.com/StuffAnThings/qbit_manage/discussions/new).
* Pull Request are welcome but please submit them to the [develop branch](https://github.com/StuffAnThings/qbit_manage/tree/develop).

## Table of Contents

* [Home](Home)
  * [Installation](Installation)
    * [unRAID Installation](Unraid-Installation)
    * [Local Installation](Local-Installations)
    * [NIX Installation](Nix-Installation)
    * [Docker Installation](Docker-Installation)
    * [V4 Migration Guide](v4-Migration-Guide)
  * [Config Setup](Config-Setup)
    * [Sample Config File](Config-Setup#config-file)
    * [List of variables](Config-Setup#list-of-variables)
      * [commands](Config-Setup#commands)
      * [qbt](Config-Setup#qbt)
      * [settings](Config-Setup#settings)
      * [directory](Config-Setup#directory)
      * [cat](Config-Setup#cat)
      * [cat_changes](Config-Setup#cat_changes)
      * [tracker](Config-Setup#tracker)
      * [nohardlinks](Config-Setup#nohardlinks)
      * [share_limits](Config-Setup#share_limits)
      * [recyclebin](Config-Setup#recyclebin)
      * [orphaned](Config-Setup#orphaned)
      * [apprise](Config-Setup#apprise)
      * [notifiarr](Config-Setup#notifiarr)
      * [webhooks](Config-Setup#webhooks)
  * [Commands](Commands)
