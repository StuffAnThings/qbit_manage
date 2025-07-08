/**
 * Modal Utility Module
 * Manages the display and interaction of modal dialogs.
 */

import { get, query, hide, show } from './dom.js';

const MODAL_OVERLAY_ID = 'modal-overlay';
const MODAL_TITLE_ID = 'modal-title';
const MODAL_CONTENT_ID = 'modal-content';
const MODAL_CONFIRM_BTN_ID = 'modal-confirm-btn';
const MODAL_CANCEL_BTN_ID = 'modal-cancel-btn';
const MODAL_CLOSE_BTN_ID = 'modal-close-btn';

let resolvePromise;

/**
 * Initializes the modal by attaching event listeners.
 * This should be called once when the application starts.
 */
export function initModal() {
    const modalOverlay = get(MODAL_OVERLAY_ID);
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                hideModal(false); // Pass false to indicate cancellation
            }
        });
    }

    const modalCloseBtn = get(MODAL_CLOSE_BTN_ID);
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', () => hideModal(false));
    }

    const modalCancelBtn = get(MODAL_CANCEL_BTN_ID);
    if (modalCancelBtn) {
        modalCancelBtn.addEventListener('click', () => hideModal(false));
    }

    const modalConfirmBtn = get(MODAL_CONFIRM_BTN_ID);
    if (modalConfirmBtn) {
        modalConfirmBtn.addEventListener('click', () => hideModal(true));
    }
}

/**
 * Displays a modal dialog.
 * @param {string} title - The title of the modal.
 * @param {string} content - The HTML content to display inside the modal.
 * @param {object} [options={}] - Options for the modal.
 * @param {string} [options.confirmText='OK'] - Text for the confirm button.
 * @param {string} [options.cancelText='Cancel'] - Text for the cancel button.
 * @param {boolean} [options.showCancel=true] - Whether to show the cancel button.
 * @returns {Promise<boolean>} A promise that resolves to true if confirmed, false if cancelled.
 */
export function showModal(title, content, options = {}) {
    const { confirmText = 'OK', cancelText = 'Cancel', showCancel = true } = options;

    const modalOverlay = get(MODAL_OVERLAY_ID);
    const modalTitle = get(MODAL_TITLE_ID);
    const modalContent = get(MODAL_CONTENT_ID);
    const confirmBtn = get(MODAL_CONFIRM_BTN_ID);
    const cancelBtn = get(MODAL_CANCEL_BTN_ID);

    if (!modalOverlay || !modalTitle || !modalContent || !confirmBtn || !cancelBtn) {
        console.error('Modal elements not found. Ensure index.html contains the modal structure.');
        return Promise.resolve(false);
    }

    modalTitle.textContent = title;
    modalContent.innerHTML = content;
    confirmBtn.textContent = confirmText;
    cancelBtn.textContent = cancelText;

    if (showCancel) {
        show(cancelBtn);
    } else {
        hide(cancelBtn);
    }

    show(modalOverlay);

    return new Promise((resolve) => {
        resolvePromise = resolve;
    });
}

/**
 * Hides the modal dialog.
 * @param {boolean} [confirmed=false] - Whether the modal was confirmed (true) or cancelled (false).
 */
export function hideModal(confirmed = false) {
    const modalOverlay = get(MODAL_OVERLAY_ID);
    if (modalOverlay) {
        hide(modalOverlay);
    }
    if (resolvePromise) {
        resolvePromise(confirmed);
        resolvePromise = null; // Clear the promise resolver
    }
}
