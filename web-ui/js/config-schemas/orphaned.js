export const orphanedSchema = {
    title: 'Orphaned Files',
    description: 'Configure settings for managing orphaned files, which are files in your root directory not associated with any torrent.',
    fields: [
        {
            name: 'empty_after_x_days',
            type: 'number',
            label: 'Empty After X Days',
            description: 'Delete orphaned files after they have been in the orphaned directory for this many days. Set to 0 for immediate deletion, or leave empty to never delete.',
            min: 0
        },
        {
            name: 'exclude_patterns',
            type: 'array',
            label: 'Exclude Patterns',
            description: 'A list of glob patterns to exclude files from being considered orphaned (e.g., "**/.DS_Store").',
            items: { type: 'text' }
        },
        {
            name: 'max_orphaned_files_to_delete',
            type: 'number',
            label: 'Max Orphaned Files to Delete',
            description: 'The maximum number of orphaned files to delete in a single run. This is a safeguard to prevent accidental mass deletions. Set to -1 to disable.',
            default: 50,
            min: -1
        }
    ]
};
