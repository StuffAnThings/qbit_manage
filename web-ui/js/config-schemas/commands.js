export const commandsSchema = {
    title: 'Commands Configuration',
    description: 'Configure which commands to run',
    fields: [
        {
            name: 'recheck',
            type: 'boolean',
            label: 'Recheck Torrents',
            description: 'Force recheck of all torrents',
            default: false
        },
        {
            name: 'cat_update',
            type: 'boolean',
            label: 'Update Categories',
            description: 'Update torrent categories based on rules',
            default: false
        },
        {
            name: 'tag_update',
            type: 'boolean',
            label: 'Update Tags',
            description: 'Update torrent tags based on rules',
            default: false
        },
        {
            name: 'rem_unregistered',
            type: 'boolean',
            label: 'Remove Unregistered',
            description: 'Remove torrents that are unregistered with tracker',
            default: false
        },
        {
            name: 'rem_orphaned',
            type: 'boolean',
            label: 'Remove Orphaned',
            description: 'Remove orphaned files from filesystem',
            default: false
        },
        {
            name: 'tag_tracker_error',
            type: 'boolean',
            label: 'Tag Tracker Errors',
            description: 'Tag torrents with tracker errors',
            default: false
        },
        {
            name: 'tag_nohardlinks',
            type: 'boolean',
            label: 'Tag No Hard Links',
            description: 'Tag torrents without hard links',
            default: false
        },
        {
            name: 'share_limits',
            type: 'boolean',
            label: 'Apply Share Limits',
            description: 'Apply share ratio and time limits',
            default: false
        },
        {
            type: 'section_header',
            label: 'Execution Options'
        },
        {
            name: 'skip_cleanup',
            type: 'boolean',
            label: 'Skip Cleanup',
            description: 'Skip cleanup operations',
            default: false
        },
        {
            name: 'dry_run',
            type: 'boolean',
            label: 'Dry Run',
            description: 'Simulate command execution without making actual changes.',
            default: true
        },
        {
            name: 'skip_qb_version_check',
            type: 'boolean',
            label: 'Skip qBittorrent Version Check',
            description: 'Skip the qBittorrent version compatibility check.',
            default: false
        }
    ]
};
