export const shareLimitsSchema = {
    title: 'Share Limits Configuration',
    description: 'Control how torrent share limits are set depending on the priority of your grouping.',
    type: 'share-limits-config',
    fields: [
        {
            name: 'share_limit_groups',
            type: 'object',
            label: 'Share Limit Groups',
            description: 'Define share limit groups and their rules',
            properties: {
                priority: {
                    type: 'number',
                    label: 'Priority',
                    description: 'The lower the number the higher the priority.',
                    required: true,
                    step: 0.1
                },
                include_all_tags: {
                    type: 'array',
                    label: 'Include All Tags',
                    description: 'Filter the group based on one or more tags. All tags defined here must be present in the torrent.',
                    items: { type: 'text' }
                },
                include_any_tags: {
                    type: 'array',
                    label: 'Include Any Tags',
                    description: 'Filter the group based on one or more tags. Any tags defined here must be present in the torrent.',
                    items: { type: 'text' }
                },
                exclude_all_tags: {
                    type: 'array',
                    label: 'Exclude All Tags',
                    description: 'Filter the group based on one or more tags. All tags defined here must be present in the torrent for it to be excluded.',
                    items: { type: 'text' }
                },
                exclude_any_tags: {
                    type: 'array',
                    label: 'Exclude Any Tags',
                    description: 'Filter the group based on one or more tags. Any tags defined here must be present in the torrent for it to be excluded.',
                    items: { type: 'text' }
                },
                categories: {
                    type: 'array',
                    label: 'Categories',
                    description: 'Filter by including one or more categories.',
                    items: {
                        type: 'text',
                        useCategoryDropdown: true // Flag to indicate array items should use category dropdown
                    }
                },
                cleanup: {
                    type: 'boolean',
                    label: 'Cleanup',
                    description: 'Setting this as true will remove and delete contents of any torrents that satisfies the share limits.',
                    default: false
                },
                max_ratio: {
                    type: 'number',
                    label: 'Maximum Share Ratio',
                    description: 'Will set the torrent Maximum share ratio until torrent is stopped from seeding/uploading. (-2: Global Limit, -1: No Limit)',
                    default: -1,
                    step: 0.1
                },
                max_seeding_time: {
                    type: 'text',
                    label: 'Maximum Seeding Time',
                    description: 'Will set the torrent Maximum seeding time until torrent is stopped from seeding/uploading. (-2: Global Limit, -1: No Limit) (e.g., 32m, 2h32m, 3d2h32m, 1w3d2h32m)',
                    default: '-1'
                },
                max_last_active: {
                    type: 'text',
                    label: 'Maximum Last Active',
                    description: 'Will delete the torrent if cleanup variable is set and if torrent has been inactive longer than x minutes. (e.g., 32m, 2h32m, 3d2h32m, 1w3d2h32m)',
                    default: '-1'
                },
                min_seeding_time: {
                    type: 'text',
                    label: 'Minimum Seeding Time',
                    description: 'Will prevent torrent deletion by the cleanup variable if the torrent has not yet reached this minimum seeding time. (e.g., 32m, 2h32m, 3d2h32m, 1w3d2h32m)',
                    default: '0'
                },
                min_last_active: {
                    type: 'text',
                    label: 'Minimum Last Active',
                    description: 'Will prevent torrent deletion by cleanup variable if torrent has been active within the last x minutes. (e.g., 32m, 2h32m, 3d2h32m, 1w3d2h32m)',
                    default: '0'
                },
                limit_upload_speed: {
                    type: 'number',
                    label: 'Limit Upload Speed (KiB/s)',
                    description: 'Will limit the upload speed KiB/s (KiloBytes/second) (-1 : No Limit)',
                    default: -1
                },
                enable_group_upload_speed: {
                    type: 'boolean',
                    label: 'Enable Group Upload Speed',
                    description: 'Upload speed limits are applied at the group level. This will take `limit_upload_speed` defined and divide it equally among the number of torrents in the group.',
                    default: false
                },
                resume_torrent_after_change: {
                    type: 'boolean',
                    label: 'Resume Torrent After Change',
                    description: 'Will resume your torrent after changing share limits.',
                    default: true
                },
                add_group_to_tag: {
                    type: 'boolean',
                    label: 'Add Group to Tag',
                    description: 'This adds your grouping as a tag with a prefix defined in settings (share_limits_tag).',
                    default: true
                },
                min_num_seeds: {
                    type: 'number',
                    label: 'Minimum Number of Seeds',
                    description: 'Will prevent torrent deletion by cleanup variable if the number of seeds is less than the value set here.',
                    default: 0
                },
                custom_tag: {
                    type: 'text',
                    label: 'Custom Tag',
                    description: 'Apply a custom tag name for this particular group. (WARNING: This tag MUST be unique)',
                    default: ''
                }
            }
        }
    ]
};
