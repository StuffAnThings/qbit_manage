/**
 * Toast Utility Module
 * Manages the display of toast notifications.
 */

import { get, show, hide } from './dom.js';
import { CLOSE_ICON_SVG } from './icons.js';

const TOAST_CONTAINER_ID = 'toast-container';

/**
 * Displays a toast notification.
 * @param {string} message - The message to display in the toast.
 * @param {'success'|'error'|'warning'|'info'} [type='info'] - The type of toast (for styling).
 * @param {number} [duration=5000] - How long the toast should be visible in milliseconds.
 */
export function showToast(message, type = 'info', duration = 5000) {
    const container = get(TOAST_CONTAINER_ID);
    if (!container) {
        console.warn('Toast container not found. Cannot display toast message.');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ',
        undo: '↶',
        redo: '↷'
    };

    // Build static structure with innerHTML, then set message via textContent
    toast.innerHTML = `
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-content">
                <div class="toast-message"></div>
            </div>
            <button class="btn btn-icon btn-close-icon toast-close">
                ${CLOSE_ICON_SVG}
            </button>
        `;
    // Insert message safely without relying on HTML escaping
    const msgNode = toast.querySelector('.toast-message');
    if (msgNode) {
        msgNode.textContent = message == null ? '' : String(message);
    }

    container.appendChild(toast);

    // Show toast (add 'show' class to trigger transition)
    setTimeout(() => {
        toast.classList.add('show');
    }, 100);

    // Auto-hide toast
    const hideToast = () => {
        toast.classList.remove('show');
        // Remove from DOM after transition
        toast.addEventListener('transitionend', () => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, { once: true });
    };

    setTimeout(hideToast, duration);

    // Close button event
    const closeButton = toast.querySelector('.toast-close');
    if (closeButton) {
        closeButton.addEventListener('click', hideToast);
    }
}
