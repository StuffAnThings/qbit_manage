export const nohardlinksSchema = {
    title: 'No Hardlinks',
    description: 'Configure settings for tagging torrents that are not hardlinked. This is useful for identifying files that can be safely deleted after being processed by applications like Sonarr or Radarr.',
    type: 'complex-object',
    keyLabel: 'Category',
    keyDescription: 'Category to check for torrents without hardlinks.',
    useCategoryDropdown: true, // Flag to indicate this should use category dropdown
    fields: [
        {
            type: 'documentation',
            title: 'No Hardlinks Configuration Documentation',
            filePath: 'Config-Setup.md',
            section: 'nohardlinks',
            defaultExpanded: false
        }
    ],
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
                    description: 'If true, ignore hardlinks found within the same root directory.',
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
                description: 'If true, ignore hardlinks found within the same root directory.',
                default: true
            }
        },
        additionalProperties: false
    }
};
