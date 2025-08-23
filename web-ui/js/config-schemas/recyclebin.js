export const recyclebinSchema = {
    title: 'Recycle Bin',
    description: 'Configure the recycle bin to move deleted files to a temporary location instead of permanently deleting them. This provides a safety net for accidental deletions.',
    fields: [
        {
            type: 'documentation',
            title: 'Recycle Bin Configuration Documentation',
            filePath: 'Config-Setup.md',
            section: 'recyclebin',
            defaultExpanded: false
        },
        {
            name: 'enabled',
            type: 'boolean',
            label: 'Enable Recycle Bin',
            description: 'Enable or disable the recycle bin functionality.',
            default: true,
            required: true
        },
        {
            name: 'empty_after_x_days',
            type: 'number',
            label: 'Empty After X Days',
            description: 'Delete files from the recycle bin after this many days. Set to 0 for immediate deletion, or leave empty to never delete.',
            min: 0
        },
        {
            name: 'save_torrents',
            type: 'boolean',
            label: 'Save Torrents',
            description: 'Save a copy of the .torrent and .fastresume files in the recycle bin. Requires `torrents_dir` to be set in the Directory configuration.',
            default: false
        },
        {
            name: 'split_by_category',
            type: 'boolean',
            label: 'Split by Category',
            description: 'Organize the recycle bin by creating subdirectories based on the torrent\'s category save path.',
            default: false
        }
    ]
};
