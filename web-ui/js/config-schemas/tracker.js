export const trackerSchema = {
    title: 'Tracker Configuration',
    description: 'Configure tracker-specific settings and rules',
    type: 'complex-object',
    patternProperties: {
        "^(?!other$).*$": { // Matches any key except 'other'
            type: 'object',
            properties: {
                tag: {
                    label: 'Tag(s)',
                    description: 'The tracker tag or additional list of tags defined',
                    type: 'array',
                    items: { type: 'string' }
                },
                cat: {
                    type: 'string',
                    label: 'Category',
                    description: 'Set the category based on tracker URL. This category option takes priority over the category defined in cat'
                },
                notifiarr: {
                    type: 'string',
                    label: 'Notifiarr React Name',
                    description: 'Set this to the notifiarr react name. This is used to add indexer reactions to the notifications sent by Notifiarr'
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
                    description: 'The tracker tag or additional list of tags defined for "other" trackers',
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
                description: 'The tracker tag or additional list of tags defined',
                type: 'array',
                items: { type: 'string' }
            },
            cat: {
                type: 'string',
                label: 'Category',
                description: 'Set the category based on tracker URL. This category option takes priority over the category defined in cat'
            },
            notifiarr: {
                type: 'string',
                label: 'Notifiarr React Name',
                description: 'Set this to the notifiarr react name. This is used to add indexer reactions to the notifications sent by Notifiarr'
            }
        },
        required: ['tag'],
        additionalProperties: false
    }
};
