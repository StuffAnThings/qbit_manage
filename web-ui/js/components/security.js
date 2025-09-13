/**
 * Security Component for qBit Manage Web UI
 * Handles authentication settings and user management
 */

import { API } from '../api.js';
import { showToast } from '../utils/toast.js';
import { showModal } from '../utils/modal.js';
import { EYE_ICON_SVG, EYE_SLASH_ICON_SVG } from '../utils/icons.js';

export class SecurityComponent {
    constructor(containerId, apiInstance = null) {
        this.container = document.getElementById(containerId);
        this.api = apiInstance || new API();
        this.currentSettings = null;
        this.hasApiKey = false; // Track whether we have an API key without storing the key itself
    }

    async init() {
        try {
            await this.loadSecuritySettings();
            this.render();
            this.bindEvents();
        } catch (error) {
            showToast('Failed to load security settings', 'error');
        }
    }

    async loadSecuritySettings() {
        try {
            const response = await this.api.makeRequest('/security', 'GET');
            this.currentSettings = response;

            // Also fetch security status to determine if API key exists
            const statusResponse = await this.api.makeRequest('/security/status', 'GET');
            this.hasApiKey = statusResponse.has_api_key;

            // Initialize actualApiKey for copy functionality (empty for security)
            this.actualApiKey = '';
        } catch (error) {
            // Use default settings if loading fails
            this.currentSettings = {
                enabled: false,
                method: 'none',
                bypass_auth_for_local: false,
                trusted_proxies: [],
                username: '',
                password_hash: '',
                api_key: ''
            };
            this.hasApiKey = false;
            this.actualApiKey = '';
        }
    }

    maskApiKey(apiKey) {
        // Completely mask the API key for display - show only dots
        if (!apiKey) {
            return '';
        }
        return '•'.repeat(Math.max(32, apiKey.length));
    }

