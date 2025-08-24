export const trackerSchema = {
    title: 'Tracker',
    description: 'Configure tags and categories based on tracker URLs. Use a keyword from the tracker URL to define rules. The `other` key is a special keyword for trackers that do not match any other entry.',
    type: 'complex-object',
    fields: [
        {
            type: 'documentation',
            title: 'Tracker Configuration Documentation',
            filePath: 'Config-Setup.md',
            section: 'tracker',
            defaultExpanded: false
        }
    ],
    patternProperties: {
        "^(?!other$).*$": { // Matches any key except 'other'
            type: 'object',
            properties: {
                tag: {
                    label: 'Tag(s)',
                    description: 'The tag or tags to apply to torrents from this tracker.',
                    type: 'array',
                    items: { type: 'string' }
                },
                cat: {
                    type: 'string',
                    label: 'Category',
                    description: 'Set a category for torrents from this tracker. This will override any category set by the `cat` section.',
                    useCategoryDropdown: true // Flag to indicate this field should use category dropdown
                },
                notifiarr: {
                    type: 'string',
                    label: 'Notifiarr React Name',
                    description: 'The Notifiarr "React Name" for this tracker, used for indexer-specific reactions in notifications.',
                }
            },
            required: ['tag'],
            additionalProperties: false
        },
        "other": { // Special handling for the 'other' key
            type: 'object',
            properties: {
                tag: {
                    label: 'Tag(s)',
                    description: 'The tag or tags to apply to torrents from any tracker not explicitly defined elsewhere.',
                    type: 'array',
                    items: { type: 'string' }
                }
            },
            required: ['tag'],
            additionalProperties: false
        }
    },
    additionalProperties: { // Schema for dynamically added properties (new tracker entries)
        type: 'object',
        properties: {
            tag: {
                label: 'Tag(s)',
                description: 'The tag or tags to apply to torrents from this tracker.',
                type: 'array',
                items: { type: 'string' }
            },
            cat: {
                type: 'string',
                label: 'Category',
                description: 'Set a category for torrents from this tracker. This will override any category set by the `cat` section.',
                useCategoryDropdown: true // Flag to indicate this field should use category dropdown
            },
            notifiarr: {
                type: 'string',
                label: 'Notifiarr React Name',
                description: 'The Notifiarr "React Name" for this tracker, used for indexer-specific reactions in notifications.',
            }
        },
        required: ['tag'],
        additionalProperties: false
    }
};
