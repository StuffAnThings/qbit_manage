export const recyclebinSchema = {
    title: 'Recycle Bin Configuration',
    description: 'Recycle Bin method of deletion will move files into the recycle bin instead of directly deleting them.',
    fields: [
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
            description: 'Will delete Recycle Bin contents if the files have been in the Recycle Bin for more than x days. (0 for immediate deletion, empty for never)',
            min: 0
        },
        {
            name: 'save_torrents',
            type: 'boolean',
            label: 'Save Torrents',
            description: 'This will save a copy of your .torrent and .fastresume file in the recycle bin before deleting it from qbittorrent.',
            default: false
        },
        {
            name: 'split_by_category',
            type: 'boolean',
            label: 'Split by Category',
            description: 'This will split the recycle bin folder by the save path defined in the `cat` attribute.',
            default: false
        }
    ]
};
