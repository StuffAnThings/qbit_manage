export const catChangeSchema = {
    title: 'Category Changes',
    description: 'Move torrents from one category to another after they are marked as complete. Be cautious, as this can cause data to be moved if "Default Torrent Management Mode" is set to automatic in qBittorrent.',
    type: 'dynamic-key-value-list',
    useCategoryDropdown: true, // Flag to indicate this should use category dropdown for keys
    fields: [
        {
            type: 'documentation',
            title: 'Category Changes Documentation',
            filePath: 'Config-Setup.md',
            section: 'cat_change',
            defaultExpanded: false
        },
        {
            name: 'category_changes',
            type: 'object',
            label: 'Category Changes',
            description: 'Define old and new category names',
            properties: {
                new_category: {
                    type: 'text',
                    label: 'New Category Name',
                    description: 'Name of the new category',
                    useCategoryDropdown: true // Flag to indicate this field should use category dropdown
                },
                delay_minutes: {
                    type: 'number',
                    label: 'Delay Minutes',
                    description: 'Number of minutes after torrent completion to wait before changing category. Set to 0 for no delay.',
                    default: 0,
                    minimum: 0
                }
            }
        }
    ]
};
