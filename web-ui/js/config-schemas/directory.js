export const directorySchema = {
    title: 'Directory Configuration',
    description: 'Configure directory paths for different operations',
    fields: [
        {
            name: 'root_dir',
            type: 'text',
            label: 'Root Directory',
            description: 'Root downloads directory used to check for orphaned files, noHL, and remove unregistered.',
            placeholder: '/path/to/torrents'
        },
        {
            name: 'remote_dir',
            type: 'text',
            label: 'Remote Directory',
            description: 'Path of docker host mapping of root_dir, this must be set if you\'re running qbit_manage locally (not required if running qbit_manage in a container) and qBittorrent/cross_seed is in a docker.',
            placeholder: '/mnt/remote'
        },
        {
            name: 'recycle_bin',
            type: 'text',
            label: 'Recycle Bin Directory',
            description: 'Path of the RecycleBin folder. Default location is set to `remote_dir/.RecycleBin`.',
            placeholder: '/path/to/recycle-bin'
        },
        {
            name: 'torrents_dir',
            type: 'text',
            label: 'Torrents Directory',
            description: 'Path of the your qbittorrent torrents directory. Required for `save_torrents` attribute in recyclebin',
            placeholder: '/path/to/torrent-files'
        },
        {
            name: 'orphaned_dir',
            type: 'text',
            label: 'Orphaned Files Directory',
            description: 'Path of the Orphaned Directory folder. Default location is set to `remote_dir/orphaned_data`.',
            placeholder: '/path/to/orphaned'
        }
    ]
};
