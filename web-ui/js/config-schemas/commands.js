export const commandsSchema = {
    title: 'Commands',
    description: 'Enable or disable specific commands to be executed during a run. This section will override any commands that are defined via environment variable or command line',
    fields: [
        {
            type: 'documentation',
            title: 'Commands Documentation',
            filePath: 'Commands.md',
            defaultExpanded: false
        },
        {
            name: 'recheck',
            type: 'boolean',
            label: 'Recheck Torrents',
            description: 'Recheck paused torrents, sorted by lowest size. Resumes the torrent if it has completed.',
            default: false
        },
        {
            name: 'cat_update',
            type: 'boolean',
            label: 'Update Categories',
            description: 'Update torrent categories based on specified rules and move torrents between categories.',
            default: false
        },
        {
            name: 'tag_update',
            type: 'boolean',
            label: 'Update Tags',
            description: 'Update torrent tags, set seed goals, and limit upload speed by tag.',
            default: false
        },
        {
            name: 'rem_unregistered',
            type: 'boolean',
            label: 'Remove Unregistered',
            description: 'Remove torrents that are unregistered with the tracker. Deletes data if not cross-seeded.',
            default: false
        },
        {
            name: 'rem_orphaned',
            type: 'boolean',
            label: 'Remove Orphaned',
            description: 'Scan for and remove orphaned files from your root directory that are not referenced by any torrents.',
            default: false
        },
        {
            name: 'tag_tracker_error',
            type: 'boolean',
            label: 'Tag Tracker Errors',
            description: 'Tag torrents that have a non-working tracker.',
            default: false
        },
        {
            name: 'tag_nohardlinks',
            type: 'boolean',
            label: 'Tag No Hard Links',
            description: 'Tag torrents that do not have any hard links, useful for managing files from Sonarr/Radarr.',
            default: false
        },
        {
            name: 'share_limits',
            type: 'boolean',
            label: 'Apply Share Limits',
            description: 'Apply share limits to torrents based on priority and grouping criteria.',
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
            description: 'Skip emptying the Recycle Bin and Orphaned directories.',
            default: false
        },
        {
            name: 'dry_run',
            type: 'boolean',
            label: 'Dry Run',
            description: 'Simulate a run without making any actual changes to files, tags, or categories.',
            default: true
        },
        {
            name: 'skip_qb_version_check',
            type: 'boolean',
            label: 'Skip qBittorrent Version Check',
            description: 'Bypass the qBittorrent/libtorrent version compatibility check. Use at your own risk.',
            default: false
        }
    ]
};