    render() {
        this.container.innerHTML = `
            <div class="security-settings">
                <div class="section-header">
                    <h2>Security Settings</h2>
                    <p class="section-description">
                        Configure authentication for the qBit Manage web interface.
                        Choose between no authentication or basic HTTP authentication.
                    </p>
                </div>

                <div class="settings-form">

                    <!-- Authentication Method -->
                    <div class="form-group">
                        <label for="auth-method" class="form-label">Authentication Method</label>
                        <select id="auth-method" class="form-select">
                            <option value="none" ${this.currentSettings.method === 'none' ? 'selected' : ''}>None (Disabled)</option>
                            <option value="basic" ${this.currentSettings.method === 'basic' ? 'selected' : ''}>Basic (HTTP Authentication)</option>
                            <option value="api_only" ${this.currentSettings.method === 'api_only' ? 'selected' : ''}>API Only</option>
                        </select>
                        <div class="field-description">
                            <strong>None:</strong> No authentication required<br>
                            <strong>Basic:</strong> Browser popup for username/password authentication<br>
                            <strong>API Only:</strong> No auth for web UI, API key required for API requests
                        </div>
                    </div>

                    <!-- Allow Local Addresses -->
                    <div class="form-group" id="local-addresses-group" style="${this.currentSettings.method === 'none' ? 'display: none;' : ''}">
                        <label class="checkbox-label">
                            <input type="checkbox" id="allow-local" ${this.currentSettings.bypass_auth_for_local ? 'checked' : ''}>
                            <span class="checkmark"></span>
                            Allow local/private IPs without authentication
                        </label>
                        <div class="field-description">
                            When checked, requests from localhost and RFC 1918 private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) won't require authentication
                        </div>
                    </div>

                    <!-- Trusted Proxies -->
                    <div class="form-group" id="trusted-proxies-group" style="${this.currentSettings.method === 'none' ? 'display: none;' : ''}">
                        <label for="trusted-proxies" class="form-label">Trusted Proxy IPs/Subnets</label>
                        <textarea id="trusted-proxies" class="form-textarea" rows="3" placeholder="One IP/subnet per line (e.g., 127.0.0.1, 172.17.0.0/16)">${(this.currentSettings.trusted_proxies || []).join('\n')}</textarea>
                        <div class="field-description">
                            List of trusted proxy IPs or subnets (one per line). When set, the app will trust X-Forwarded-For headers from these proxies to determine the real client IP for local bypass decisions. Leave empty for direct connections.<br>
                            <strong>Format:</strong> IPv4 addresses (e.g., 192.168.1.1) or CIDR notation (e.g., 192.168.1.0/24, 10.0.0.0/8)
                        </div>
                    </div>

                    <!-- Credentials Section -->
                    <div id="credentials-section" style="${this.currentSettings.method !== 'none' ? '' : 'display: none;'}">
                        <h3>Credentials</h3>

                        <!-- Username -->
                        <div class="form-group">
                            <label for="username" class="form-label">Username</label>
                            <input type="text" id="username" class="form-input" value="${this.currentSettings.username || ''}" placeholder="Enter username">
                            <div class="field-description">Username for authentication</div>
                        </div>

                        <!-- Password -->
                        <div class="form-group">
                            <label for="password" class="form-label">Password</label>
                            <div class="password-input-group">
                                <input type="password" id="password" class="form-input" placeholder="Enter new password">
                                <button type="button" class="btn btn-icon password-toggle" data-target="password">
                                    ${EYE_ICON_SVG}
                                </button>
                            </div>
                            <div class="field-description">Leave blank to keep current password</div>
                        </div>

                        <!-- Confirm Password -->
                        <div class="form-group">
                            <label for="confirm-password" class="form-label">Confirm Password</label>
                            <div class="password-input-group">
                                <input type="password" id="confirm-password" class="form-input" placeholder="Confirm new password">
                                <button type="button" class="btn btn-icon password-toggle" data-target="confirm-password">
                                    ${EYE_ICON_SVG}
                                </button>
                            </div>
                            <div class="field-description">Must match the password above</div>
                        </div>
                    </div>

                    <!-- API Key Section -->
                    <div id="api-key-section">
                        <h3>API Key</h3>
                        <div class="form-group">
                            <div class="api-key-input-group">
                                <button type="button" class="btn btn-secondary" id="generate-api-key">
                                    ${this.hasApiKey ? 'Generate New Key' : 'Generate Key'}
                                </button>
                                ${this.hasApiKey ? `
                                <button type="button" class="btn btn-outline" id="clear-api-key">
                                    Clear Key
                                </button>
                                ` : ''}
                            </div>
                            <div class="field-description">
                                API key for programmatic access. Click "Generate Key" to create a new key. The key will be displayed in a popup and won't be shown again.
                            </div>
                        </div>
                    </div>

                    <!-- Save Button -->
                    <div class="form-actions">
                        <button type="button" class="btn btn-primary" id="save-security-settings">
                            Save Settings
                        </button>
                    </div>

                </div>
            </div>
        `;
    }

