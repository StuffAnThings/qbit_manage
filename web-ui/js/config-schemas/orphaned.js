export const orphanedSchema = {
    title: 'Orphaned Files Configuration',
    description: 'Configure settings for managing orphaned files.',
    fields: [
        {
            name: 'empty_after_x_days',
            type: 'number',
            label: 'Empty After X Days',
            description: 'Will delete Orphaned data contents if the files have been in the Orphaned data for more than x days. (0 for immediate deletion, empty for never)',
            min: 0
        },
        {
            name: 'exclude_patterns',
            type: 'array',
            label: 'Exclude Patterns',
            description: 'List of patterns to exclude certain files from orphaned.',
            items: { type: 'text' }
        },
        {
            name: 'max_orphaned_files_to_delete',
            type: 'number',
            label: 'Max Orphaned Files to Delete',
            description: 'Set your desired threshold for the maximum number of orphaned files qbm will delete in a single run. (-1 to disable safeguards)',
            default: 50,
            min: -1
        }
    ]
};
