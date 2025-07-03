export const catSchema = {
    title: 'Categories Configuration',
    description: 'Configure torrent categories and their rules',
    type: 'dynamic-key-value-list',
    fields: [
        {
            name: 'categories',
            type: 'object',
            label: 'Categories',
            description: 'Define categories and their save paths',
            properties: {
                save_path: {
                    type: 'text',
                    label: 'Save Path',
                    description: 'Directory path for this category'
                }
            }
        }
    ]
};
