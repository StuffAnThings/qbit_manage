export const qbtSchema = {
    title: 'qBittorrent Connection',
    description: 'Configure the connection to your qBittorrent client.',
    fields: [
        {
            type: 'documentation',
            title: 'qBittorrent Configuration Guide',
            filePath: 'Config-Setup.md',
            section: 'qbt',
            defaultExpanded: false
        },
        {
            name: 'host',
            type: 'text',
            label: 'Host',
            description: 'The IP address and port of your qBittorrent WebUI.',
            required: true,
            placeholder: 'localhost:8080 or qbittorrent:8080'
        },
        {
            name: 'user',
            type: 'text',
            label: 'Username',
            description: 'The username for your qBittorrent WebUI.',
            required: false,
            placeholder: 'admin'
        },
        {
            name: 'pass',
            type: 'password',
            label: 'Password',
            description: 'The password for your qBittorrent WebUI.',
            required: false,
            placeholder: 'Enter password'
        }
    ]
};
