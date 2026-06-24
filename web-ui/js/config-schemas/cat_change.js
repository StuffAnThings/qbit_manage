export const catChangeSchema = {
    title: 'Category Changes',
    description: 'Move torrents from one category to another after they are marked as complete. Be cautious, as this can cause data to be moved if "Default Torrent Management Mode" is set to automatic in qBittorrent.',
    type: 'complex-object',
    useCategoryDropdown: true, // old-category key uses the category dropdown
    keyLabel: 'Old Category',
    fields: [
        {
            type: 'documentation',
            title: 'Category Changes Documentation',
            filePath: 'Config-Setup.md',
            section: 'cat_change',
            defaultExpanded: false
        }
    ],
    // Value schema: each old category maps to {new_cat, delay_minutes}. These key
    // names match the backend (modules.config.normalize_cat_change) exactly so the
    // saved YAML round-trips. The simple form (old_cat: "new_cat") is normalized to
    // this object shape on load by ConfigForm._preprocessComplexObjectData.
    patternProperties: {
        ".*": {
            type: 'object',
            properties: {
                new_cat: {
                    type: 'string',
                    label: 'New Category',
                    description: 'Category to move torrents to once they complete.',
                    useCategoryDropdown: true
                },
                delay_minutes: {
                    type: 'number',
                    label: 'Delay (minutes)',
                    description: 'Whole minutes after torrent completion to wait before changing category. Set to 0 for no delay.',
                    default: 0,
                    minimum: 0
                }
            },
            required: ['new_cat'],
            additionalProperties: false
        }
    },
    additionalProperties: { // Schema for newly added entries
        type: 'object',
        properties: {
            new_cat: {
                type: 'string',
                label: 'New Category',
                description: 'Category to move torrents to once they complete.',
                useCategoryDropdown: true
            },
            delay_minutes: {
                type: 'number',
                label: 'Delay (minutes)',
                description: 'Whole minutes after torrent completion to wait before changing category. Set to 0 for no delay.',
                default: 0,
                minimum: 0
            }
        },
        required: ['new_cat'],
        additionalProperties: false
    }
};
