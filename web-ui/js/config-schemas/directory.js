export const directorySchema = {
    title: 'Directory Paths',
    description: 'Configure directory paths for various operations. Proper configuration is crucial for features like orphaned file detection, no-hardlinks tagging, and the recycle bin.',
    fields: [
        {
            type: 'documentation',
            title: 'Directory Configuration Guide',
            filePath: 'Config-Setup.md',
            section: 'directory',
            defaultExpanded: false
        },
        {
            name: 'root_dir',
            type: 'text',
            label: 'Root Directory',
            description: 'The primary download directory qBittorrent uses. This path is essential for checking for orphaned files, no-hardlinks, and unregistered torrents.',
            placeholder: '/path/to/torrents'
        },
        {
            name: 'remote_dir',
            type: 'text',
            label: 'Remote Directory',
            description: 'If running qbit_manage locally and qBittorrent is in Docker, this should be the host path that maps to `root_dir` inside the container. Not required if qbit_manage is also in a container.',
            placeholder: '/mnt/remote'
        },
        {
            name: 'recycle_bin',
            type: 'text',
            label: 'Recycle Bin Directory',
            description: 'The path to the recycle bin folder. If not specified, it defaults to `.RecycleBin` inside your `root_dir`.',
            placeholder: '/path/to/recycle-bin'
        },
        {
            name: 'torrents_dir',
            type: 'text',
            label: 'Torrents Directory',
            description: 'The path to your qBittorrent `BT_backup` directory. This is required to use the `save_torrents` feature in the recycle bin.',
            placeholder: '/path/to/torrent-files'
        },
        {
            name: 'orphaned_dir',
            type: 'text',
            label: 'Orphaned Files Directory',
            description: 'The path to the orphaned files directory. If not specified, it defaults to `orphaned_data` inside your `root_dir`.',
            placeholder: '/path/to/orphaned'
        }
    ]
};
