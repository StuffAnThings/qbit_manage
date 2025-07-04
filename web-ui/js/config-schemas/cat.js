export const catSchema = {
    title: 'Categories Configuration',
    description: 'Configure torrent categories and their rules',
    type: 'complex-object',
    keyLabel: 'Category Name',
    keyDescription: 'category name',
    // Special handling for flat string values (category: path format)
    flatStringValues: true,
    patternProperties: {
        ".*": {
            type: 'string',
            label: 'Save Path',
            description: 'Directory path for this category',
            default: ''
        }
    },
    additionalProperties: {
        type: 'string',
        label: 'Save Path',
        description: 'Directory path for this category',
        default: ''
    }
};
