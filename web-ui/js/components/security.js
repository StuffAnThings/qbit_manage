/**
 * Security Component for qBit Manage Web UI
 * Login mode, OpenID Connect settings, password, and API key.
 */

import { API } from '../api.js';
import { showToast } from '../utils/toast.js';
import { showModal } from '../utils/modal.js';
import { EYE_ICON_SVG, EYE_SLASH_ICON_SVG } from '../utils/icons.js';

const MODE_HELP = {
    local: '<strong>Local:</strong> login form with a username and password.',
    oidc: '<strong>OpenID Connect:</strong> single sign-on for one user, for example with Authentik. The local password works only if you turn on the break-glass option.',
    api_only: '<strong>API only:</strong> no browser login. Scripts use an API key or HTTP Basic.'
};

export class SecurityComponent {
    constructor(containerId, apiInstance = null) {
        this.container = document.getElementById(containerId);
        this.api = apiInstance || window.app?.api || new API();
        this.settings = null;
    }

    async init() {
        try {
            await this.load();
            this.render();
            this.bindEvents();
        } catch (error) {
            showToast('Failed to load security settings', 'error');
        }
    }

    async load() {
        this.settings = await this.api.makeRequest('/security', 'GET');
    }

    esc(value) {
        const div = document.createElement('div');
        div.textContent = value ?? '';
        return div.innerHTML.replace(/"/g, '&quot;');
    }

    render() {
        const s = this.settings;
        const mode = s.mode || 'local';
        const modes = [['local', 'Local login'], ['oidc', 'OpenID Connect']];
        if (mode === 'api_only') {
            modes.push(['api_only', 'API only']);
        }
        this.container.innerHTML = `
            <div class="security-settings">
                <div class="section-header">
                    <h2>Security Settings</h2>
                    <p class="section-description">
                        A login is always required while the web server is on. Choose how people sign in.
                    </p>
                </div>

                <div class="settings-form">
                    <div class="form-group">
                        <label for="auth-mode" class="form-label">Login mode</label>
                        <select id="auth-mode" class="form-select">
                            ${modes.map(([value, label]) => `<option value="${value}" ${mode === value ? 'selected' : ''}>${label}</option>`).join('')}
                        </select>
                        <div class="field-description" id="mode-help"></div>
                    </div>

                    <div class="form-group" id="public-url-group">
                        <label for="public-url" class="form-label">Public URL</label>
                        <input type="text" id="public-url" class="form-input" value="${this.esc(s.public_url)}" placeholder="https://qbm.example.com">
                        <div class="field-description">The address people type in the browser, scheme and host only (no path). Used for the OpenID Connect redirect and for the browser origin check when a proxy changes the host name.</div>
                    </div>

                    <div class="form-group" id="https-only-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="https-only" ${s.https_only ? 'checked' : ''}>
                            <span class="checkmark"></span>
                            Send the session cookie over HTTPS only
                        </label>
                        <div class="field-description">Turn on when you reach qBit Manage through HTTPS. Takes effect after a restart.</div>
                    </div>

                    <div id="oidc-section">
                        <h3>OpenID Connect</h3>
                        <div class="form-group">
                            <label for="oidc-metadata-url" class="form-label">Issuer discovery URL</label>
                            <input type="text" id="oidc-metadata-url" class="form-input" value="${this.esc(s.oidc_metadata_url)}" placeholder="https://auth.example.com/application/o/qbit-manage/.well-known/openid-configuration">
                        </div>
                        <div class="form-group">
                            <label for="oidc-client-id" class="form-label">Client ID</label>
                            <input type="text" id="oidc-client-id" class="form-input" value="${this.esc(s.oidc_client_id)}">
                        </div>
                        <div class="form-group">
                            <label for="oidc-client-secret" class="form-label">Client secret</label>
                            <input type="password" id="oidc-client-secret" class="form-input" autocomplete="new-password" placeholder="${s.has_oidc_client_secret ? '&lt;redacted&gt; (leave blank to keep)' : 'Enter client secret'}">
                        </div>
                        <div class="form-group">
                            <label for="oidc-sub" class="form-label">Allowed user (sub claim)</label>
                            <input type="text" id="oidc-sub" class="form-input" value="${this.esc(s.oidc_sub)}">
                        </div>
                        <div class="form-group">
                            <label for="oidc-email" class="form-label">Or allowed email</label>
                            <input type="text" id="oidc-email" class="form-input" value="${this.esc(s.oidc_email)}">
                            <div class="field-description">Accepted only when the provider marks the address as verified. One identity is allowed.</div>
                        </div>
                        <div class="form-group">
                            <label class="checkbox-label">
                                <input type="checkbox" id="allow-local-login" ${s.allow_local_login ? 'checked' : ''}>
                                <span class="checkmark"></span>
                                Break-glass: also allow the local password
                            </label>
                        </div>
                    </div>

                    <div id="credentials-section">
                        <h3>Local login</h3>
                        <div class="form-group">
                            <label for="username" class="form-label">Username</label>
                            <input type="text" id="username" class="form-input" value="${this.esc(s.username)}" autocomplete="username">
                        </div>
                        <div class="form-group">
                            <label for="password" class="form-label">New password</label>
                            <div class="password-input-group">
                                <input type="password" id="password" class="form-input" autocomplete="new-password" placeholder="Leave blank to keep the current password">
                                <button type="button" class="btn btn-icon password-toggle" data-target="password">${EYE_ICON_SVG}</button>
                            </div>
                            <div class="field-description">8 or more characters with 3 of: uppercase, lowercase, number, special (!@#$%^&amp;*).</div>
                        </div>
                        <div class="form-group">
                            <label for="confirm-password" class="form-label">Confirm new password</label>
                            <div class="password-input-group">
                                <input type="password" id="confirm-password" class="form-input" autocomplete="new-password">
                                <button type="button" class="btn btn-icon password-toggle" data-target="confirm-password">${EYE_ICON_SVG}</button>
                            </div>
                        </div>
                        ${s.has_password ? `
                        <div class="form-group">
                            <label for="current-password" class="form-label">Current password</label>
                            <input type="password" id="current-password" class="form-input" autocomplete="current-password">
                            <div class="field-description">Needed to set a new password. Changing the password, username, or mode signs out every browser.</div>
                        </div>` : ''}
                    </div>

                    <div id="api-key-section">
                        <h3>API Key</h3>
                        <div class="form-group">
                            <div class="field-description">${s.has_api_key ? 'An API key is set. The key is never shown again after it is created.' : 'No API key is set.'}</div>
                            <div class="api-key-input-group">
                                <button type="button" class="btn btn-secondary" id="generate-api-key">${s.has_api_key ? 'Regenerate Key' : 'Generate Key'}</button>
                                ${s.has_api_key ? '<button type="button" class="btn btn-outline" id="clear-api-key">Clear Key</button>' : ''}
                            </div>
                            <div class="field-description">Scripts send it in the X-Api-Key header. An API key cannot change these settings.</div>
                        </div>
                    </div>

                    <div class="form-actions">
                        <button type="button" class="btn btn-primary" id="save-security-settings">Save Settings</button>
                    </div>
                </div>
            </div>
        `;
        this.applyMode();
    }

    bindEvents() {
        const on = (id, event, handler) => document.getElementById(id)?.addEventListener(event, handler);
        on('auth-mode', 'change', () => this.applyMode());
        on('save-security-settings', 'click', () => this.saveSettings());
        on('generate-api-key', 'click', () => this.generateApiKey());
        on('clear-api-key', 'click', () => this.clearApiKey());
        this.container.querySelectorAll('.password-toggle').forEach(button => {
            button.addEventListener('click', () => {
                const input = document.getElementById(button.dataset.target);
                const hidden = input.type === 'password';
                input.type = hidden ? 'text' : 'password';
                button.innerHTML = hidden ? EYE_SLASH_ICON_SVG : EYE_ICON_SVG;
            });
        });
    }

    applyMode() {
        const mode = document.getElementById('auth-mode').value;
        const show = (id, visible) => {
            const el = document.getElementById(id);
            if (el) el.style.display = visible ? '' : 'none';
        };
        show('public-url-group', mode !== 'api_only');
        show('https-only-group', mode !== 'api_only');
        show('oidc-section', mode === 'oidc');
        show('credentials-section', mode !== 'api_only');
        document.getElementById('mode-help').innerHTML = MODE_HELP[mode] || '';
    }

    validatePasswordComplexity(password) {
        const kinds = [/[A-Z]/, /[a-z]/, /\d/, /[!@#$%^&*]/].filter(re => re.test(password)).length;
        return password.length >= 8 && kinds >= 3;
    }

    formValues() {
        const value = id => document.getElementById(id)?.value.trim() ?? '';
        const mode = value('auth-mode');
        const data = {
            mode,
            username: value('username'),
            password: document.getElementById('password')?.value || '',
            current_password: document.getElementById('current-password')?.value || '',
            public_url: value('public-url'),
            https_only: !!document.getElementById('https-only')?.checked,
            oidc_metadata_url: value('oidc-metadata-url'),
            oidc_client_id: value('oidc-client-id'),
            oidc_client_secret: document.getElementById('oidc-client-secret')?.value || '',
            oidc_sub: value('oidc-sub'),
            oidc_email: value('oidc-email'),
            allow_local_login: !!document.getElementById('allow-local-login')?.checked
        };
        return data;
    }

    async saveSettings() {
        const data = this.formValues();
        const confirmPassword = document.getElementById('confirm-password').value;
        if (data.password) {
            if (data.password !== confirmPassword) return showToast('Passwords do not match', 'error');
            if (!this.validatePasswordComplexity(data.password)) {
                return showToast('Password needs 8 or more characters and 3 of: uppercase, lowercase, number, special (!@#$%^&*)', 'error');
            }
        }
        if (data.mode === 'oidc' && (!data.public_url || !data.oidc_metadata_url || !data.oidc_client_id || !(data.oidc_sub || data.oidc_email))) {
            return showToast('OpenID Connect needs the public URL, discovery URL, client ID, and an allowed user or email', 'error');
        }
        if (data.mode === 'api_only' && this.settings.mode !== 'api_only') {
            if (!confirm('API only mode has no browser login. This page signs out and cannot sign in again until the mode is changed in qbm_settings.yml. Continue?')) return;
        }
        await this.submit(data, 'Security settings saved. A new password, username, or mode signs out every browser.');
    }

    async submit(data, successMessage) {
        try {
            const response = await this.api.makeRequest('/security', 'PUT', data);
            if (!response.success) {
                showToast(response.message || 'Failed to save security settings', 'error');
                return null;
            }
            showToast(successMessage, 'success');
            await this.load();
            this.render();
            this.bindEvents();
            return response;
        } catch (error) {
            showToast(error.message || 'Failed to save security settings', 'error');
            return null;
        }
    }

    async generateApiKey() {
        if (!confirm('Generate a new API key? The old key stops working.')) return;
        try {
            const response = await this.api.makeRequest('/security', 'PUT', { generate_api_key: true });
            if (!response.success) return showToast(response.message || 'Failed to generate API key', 'error');
            const key = response.api_key;
            const content = `
                <div class="api-key-modal">
                    <p><strong>Copy this API key now.</strong> It is not shown again.</p>
                    <div class="api-key-display-modal">
                        <input type="text" id="modal-api-key" class="form-input" readonly value="${this.esc(key)}">
                        <button type="button" class="btn btn-icon" id="modal-copy-api-key" title="Copy to clipboard">Copy</button>
                    </div>
                </div>`;
            const copy = event => {
                if (event.target?.id === 'modal-copy-api-key') {
                    navigator.clipboard.writeText(key)
                        .then(() => showToast('API key copied to clipboard', 'success'))
                        .catch(() => showToast('Failed to copy API key', 'error'));
                }
            };
            document.addEventListener('click', copy);
            await showModal('New API Key Generated', content, { confirmText: 'Close', showCancel: false });
            document.removeEventListener('click', copy);
            await this.load();
            this.render();
            this.bindEvents();
        } catch (error) {
            showToast(error.message || 'Failed to generate API key', 'error');
        }
    }

    async clearApiKey() {
        if (!confirm('Clear the API key? API access with a key stops until you generate a new one.')) return;
        try {
            const response = await this.api.makeRequest('/security', 'PUT', { clear_api_key: true });
            if (!response.success) return showToast(response.message || 'Failed to clear API key', 'error');
            showToast('API key cleared', 'success');
            await this.load();
            this.render();
            this.bindEvents();
        } catch (error) {
            showToast(error.message || 'Failed to clear API key', 'error');
        }
    }
}
