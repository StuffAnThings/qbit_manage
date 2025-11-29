export const settingsSchema = {
    title: 'General Settings',
    description: 'Configure general application settings and default behaviors.',
    fields: [
        {
            type: 'documentation',
            title: 'Settings Configuration Guide',
            filePath: 'Config-Setup.md',
            section: 'settings',
            defaultExpanded: false
        },
        {
            name: 'force_auto_tmm',
            type: 'boolean',
            label: 'Force Auto TMM',
            description: 'Force qBittorrent to enable Automatic Torrent Management (ATM) for each torrent.',
            default: false
        },
        {
            name: 'force_auto_tmm_ignore_tags',
            type: 'array',
            label: 'Force Auto TMM Ignore Tags',
            description: 'Torrents with these tags will be ignored when force_auto_tmm is enabled.',
            items: { type: 'text' }
        },
        {
            name: 'tracker_error_tag',
            type: 'text',
            label: 'Tracker Error Tag',
            description: 'The tag to apply to torrents that have a tracker error. Used by the `tag_tracker_error` command.',
            default: 'issue'
        },
        {
            name: 'nohardlinks_tag',
            type: 'text',
            label: 'No Hard Links Tag',
            description: 'The tag to apply to torrents that do not have any hardlinks. Used by the `tag_nohardlinks` command.',
            default: 'noHL'
        },
        {
            name: 'stalled_tag',
            type: 'text',
            label: 'Stalled Tag',
            description: 'The tag to apply to torrents that are stalled during download.',
            default: 'stalledDL'
        },
        {
            name: 'private_tag',
            type: 'text',
            label: 'Private Tag',
            description: 'The tag to apply to private torrents.',
            default: null
        },
        {
            name: 'share_limits_tag',
            type: 'text',
            label: 'Share Limits Tag',
            description: 'The prefix for tags created by share limit groups. For example, a group named "group1" with priority 1 would get the tag "~share_limit_1.group1".',
            default: '~share_limit'
        },
        {
            name: 'share_limits_min_seeding_time_tag',
            type: 'text',
            label: 'Min Seeding Time Tag',
            description: 'The tag to apply to torrents that have not met their minimum seeding time requirement in a share limit group.',
            default: 'MinSeedTimeNotReached'
        },
        {
            name: 'share_limits_min_num_seeds_tag',
            type: 'text',
            label: 'Min Num Seeds Tag',
            description: 'The tag to apply to torrents that have not met their minimum number of seeds requirement in a share limit group.',
            default: 'MinSeedsNotMet'
        },
        {
            name: 'share_limits_last_active_tag',
            type: 'text',
            label: 'Last Active Tag',
            description: 'The tag to apply to torrents that have not met their last active time requirement in a share limit group.',
            default: 'LastActiveLimitNotReached'
        },
        {
            name: 'cat_filter_completed',
            type: 'boolean',
            label: 'Category Filter Completed',
            description: 'If true, the `cat_update` command will only process completed torrents.',
            default: true
        },
        {
            name: 'share_limits_filter_completed',
            type: 'boolean',
            label: 'Share Limits Filter Completed',
            description: 'If true, the `share_limits` command will only process completed torrents.',
            default: true
        },
        {
            name: 'tag_nohardlinks_filter_completed',
            type: 'boolean',
            label: 'Tag No Hardlinks Filter Completed',
            description: 'If true, the `tag_nohardlinks` command will only process completed torrents.',
            default: true
        },
        {
            name: 'rem_unregistered_filter_completed',
            type: 'boolean',
            label: 'Remove Unregistered Filter Completed',
            description: 'If true, the `rem_unregistered` command will only process completed torrents.',
            default: false
        },
        {
            name: 'cat_update_all',
            type: 'boolean',
            label: 'Category Update All',
            description: 'If true, `cat_update` will update all torrents; otherwise, it will only update uncategorized torrents.',
            default: true
        },
        {
            name: 'disable_qbt_default_share_limits',
            type: 'boolean',
            label: 'Disable qBittorrent Default Share Limits',
            description: 'If true, qBittorrent\'s default share limits will be disabled, allowing qbit_manage to handle them exclusively.',
            default: true
        },
        {
            name: 'tag_stalled_torrents',
            type: 'boolean',
            label: 'Tag Stalled Torrents',
            description: 'If true, the `tag_update` command will tag stalled downloading torrents with the `stalled_tag`.',
            default: true
        },
        {
            name: 'rem_unregistered_ignore_list',
            type: 'array',
            label: 'Remove Unregistered Ignore List',
            description: 'A list of keywords. If any of these are found in a tracker\'s status message, the torrent will not be removed by the `rem_unregistered` command.',
            items: { type: 'text' }
        },
        {
            name: 'rem_unregistered_grace_minutes',
            type: 'number',
            label: 'Remove Unregistered Grace Period (minutes)',
            description: 'Minimum age in minutes to protect newly added torrents from removal when a tracker reports unregistered. Set to 0 to disable.',
            default: 10,
            min: 0
        },
        {
            name: 'rem_unregistered_max_torrents',
            type: 'number',
            label: 'Remove Unregistered Max Torrents',
            description: 'Maximum number of torrents to remove per tracker per run. Set to 0 to disable.',
            default: 10,
            min: 0
        }
    ]
};
