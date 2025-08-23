export const catSchema = {
    title: 'Categories',
    description: 'Define categories and their associated save paths. All save paths in qBittorrent must be defined here. You can use `*` as a wildcard for subdirectories.',
    type: 'complex-object',
    keyLabel: 'Category Name',
    keyDescription: 'Name of the category as it appears in qBittorrent.',
    // Special handling for flat string values (category: path format)
    flatStringValues: true,
    fields: [
        {
            type: 'documentation',
            title: 'Categories Configuration Guide',
            filePath: 'Config-Setup.md',
            section: 'cat',
            defaultExpanded: false
        }
    ],
    patternProperties: {
        ".*": {
            type: 'string',
            label: 'Save Path',
            description: 'The absolute path where torrents in this category should be saved.',
            default: ''
        }
    },
    additionalProperties: {
        type: 'string',
        label: 'Save Path',
        description: 'The absolute path where torrents in this category should be saved.',
        default: ''
    }
};
