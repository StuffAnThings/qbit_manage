export const notificationsSchema = {
    title: 'Notifications',
    description: 'Configure Apprise, Notifiarr, and Webhook notifications.',
    type: 'multi-root-object',
    fields: [
        {
            type: 'section_header',
            label: 'Apprise Configuration'
        },
        {
            name: 'apprise.api_url',
            type: 'text',
            label: 'Apprise API Endpoint URL',
            description: 'Mandatory to fill out the url of your apprise API endpoint. Leave empty to disable.',
            placeholder: 'http://apprise-api:8000'
        },
        {
            name: 'apprise.notify_url',
            type: 'text',
            label: 'Notification Services URL',
            description: 'Mandatory to fill out the notification url/urls based on the notification services provided by apprise.',
            placeholder: 'discord://webhook_id/webhook_token'
        },
        {
            type: 'section_header',
            label: 'Notifiarr Configuration'
        },
        {
            name: 'notifiarr.apikey',
            type: 'password',
            label: 'API Key',
            description: 'Mandatory to fill out API Key. Leave empty to disable.',
            placeholder: 'Your Notifiarr API Key'
        },
        {
            name: 'notifiarr.instance',
            type: 'text',
            label: 'Instance',
            description: 'Optional unique value used to identify your instance. (could be your username on notifiarr for example)',
            placeholder: 'my-instance'
        },
        {
            type: 'section_header',
            label: 'Apply to All Webhooks'
        },
        {
            name: 'apply_to_all_value',
            type: 'select',
            label: 'Value to Apply',
            options: [
                { value: 'notifiarr', label: 'Notifiarr' },
                { value: 'apprise', label: 'Apprise' },
                { value: 'custom', label: 'Custom URL' }
            ],
            default: 'notifiarr'
        },
        {
            type: 'button',
            label: 'Apply to All',
            action: 'apply-to-all'
        },
        {
            type: 'section_header',
            label: 'Webhooks Configuration'
        },
        {
            name: 'webhooks.error',
            type: 'dynamic_select_text',
            label: 'Error Webhook',
            description: 'Webhook for error notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.run_start',
            type: 'dynamic_select_text',
            label: 'Run Start Webhook',
            description: 'Webhook for run start notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.run_end',
            type: 'dynamic_select_text',
            label: 'Run End Webhook',
            description: 'Webhook for run end notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            type: 'section_header',
            label: 'Function Specific Webhooks'
        },
        {
            name: 'webhooks.function.recheck',
            type: 'dynamic_select_text',
            label: 'Recheck Webhook',
            description: 'Webhook for recheck notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.cat_update',
            type: 'dynamic_select_text',
            label: 'Category Update Webhook',
            description: 'Webhook for category update notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.tag_update',
            type: 'dynamic_select_text',
            label: 'Tag Update Webhook',
            description: 'Webhook for tag update notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.rem_unregistered',
            type: 'dynamic_select_text',
            label: 'Remove Unregistered Webhook',
            description: 'Webhook for remove unregistered notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.tag_tracker_error',
            type: 'dynamic_select_text',
            label: 'Tag Tracker Error Webhook',
            description: 'Webhook for tag tracker error notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.rem_orphaned',
            type: 'dynamic_select_text',
            label: 'Remove Orphaned Webhook',
            description: 'Webhook for remove orphaned notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.tag_nohardlinks',
            type: 'dynamic_select_text',
            label: 'Tag No Hardlinks Webhook',
            description: 'Webhook for tag no hardlinks notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.empty_recyclebin',
            type: 'dynamic_select_text',
            label: 'Empty Recycle Bin Webhook',
            description: 'Webhook for empty recycle bin notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.share_limits',
            type: 'dynamic_select_text',
            label: 'Share Limits Webhook',
            description: 'Webhook for share limits notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        },
        {
            name: 'webhooks.function.cleanup_dirs',
            type: 'dynamic_select_text',
            label: 'Cleanup Directories Webhook',
            description: 'Webhook for cleanup directories notifications. Can be "apprise", "notifiarr", or a custom URL.',
            options: ['apprise', 'notifiarr', 'webhook']
        }
    ]
};
