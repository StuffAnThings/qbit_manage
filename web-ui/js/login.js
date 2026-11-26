/**
 * Login page UI enhancements (theme switching and password visibility toggle).
 * Reuses ThemeManager and SVG icons from the shared Web UI utilities.
 */

import './utils/theme-manager.js';
import { EYE_ICON_SVG, EYE_SLASH_ICON_SVG } from './utils/icons.js';

const OIDC_ICON_SVG =
    '<svg class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
    '<path d="M11 7L9.6 8.4l2.6 2.6H2v2h10.2l-2.6 2.6L11 17l5-5-5-5zm9 12h-8v2h8c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-8v2h8v14z"/></svg>';

const oidcIcon = document.getElementById('oidc-login-icon');
if (oidcIcon) {
    oidcIcon.innerHTML = OIDC_ICON_SVG;
}

const pwToggle = document.getElementById('password-toggle');
const pwInput = document.getElementById('login-password');
if (pwToggle && pwInput) {
    pwToggle.innerHTML = EYE_ICON_SVG;
    pwToggle.addEventListener('click', () => {
        const reveal = pwInput.type === 'password';
        pwInput.type = reveal ? 'text' : 'password';
        pwToggle.innerHTML = reveal ? EYE_SLASH_ICON_SVG : EYE_ICON_SVG;
        pwToggle.setAttribute('aria-pressed', reveal ? 'true' : 'false');
        pwToggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
    });
}
