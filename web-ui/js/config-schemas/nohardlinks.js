export const nohardlinksSchema = {
    title: 'No Hardlinks Configuration',
    description: 'Configure settings for checking and tagging torrents without hardlinks.',
    type: 'complex-object',
    keyLabel: 'Category',
    keyDescription: 'Category name to check for no hardlinks',
    useCategoryDropdown: true, // Flag to indicate this should use category dropdown
    patternProperties: {
        ".*": { // Matches any category name
            type: 'object',
            properties: {
                exclude_tags: {
                    type: 'array',
                    label: 'Exclude Tags',
                    description: 'List of tags to exclude from the check. Torrents with any of these tags will not be processed.',
                    items: { type: 'string' }
                },
                ignore_root_dir: {
                    type: 'boolean',
                    label: 'Ignore Root Directory',
                    description: 'Ignore any hardlinks detected in the same root_dir (Default True).',
                    default: true
                }
            },
            additionalProperties: false
        }
    },
    additionalProperties: { // Schema for dynamically added properties (new category entries)
        type: 'object',
        properties: {
            exclude_tags: {
                type: 'array',
                label: 'Exclude Tags',
                description: 'List of tags to exclude from the check. Torrents with any of these tags will not be processed.',
                items: { type: 'string' }
            },
            ignore_root_dir: {
                type: 'boolean',
                label: 'Ignore Root Directory',
                description: 'Ignore any hardlinks detected in the same root_dir (Default True).',
                default: true
            }
        },
        additionalProperties: false
    }
};
