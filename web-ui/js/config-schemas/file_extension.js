export const fileExtTagsSchema = {
    title: 'File Extension Tags',
    description: 'Tag torrents based on file extensions found in the torrent. This will check all files in the torrent and apply tags if any file matches the specified extension.',
    type: 'complex-object',
    keyLabel: 'File Extension',
    keyDescription: 'File extension to match (without the leading dot, case-insensitive)',
    fields: [
        {
            type: 'documentation',
            title: 'File Extension Tags Documentation',
            filePath: 'Config-Setup.md',
            section: 'file_extension',
            defaultExpanded: false
        }
    ],
    patternProperties: {
        ".*": { // Matches any extension
            type: 'object',
            properties: {
                tag: {
                    label: 'Tag(s)',
                    description: 'The tag or tags to apply when this file extension is found.',
                    type: 'array',
                    items: { type: 'string' }
                }
            },
            required: ['tag'],
            additionalProperties: false
        }
    },
    additionalProperties: { // Schema for dynamically added properties (new extension entries)
        type: 'object',
        properties: {
            tag: {
                label: 'Tag(s)',
                description: 'The tag or tags to apply when this file extension is found.',
                type: 'array',
                items: { type: 'string' }
            }
        },
        required: ['tag'],
        additionalProperties: false
    }
};

