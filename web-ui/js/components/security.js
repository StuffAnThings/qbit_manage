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
        this.linkedSub = '';
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
        const link = s.oidc_link || null;
        const mode = link ? 'oidc' : (s.mode || 'local');
        const publicUrl = link ? link.public_url : s.public_url;
        const metadataUrl = link ? link.oidc_metadata_url : s.oidc_metadata_url;
        const clientId = link ? link.oidc_client_id : s.oidc_client_id;
        this.linkedSub = link ? link.sub : (s.oidc_sub || '');
        const allowLocal = link && s.mode !== 'oidc' ? true : !!s.allow_local_login;
        const modes = [['local', 'Local login'], ['oidc', 'OpenID Connect']];
        if (mode === 'api_only') {
            modes.push(['api_only', 'API only']);
        }
        const linkedIdentity = link
            ? [link.preferred_username, link.email].filter(Boolean).join(' · ')
            : '';
        const linkBanner = link ? `
            <div class="alert alert-success security-link-banner" role="status">
                <strong>OpenID Connect verified!</strong>
                ${linkedIdentity ? `Signed in as <strong>${this.esc(linkedIdentity)}</strong>.` : 'Account verified.'}
                Click <strong>Save Settings</strong> below to apply.
            </div>` : '';
        const linkStatusText = link
            ? 'Ready to save linked account.'
            : (this.linkedSub ? 'An OpenID Connect account is linked.' : 'No account linked yet.');
        const linkBtnLabel = this.linkedSub ? 'Re-link OIDC account' : 'Sign in with OIDC to link account';
        const secretPlaceholder = link?.has_client_secret
            ? '&lt;linked secret ready&gt; (leave blank to use)'
            : (s.has_oidc_client_secret ? '&lt;redacted&gt; (leave blank to keep)' : 'Enter client secret');
        const redirectUri = this.computeRedirectUri(publicUrl);

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
                        <div class="security-input-row">
                            <input type="text" id="public-url" class="form-input" value="${this.esc(publicUrl)}" placeholder="https://qbm.example.com">
                            <button type="button" class="btn btn-secondary" id="use-current-url">Use current URL</button>
                        </div>
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
                        ${linkBanner}
                        <div class="form-group">
                            <label for="oidc-redirect-uri" class="form-label">Redirect URI (for your provider)</label>
                            <div class="security-input-row">
                                <input type="text" id="oidc-redirect-uri" class="form-input security-redirect-input" readonly value="${this.esc(redirectUri)}">
                                <button type="button" class="btn btn-secondary" id="copy-redirect-uri">Copy</button>
                            </div>
                            <div class="field-description" id="redirect-uri-help">Register this exact Redirect URI in your provider (for example Authentik).</div>
                        </div>
                        <div class="form-group">
                            <label for="oidc-metadata-url" class="form-label">Issuer / Discovery URL</label>
                            <div class="security-input-row">
                                <input type="text" id="oidc-metadata-url" class="form-input" value="${this.esc(metadataUrl)}" placeholder="https://auth.example.com/application/o/qbit-manage/">
                                <button type="button" class="btn btn-secondary" id="test-oidc-discovery">Test URL</button>
                            </div>
                            <div class="field-description" id="oidc-discovery-status">Paste the Authentik Issuer URL or full OpenID Configuration URL.</div>
                        </div>
                        <div class="form-group">
                            <label for="oidc-client-id" class="form-label">Client ID</label>
                            <input type="text" id="oidc-client-id" class="form-input" value="${this.esc(clientId)}">
                        </div>
                        <div class="form-group">
                            <label for="oidc-client-secret" class="form-label">Client secret</label>
                            <input type="password" id="oidc-client-secret" class="form-input" autocomplete="new-password" placeholder="${secretPlaceholder}">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Linked account</label>
                            <div class="security-oidc-actions">
                                <button type="button" class="btn btn-secondary" id="link-oidc-account">${linkBtnLabel}</button>
                                <span class="security-link-status ${this.linkedSub ? 'security-status-ok' : ''}">${linkStatusText}</span>
                            </div>
                            <div class="field-description">Signs in with your provider to verify settings and bind your admin account without looking up claim IDs.</div>
                        </div>
                        <div class="form-group">
                            <label class="checkbox-label">
                                <input type="checkbox" id="allow-local-login" ${allowLocal ? 'checked' : ''}>
                                <span class="checkmark"></span>
                                Break-glass: also allow the local password
                            </label>
                            <div class="field-description">Keep this on while testing OpenID Connect so you can still sign in locally if a setting is wrong.</div>
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
                        ${s.reauth_with_password ? `
                        <div class="form-group">
                            <label for="current-password" class="form-label">Current password</label>
                            <input type="password" id="current-password" class="form-input" autocomplete="current-password">
                            <div class="field-description">Needed for every change on this page. A change signs out every browser.</div>
                        </div>` : `
                        <div class="field-description" id="oidc-reauth-note">
                            There is no local password. Changes need a fresh OpenID Connect login: <a href="${this.api.baseUrl}/auth/oidc/login?reauth=1">sign in again</a>, then save within 5 minutes. A change signs out every browser.
                        </div>`}
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
        this.updateRedirectUri();
    }

    computeRedirectUri(publicUrlValue) {
        const raw = (publicUrlValue || '').trim().replace(/\/+$/, '');
        const base = (this.api.baseUrl || '').replace(/\/+$/, '');
        const origin = raw || window.location.origin;
        return `${origin}${base}/auth/oidc/callback`;
    }

    updateRedirectUri() {
        const input = document.getElementById('oidc-redirect-uri');
        const publicUrl = document.getElementById('public-url')?.value.trim() || '';
        if (input) {
            input.value = this.computeRedirectUri(publicUrl);
        }
        const help = document.getElementById('redirect-uri-help');
        if (help) {
            help.textContent = publicUrl
                ? 'Register this exact Redirect URI in your provider (for example Authentik).'
                : 'Showing your current browser origin as a preview. Set Public URL above first if using a reverse proxy.';
        }
    }

    bindEvents() {
        const on = (id, event, handler) => document.getElementById(id)?.addEventListener(event, handler);
        on('auth-mode', 'change', () => {
            const mode = document.getElementById('auth-mode')?.value;
            if (mode === 'oidc' && this.settings?.mode !== 'oidc') {
                const breakGlass = document.getElementById('allow-local-login');
                if (breakGlass && !breakGlass.checked) {
                    breakGlass.checked = true;
                }
            }
            this.applyMode();
        });
        on('public-url', 'input', () => this.updateRedirectUri());
        on('use-current-url', 'click', () => {
            const input = document.getElementById('public-url');
            if (input) {
                input.value = window.location.origin;
                this.updateRedirectUri();
            }
        });
        on('copy-redirect-uri', 'click', () => this.copyRedirectUri());
        on('test-oidc-discovery', 'click', () => this.testDiscovery());
        on('link-oidc-account', 'click', () => this.startOidcLink());
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

    async copyRedirectUri() {
        const input = document.getElementById('oidc-redirect-uri');
        const value = input?.value || '';
        if (!value) return;
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(value);
            } else {
                input.select();
                input.setSelectionRange(0, value.length);
                if (!document.execCommand('copy')) {
                    throw new Error('Copy command rejected');
                }
            }
            showToast('Redirect URI copied to clipboard', 'success');
        } catch (error) {
            showToast('Failed to copy Redirect URI', 'error');
        }
    }

    normalizeDiscoveryUrl(url) {
        const trimmed = (url || '').trim();
        if (!trimmed) return '';
        try {
            const parsed = new URL(trimmed);
            if (!parsed.pathname.includes('/.well-known/') && !parsed.pathname.endsWith('.json') && !parsed.search && !parsed.hash) {
                parsed.pathname = `${parsed.pathname.replace(/\/+$/, '')}/.well-known/openid-configuration`;
                return parsed.toString();
            }
        } catch (e) {}
        return trimmed;
    }

    async testDiscovery() {
        const btn = document.getElementById('test-oidc-discovery');
        const statusEl = document.getElementById('oidc-discovery-status');
        const input = document.getElementById('oidc-metadata-url');
        const url = this.normalizeDiscoveryUrl(input?.value);
        if (!url) {
            return showToast('Enter an Issuer / Discovery URL first', 'error');
        }
        if (input) input.value = url;
        const origText = btn?.textContent || 'Test URL';
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Testing...';
        }
        try {
            const response = await this.api.makeRequest('/security/oidc/test', 'POST', { oidc_metadata_url: url });
            if (statusEl) {
                statusEl.className = 'field-description security-status-ok';
                statusEl.textContent = response.message || 'Discovery document reachable.';
            }
            showToast(response.message || 'Discovery document reachable', 'success');
        } catch (error) {
            if (statusEl) {
                statusEl.className = 'field-description security-status-err';
                statusEl.textContent = error.message || 'Could not reach discovery URL.';
            }
            showToast(error.message || 'Could not reach discovery URL', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = origText;
            }
        }
    }

    async startOidcLink() {
        const values = this.formValues();
        const metadataInput = document.getElementById('oidc-metadata-url');
        if (metadataInput && values.oidc_metadata_url) {
            metadataInput.value = values.oidc_metadata_url;
        }
        if (!values.public_url || !values.oidc_metadata_url || !values.oidc_client_id) {
            return showToast('Enter Public URL, Issuer / Discovery URL, and Client ID first', 'error');
        }
        const btn = document.getElementById('link-oidc-account');
        const origText = btn?.textContent || 'Sign in with OIDC to link account';
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Connecting...';
        }
        try {
            const response = await this.api.makeRequest('/security/oidc/link', 'POST', {
                public_url: values.public_url,
                oidc_metadata_url: values.oidc_metadata_url,
                oidc_client_id: values.oidc_client_id,
                oidc_client_secret: values.oidc_client_secret
            });
            if (response?.success && response.authorize_url) {
                const target = new URL(response.authorize_url);
                if (target.protocol === 'https:' || target.protocol === 'http:') {
                    location.assign(target.toString());
                    return;
                }
            }
            showToast(response?.message || 'Failed to start OpenID Connect linking', 'error');
        } catch (error) {
            showToast(error.message || 'Failed to start OpenID Connect linking', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = origText;
            }
        }
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
        return {
            mode,
            username: value('username'),
            password: document.getElementById('password')?.value || '',
            current_password: document.getElementById('current-password')?.value || '',
            public_url: value('public-url'),
            https_only: !!document.getElementById('https-only')?.checked,
            oidc_metadata_url: this.normalizeDiscoveryUrl(value('oidc-metadata-url')),
            oidc_client_id: value('oidc-client-id'),
            oidc_client_secret: document.getElementById('oidc-client-secret')?.value || '',
            oidc_sub: this.linkedSub || '',
            allow_local_login: !!document.getElementById('allow-local-login')?.checked
        };
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
        if (
            data.mode === 'oidc' &&
            (!data.public_url || !data.oidc_metadata_url || !data.oidc_client_id || !(data.oidc_sub || this.settings?.oidc_claim_first_login))
        ) {
            return showToast('OpenID Connect needs Public URL, Issuer / Discovery URL, Client ID, and a linked account', 'error');
        }
        if (data.mode === 'api_only' && this.settings.mode !== 'api_only') {
            if (!confirm('API only mode has no browser login. This page signs out and cannot sign in again until the mode is changed in qbm_settings.yml. Continue?')) return;
        }
        await this.submit(data, 'Security settings saved. Every browser is signed out.');
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

    // The server needs the current password for every change; without a local password it needs a fresh OIDC login.
    askCurrentPassword() {
        if (!this.settings.reauth_with_password) return '';
        const typed = document.getElementById('current-password')?.value;
        return typed || window.prompt('Enter your current password to continue');
    }

    async generateApiKey() {
        if (!confirm('Generate a new API key? The old key stops working, and every browser is signed out.')) return;
        const current = this.askCurrentPassword();
        if (current === null) return;
        try {
            const response = await this.api.makeRequest('/security', 'PUT', { generate_api_key: true, current_password: current });
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
        const current = this.askCurrentPassword();
        if (current === null) return;
        try {
            const response = await this.api.makeRequest('/security', 'PUT', { clear_api_key: true, current_password: current });
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
