export const settingsSchema = {
    title: 'General Settings',
    description: 'Configure general application settings',
    fields: [
        {
            name: 'force_auto_tmm',
            type: 'boolean',
            label: 'Force Auto TMM',
            description: 'Will force qBittorrent to enable Automatic Torrent Management for each torrent.',
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
            description: 'Define the tag of any torrents that do not have a working tracker. (Used in --tag-tracker-error)',
            default: 'issue'
        },
        {
            name: 'nohardlinks_tag',
            type: 'text',
            label: 'No Hard Links Tag',
            description: 'Define the tag of any torrents that don\'t have hardlinks (Used in --tag-nohardlinks)',
            default: 'noHL'
        },
        {
            name: 'stalled_tag',
            type: 'text',
            label: 'Stalled Tag',
            description: 'Will set the tag of any torrents stalled downloading.',
            default: 'stalledDL'
        },
        {
            name: 'share_limits_tag',
            type: 'text',
            label: 'Share Limits Tag',
            description: 'Will add this tag when applying share limits to provide an easy way to filter torrents by share limit group/priority for each torrent',
            default: '~share_limit'
        },
        {
            name: 'share_limits_min_seeding_time_tag',
            type: 'text',
            label: 'Min Seeding Time Tag',
            description: 'Will add this tag when applying share limits to torrents that have not yet reached the minimum seeding time (Used in --share-limits)',
            default: 'MinSeedTimeNotReached'
        },
        {
            name: 'share_limits_min_num_seeds_tag',
            type: 'text',
            label: 'Min Num Seeds Tag',
            description: 'Will add this tag when applying share limits to torrents that have not yet reached the minimum number of seeds (Used in --share-limits)',
            default: 'MinSeedsNotMet'
        },
        {
            name: 'share_limits_last_active_tag',
            type: 'text',
            label: 'Last Active Tag',
            description: 'Will add this tag when applying share limits to torrents that have not yet reached the last active limit (Used in --share-limits)',
            default: 'LastActiveLimitNotReached'
        },
        {
            name: 'cat_filter_completed',
            type: 'boolean',
            label: 'Category Filter Completed',
            description: 'When running --cat-update function, it will filter for completed torrents only.',
            default: true
        },
        {
            name: 'share_limits_filter_completed',
            type: 'boolean',
            label: 'Share Limits Filter Completed',
            description: 'When running --share-limits function, it will filter for completed torrents only.',
            default: true
        },
        {
            name: 'tag_nohardlinks_filter_completed',
            type: 'boolean',
            label: 'Tag No Hardlinks Filter Completed',
            description: 'When running --tag-nohardlinks function, it will filter for completed torrents only.',
            default: true
        },
        {
            name: 'rem_unregistered_filter_completed',
            type: 'boolean',
            label: 'Remove Unregistered Filter Completed',
            description: 'Filters for completed torrents only when running rem_unregistered command',
            default: false
        },
        {
            name: 'cat_update_all',
            type: 'boolean',
            label: 'Category Update All',
            description: 'When running --cat-update function, it will check and update all torrents categories, otherwise it will only update uncategorized torrents.',
            default: true
        },
        {
            name: 'disable_qbt_default_share_limits',
            type: 'boolean',
            label: 'Disable qBittorrent Default Share Limits',
            description: 'When running --share-limits function, it allows QBM to handle share limits by disabling qBittorrents default Share limits.',
            default: true
        },
        {
            name: 'tag_stalled_torrents',
            type: 'boolean',
            label: 'Tag Stalled Torrents',
            description: 'Tags any downloading torrents that are stalled with the user defined `stalledDL` tag when running the tag_update command',
            default: true
        },
        {
            name: 'rem_unregistered_ignore_list',
            type: 'array',
            label: 'Remove Unregistered Ignore List',
            description: 'Ignores a list of words found in the status of the tracker when running rem_unregistered command and will not remove the torrent if matched',
            items: { type: 'text' }
        }
    ]
};
