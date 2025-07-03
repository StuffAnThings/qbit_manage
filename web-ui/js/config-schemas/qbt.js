export const qbtSchema = {
    title: 'qBittorrent Connection',
    description: 'Configure connection to qBittorrent client',
    fields: [
        {
            name: 'host',
            type: 'text',
            label: 'Host',
            description: 'qBittorrent host address (e.g., localhost:8080)',
            required: true,
            placeholder: 'localhost:8080 or qbittorrent:8080'
        },
        {
            name: 'user',
            type: 'text',
            label: 'Username',
            description: 'qBittorrent WebUI username',
            required: false,
            placeholder: 'admin'
        },
        {
            name: 'pass',
            type: 'password',
            label: 'Password',
            description: 'qBittorrent WebUI password',
            required: false,
            placeholder: 'Enter password'
        }
    ]
};
