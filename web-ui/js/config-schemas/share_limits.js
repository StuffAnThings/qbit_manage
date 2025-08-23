export const shareLimitsSchema = {
    title: 'Share Limits Configuration',
    description: 'Define prioritized groups to manage share limits for your torrents. Each torrent is matched to the highest-priority group that meets the filter criteria.',
    type: 'share-limits-config',
    fields: [
        {
            type: 'documentation',
            title: 'Share Limits Configuration Documentation',
            filePath: 'Config-Setup.md',
            section: 'share_limits',
            defaultExpanded: false
        },
        {
            name: 'share_limit_groups',
            type: 'object',
            label: 'Share Limit Groups',
            description: 'Define share limit groups and their rules',
            properties: {
                priority: {
                    type: 'number',
                    label: 'Priority',
                    description: 'The priority of the group. Lower numbers have higher priority.',
                    required: true,
                    step: 0.1,
                    default: 999
                },
                include_all_tags: {
                    type: 'array',
                    label: 'Include All Tags',
                    description: 'Torrents must have all of these tags to be included in this group.',
                    items: { type: 'text' }
                },
                include_any_tags: {
                    type: 'array',
                    label: 'Include Any Tags',
                    description: 'Torrents must have at least one of these tags to be included in this group.',
                    items: { type: 'text' }
                },
                exclude_all_tags: {
                    type: 'array',
                    label: 'Exclude All Tags',
                    description: 'Torrents that have all of these tags will be excluded from this group.',
                    items: { type: 'text' }
                },
                exclude_any_tags: {
                    type: 'array',
                    label: 'Exclude Any Tags',
                    description: 'Torrents that have at least one of these tags will be excluded from this group.',
                    items: { type: 'text' }
                },
                categories: {
                    type: 'array',
                    label: 'Categories',
                    description: 'Torrents must be in one of these categories to be included in this group.',
                    items: {
                        type: 'text',
                        useCategoryDropdown: true // Flag to indicate array items should use category dropdown
                    }
                },
                cleanup: {
                    type: 'boolean',
                    label: 'Cleanup',
                    description: 'If true, torrents that meet their share limits will be removed and their contents deleted.',
                    default: false
                },
                max_ratio: {
                    type: 'number',
                    label: 'Maximum Share Ratio',
                    description: 'The maximum share ratio before a torrent is paused. Use -2 for the global limit and -1 for no limit.',
                    default: -1,
                    step: 0.1
                },
                max_seeding_time: {
                    type: 'text',
                    label: 'Maximum Seeding Time',
                    description: 'The maximum seeding time before a torrent is paused. Use -2 for the global limit and -1 for no limit. (e.g., "30d", "1w4d2h").',
                    default: '-1'
                },
                max_last_active: {
                    type: 'text',
                    label: 'Maximum Last Active',
                    description: 'If cleanup is enabled, delete torrents that have been inactive for this duration. Use -1 for no limit. (e.g., "30d", "1w4d2h").',
                    default: '-1'
                },
                min_seeding_time: {
                    type: 'text',
                    label: 'Minimum Seeding Time',
                    description: 'Prevents cleanup from deleting a torrent until it has been seeding for at least this long. (e.g., "30d", "1w4d2h").',
                    default: '0'
                },
                min_last_active: {
                    type: 'text',
                    label: 'Minimum Last Active',
                    description: 'Prevents cleanup from deleting a torrent if it has been active within this duration. (e.g., "30d", "1w4d2h").',
                    default: '0'
                },
                limit_upload_speed: {
                    type: 'number',
                    label: 'Limit Upload Speed (KiB/s)',
                    description: 'The upload speed limit in KiB/s. Use -1 for no limit.',
                    default: -1
                },
                upload_speed_on_limit_reached: {
                    type: 'number',
                    label: 'Upload Speed on Limit Reached (KiB/s)',
                    description: 'When cleanup is false and share limits are reached, throttle per-torrent upload to this value. Use -1 for unlimited.',
                    default: -1
                },
                enable_group_upload_speed: {
                    type: 'boolean',
                    label: 'Enable Group Upload Speed',
                    description: 'If true, the `limit_upload_speed` will be divided equally among all torrents in this group.',
                    default: false
                },
                resume_torrent_after_change: {
                    type: 'boolean',
                    label: 'Resume Torrent After Change',
                    description: 'If true, the torrent will be resumed after its share limits are changed.',
                    default: true
                },
                add_group_to_tag: {
                    type: 'boolean',
                    label: 'Add Group to Tag',
                    description: 'If true, a tag representing the group and its priority will be added to the torrent.',
                    default: true
                },
                min_num_seeds: {
                    type: 'number',
                    label: 'Minimum Number of Seeds',
                    description: 'Prevents cleanup from deleting a torrent if it has fewer than this many seeds.',
                    default: 0
                },
                custom_tag: {
                    type: 'text',
                    label: 'Custom Tag',
                    description: 'Apply a unique custom tag for this group. This tag will be used to identify and manage the share limits for these torrents.',
                    default: ''
                },
                reset_upload_speed_on_unmet_minimums: {
                    type: 'boolean',
                    label: 'Reset Upload Speed on Unmet Minimums',
                    description: 'If true, upload speed limits will be reset to unlimited when minimum conditions (seeding time, number of seeds, last active time) are not met. If false, existing upload speed limits will be preserved.',
                    default: true
                },
                min_torrent_size: {
                    type: 'text',
                    label: 'Minimum Torrent Size',
                    description: 'Only include torrents at least this size in the group. Accepts human-readable sizes like "200MB", "40GB", "1024MiB". Leave blank to disable.',
                    default: ''
                },
                max_torrent_size: {
                    type: 'text',
                    label: 'Maximum Torrent Size',
                    description: 'Only include torrents no larger than this size in the group. Accepts human-readable sizes like "200MB", "40GB", "1024MiB". Leave blank to disable.',
                    default: ''
                }
            }
        }
    ],
    ui: {
        sections: [
            {
                title: 'Basic Configuration',
                fields: ['priority', 'cleanup', 'resume_torrent_after_change', 'add_group_to_tag']
            },
            {
                title: 'Share Limits',
                fields: ['max_ratio', 'max_seeding_time', 'max_last_active', 'min_seeding_time', 'min_last_active', 'min_num_seeds']
            },
            {
                title: 'Size Filters',
                fields: ['min_torrent_size', 'max_torrent_size']
            },
            {
                title: 'Upload Speed Limits',
                fields: ['limit_upload_speed', 'upload_speed_on_limit_reached', 'enable_group_upload_speed', 'reset_upload_speed_on_unmet_minimums']
            },
            {
                title: 'Tag Filters',
                fields: ['include_all_tags', 'include_any_tags', 'exclude_all_tags', 'exclude_any_tags']
            },
            {
                title: 'Category Filters',
                fields: ['categories']
            },
            {
                title: 'Advanced',
                fields: ['custom_tag']
            }
        ],
        fieldIcons: {
            'priority': '<span class="material-icons">priority_high</span>',
            'max_ratio': '<span class="material-icons">share</span>',
            'max_seeding_time': '<span class="material-icons">schedule</span>',
            'min_seeding_time': '<span class="material-icons">timer</span>',
            'limit_upload_speed': '<span class="material-icons">upload</span>',
            'upload_speed_on_limit_reached': '<span class="material-icons">speed</span>',
            'cleanup': '<span class="material-icons">cleaning_services</span>',
            'categories': '<span class="material-icons">category</span>',
            'custom_tag': '<span class="material-icons">label</span>',
            'include_all_tags': '<span class="material-icons">check_circle</span>',
            'include_any_tags': '<span class="material-icons">radio_button_checked</span>',
            'exclude_all_tags': '<span class="material-icons">block</span>',
            'exclude_any_tags': '<span class="material-icons">remove_circle</span>',
            'min_num_seeds': '<span class="material-icons">group</span>',
            'enable_group_upload_speed': '<span class="material-icons">speed</span>',
            'reset_upload_speed_on_unmet_minimums': '<span class="material-icons">refresh</span>',
            'resume_torrent_after_change': '<span class="material-icons">play_arrow</span>',
            'add_group_to_tag': '<span class="material-icons">add_circle</span>',
            'max_last_active': '<span class="material-icons">access_time</span>',
            'min_last_active': '<span class="material-icons">history</span>',
            'min_torrent_size': '<span class="material-icons">sd_storage</span>',
            'max_torrent_size': '<span class="material-icons">sd_storage</span>'
        }
    }
};