    bindEvents() {
        // Cache DOM elements for better performance
        this.authMethod = document.getElementById('auth-method');
        this.localAddressesGroup = document.getElementById('local-addresses-group');
        this.trustedProxiesGroup = document.getElementById('trusted-proxies-group');
        this.credentialsSection = document.getElementById('credentials-section');
        this.generateApiKeyBtn = document.getElementById('generate-api-key');
        this.clearApiKeyBtn = document.getElementById('clear-api-key');
        this.saveBtn = document.getElementById('save-security-settings');

        // Handle authentication method change
        if (this.authMethod) {
            this.authMethod.addEventListener('change', () => {
                this.handleMethodChange(this.authMethod.value);
            });
        }

        // Handle password visibility toggles
        const passwordToggles = document.querySelectorAll('.password-toggle');
        passwordToggles.forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                const targetId = toggle.dataset.target;
                this.togglePasswordVisibility(targetId);
            });
        });

        // Handle generate API key
        if (this.generateApiKeyBtn) {
            this.generateApiKeyBtn.addEventListener('click', () => {
                this.generateApiKey();
            });
        }

        // Handle clear API key
        if (this.clearApiKeyBtn) {
            this.clearApiKeyBtn.addEventListener('click', () => {
                this.clearApiKey();
            });
        }

        // Handle save settings
        if (this.saveBtn) {
            this.saveBtn.addEventListener('click', () => {
                this.saveSettings();
            });
        }
    }


    handleMethodChange(method) {
        const isNone = method === 'none';
        const isApiOnly = method === 'api_only';
        if (this.localAddressesGroup) {
            this.localAddressesGroup.style.display = isNone ? 'none' : '';
        }
        if (this.trustedProxiesGroup) {
            this.trustedProxiesGroup.style.display = isNone ? 'none' : '';
        }
        if (this.credentialsSection) {
            this.credentialsSection.style.display = (isNone || isApiOnly) ? 'none' : '';
        }
    }

    togglePasswordVisibility(targetId) {
        const input = document.getElementById(targetId);
        const button = document.querySelector(`[data-target="${targetId}"]`);

        if (!input || !button) {
            console.error('Password input or toggle button not found:', targetId);
            return;
        }

        // Standard password field behavior (no special handling for API key anymore)
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        button.innerHTML = isPassword ? EYE_SLASH_ICON_SVG : EYE_ICON_SVG;
    }

    // Removed maskApiKey and toggleApiKeyVisibility methods - API key is always shown in full

    async generateApiKey() {
        if (!confirm('Are you sure you want to generate a new API key? The old key will no longer work.')) {
            return;
        }

        try {
            // Get current form values to send complete request
            const method = document.getElementById('auth-method').value;
            const allowLocalCheckbox = document.getElementById('allow-local');
            const allowLocalIps = allowLocalCheckbox && allowLocalCheckbox.checked;
            const trustedProxiesTextarea = document.getElementById('trusted-proxies');
            const trustedProxies = trustedProxiesTextarea ? trustedProxiesTextarea.value.split('\n').map(line => line.trim()).filter(line => line) : [];
            const username = document.getElementById('username')?.value.trim() || '';
            const password = document.getElementById('password')?.value || '';

            const requestData = {
                enabled: method !== 'none',
                method: method,
                bypass_auth_for_local: allowLocalIps,
                trusted_proxies: trustedProxies,
                username: username,
                password: password,
                generate_api_key: true
            };

            const response = await this.api.makeRequest('/security', 'PUT', requestData);

            if (response.success) {
                // Store the newly generated API key temporarily for the modal
                const newApiKey = response.api_key;

                // Show modal with the API key
                const modalContent = `
                    <div class="api-key-modal">
                        <p><strong>Important:</strong> Copy this API key now. It will not be shown again.</p>
                        <div class="api-key-display-modal">
                            <input type="text" id="modal-api-key" class="form-input" readonly value="${newApiKey}">
                            <button type="button" class="btn btn-icon" id="modal-copy-api-key" title="Copy to clipboard">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
                                </svg>
                            </button>
                        </div>
                        <p class="modal-warning">This key provides full access to the qBit Manage API. Keep it secure!</p>
                    </div>
                `;

                // Add copy functionality using event delegation before showing modal
                const handleCopyClick = (event) => {
                    if (event.target && event.target.id === 'modal-copy-api-key') {
                        navigator.clipboard.writeText(newApiKey)
                            .then(() => showToast('API key copied to clipboard', 'success'))
                            .catch(() => showToast('Failed to copy API key', 'error'));
                    }
                };

                // Attach event listener to document for the copy button
                document.addEventListener('click', handleCopyClick);

                // Show the modal
                const modalResult = await showModal('New API Key Generated', modalContent, {
                    confirmText: 'Close',
                    showCancel: false
                });

                // Clean up event listener after modal is closed
                document.removeEventListener('click', handleCopyClick);

                // Update the component state to reflect that we now have a key
                this.hasApiKey = true;

                // Re-render to update button states
                this.render();
                this.bindEvents();

                showToast('New API key generated successfully', 'success');
            } else {
                showToast(response.message || 'Failed to generate API key', 'error');
            }
        } catch (error) {
            console.error('Failed to generate API key:', error);
            showToast('Failed to generate API key', 'error');
        }
    }

    async clearApiKey() {
        if (!confirm('Are you sure you want to clear the API key? This will disable API access until a new key is generated.')) {
            return;
        }

        try {
            // Get current form values to send complete request
            const method = document.getElementById('auth-method').value;
            const allowLocalCheckbox = document.getElementById('allow-local');
            const allowLocalIps = allowLocalCheckbox && allowLocalCheckbox.checked;
            const trustedProxiesTextarea = document.getElementById('trusted-proxies');
            const trustedProxies = trustedProxiesTextarea ? trustedProxiesTextarea.value.split('\n').map(line => line.trim()).filter(line => line) : [];
            const username = document.getElementById('username')?.value.trim() || '';
            const password = document.getElementById('password')?.value || '';

            const requestData = {
                enabled: method !== 'none',
                method: method,
                bypass_auth_for_local: allowLocalIps,
                trusted_proxies: trustedProxies,
                username: username,
                password: password,
                clear_api_key: true
            };

            const response = await this.api.makeRequest('/security', 'PUT', requestData);

            if (response.success) {
                // Clear the API key state
                this.hasApiKey = false;

                // Re-render to update button states
                this.render();
                this.bindEvents();

                showToast('API key cleared successfully', 'success');
            } else {
                showToast(response.message || 'Failed to clear API key', 'error');
            }
        } catch (error) {
            console.error('Failed to clear API key:', error);
            showToast('Failed to clear API key', 'error');
        }
    }


    validatePasswordComplexity(password) {
        const minLength = 8;
        const hasUpper = /[A-Z]/.test(password);
        const hasLower = /[a-z]/.test(password);
        const hasNumber = /\d/.test(password);
        const hasSpecial = /[!@#$%^&*]/.test(password);

        // Count how many character types are present
        const typeCount = [hasUpper, hasLower, hasNumber, hasSpecial].filter(Boolean).length;

        return password.length >= minLength && typeCount >= 3;
    }

    validateIpOrCidr(ip) {
        // Check if it's a valid IPv4 address
        const ipv4Regex = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
        const match = ip.match(ipv4Regex);

        if (match) {
            // Check if it's a valid IP address (each octet 0-255)
            for (let i = 1; i <= 4; i++) {
                const octet = parseInt(match[i], 10);
                if (octet < 0 || octet > 255) {
                    return false;
                }
            }
            return true;
        }

        // Check if it's a valid CIDR notation
        const cidrRegex = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\/(\d{1,2})$/;
        const cidrMatch = ip.match(cidrRegex);

        if (cidrMatch) {
            // Validate IP part
            for (let i = 1; i <= 4; i++) {
                const octet = parseInt(cidrMatch[i], 10);
                if (octet < 0 || octet > 255) {
                    return false;
                }
            }
            // Validate subnet mask (0-32)
            const mask = parseInt(cidrMatch[5], 10);
            return mask >= 0 && mask <= 32;
        }

        return false;
    }

    validateTrustedProxies(proxies) {
        if (!proxies || proxies.length === 0) {
            return { valid: true }; // Empty is valid
        }

        const invalidEntries = [];
        const duplicates = [];

        for (let i = 0; i < proxies.length; i++) {
            const proxy = proxies[i].trim();

            if (!proxy) continue; // Skip empty lines

            // Check format
            if (!this.validateIpOrCidr(proxy)) {
                invalidEntries.push(proxy);
            }

            // Check for duplicates
            if (proxies.indexOf(proxy) !== i) {
                if (!duplicates.includes(proxy)) {
                    duplicates.push(proxy);
                }
            }
        }

        if (invalidEntries.length > 0 || duplicates.length > 0) {
            return {
                valid: false,
                invalidEntries,
                duplicates
            };
        }

        return { valid: true };
    }

    async saveSettings() {
        try {
            const method = document.getElementById('auth-method').value;
            const allowLocalCheckbox = document.getElementById('allow-local');
            const allowLocalIps = allowLocalCheckbox && allowLocalCheckbox.checked;
            const trustedProxiesTextarea = document.getElementById('trusted-proxies');
            const trustedProxies = trustedProxiesTextarea ? trustedProxiesTextarea.value.split('\n').map(line => line.trim()).filter(line => line) : [];
            const username = document.getElementById('username')?.value.trim() || '';
            const password = document.getElementById('password')?.value || '';
            const confirmPassword = document.getElementById('confirm-password')?.value || '';

            // Validate trusted proxies
            const proxyValidation = this.validateTrustedProxies(trustedProxies);
            if (!proxyValidation.valid) {
                let errorMessage = 'Invalid trusted proxy entries:';

                if (proxyValidation.invalidEntries.length > 0) {
                    errorMessage += `\n• Invalid format: ${proxyValidation.invalidEntries.join(', ')}`;
                    errorMessage += '\n  (Use IPv4 addresses like 192.168.1.1 or CIDR notation like 192.168.1.0/24)';
                }

                if (proxyValidation.duplicates.length > 0) {
                    errorMessage += `\n• Duplicates found: ${proxyValidation.duplicates.join(', ')}`;
                }

                showToast(errorMessage, 'error');
                return;
            }

            // Validation
            if (method !== 'none' && method !== 'api_only') {
                if (!username) {
                    showToast('Username is required', 'error');
                    return;
                }

                // For basic authentication, password is required
                if (method === 'basic') {
                    const hasExistingPassword = this.currentSettings.password_hash && this.currentSettings.password_hash !== '';
                    const hasNewPassword = password && password.trim() !== '';

                    if (!hasExistingPassword && !hasNewPassword) {
                        showToast('Password is required for basic authentication', 'error');
                        return;
                    }
                }

                if (password && password !== confirmPassword) {
                    showToast('Passwords do not match', 'error');
                    return;
                }

                // Password complexity validation
                if (password && !this.validatePasswordComplexity(password)) {
                    showToast('Password must be at least 8 characters with at least 3 of: uppercase, lowercase, number, special character', 'error');
                    return;
                }
            }

            // Prepare request data
            const requestData = {
                enabled: method !== 'none',
                method: method,
                bypass_auth_for_local: allowLocalIps,
                trusted_proxies: trustedProxies,
                username: username,
                password: password,
                generate_api_key: false
            };

            // Make API request
            const response = await this.api.makeRequest('/security', 'PUT', requestData);

            if (response.success) {
                showToast('Security settings saved successfully', 'success');

                // Update current settings
                this.currentSettings = {
                    enabled: method !== 'none',
                    method: method,
                    bypass_auth_for_local: allowLocalIps,
                    trusted_proxies: trustedProxies,
                    username: username,
                    password_hash: password ? '***' : this.currentSettings.password_hash,
                    api_key: this.currentSettings.api_key
                };

                // Clear password fields
                const passwordField = document.getElementById('password');
                const confirmPasswordField = document.getElementById('confirm-password');
                if (passwordField) passwordField.value = '';
                if (confirmPasswordField) confirmPasswordField.value = '';
            } else {
                showToast(response.message || 'Failed to save settings', 'error');
            }

        } catch (error) {
            console.error('Failed to save security settings:', error);
            showToast('Failed to save security settings', 'error');
        }
    }

    async resetSettings() {
        if (confirm('Are you sure you want to reset security settings? This will disable authentication.')) {
            try {
                await this.loadSecuritySettings();
                this.render();
                this.bindEvents();
                showToast('Security settings reset', 'info');
            } catch (error) {
                console.error('Failed to reset settings:', error);
                showToast('Failed to reset settings', 'error');
            }
        }
    }
}
