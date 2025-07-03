export const catChangeSchema = {
    title: 'Category Change Configuration',
    description: 'Moves all the torrents from one category to another category if the torrents are marked as complete.',
    type: 'dynamic-key-value-list',
    fields: [
        {
            name: 'category_changes',
            type: 'object',
            label: 'Category Changes',
            description: 'Define old and new category names',
            properties: {
                new_category: {
                    type: 'text',
                    label: 'New Category Name',
                    description: 'Name of the new category'
                }
            }
        }
    ]
};
