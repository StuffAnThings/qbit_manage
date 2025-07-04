/**
 * Header Component
 * Handles header-specific functionality including mobile menu toggle,
 * action buttons, and responsive behavior
 */

class HeaderComponent {
    constructor() {
        this.mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        this.headerActions = document.querySelector('.header-actions');
        this.sidebar = document.querySelector('.sidebar');
        this.isMobileMenuOpen = false;
        this.originalButtonTexts = new Map(); // Store original button texts

        this.init();
    }

    init() {
        this.bindEvents();
        this.handleResize();

        // Listen for window resize to handle responsive behavior
        window.addEventListener('resize', () => this.handleResize());
    }

    bindEvents() {
        // Mobile menu toggle
        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.addEventListener('click', () => this.toggleMobileMenu());
        }

        // Header action buttons
        this.bindActionButtons();
    }

    bindActionButtons() {
        // Save button
        const saveBtn = document.getElementById('save-config-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.handleSave());
        }

        // Validate button
        const validateBtn = document.getElementById('validate-config-btn');
        if (validateBtn) {
            validateBtn.addEventListener('click', () => this.handleValidate());
        }

        // Backup button
        const backupBtn = document.getElementById('backup-config-btn');
        if (backupBtn) {
            backupBtn.addEventListener('click', () => this.handleBackup());
        }

        // Help button
        const helpBtn = document.getElementById('help-btn');
        if (helpBtn) {
            helpBtn.addEventListener('click', () => this.handleHelp());
        }

        // Undo/Redo buttons are handled by history manager
    }

    toggleMobileMenu() {
        this.isMobileMenuOpen = !this.isMobileMenuOpen;

        if (this.sidebar) {
            this.sidebar.classList.toggle('mobile-open', this.isMobileMenuOpen);
        }

        // Update mobile menu toggle icon
        const icon = this.mobileMenuToggle.querySelector('.material-icons');
        if (icon) {
            icon.textContent = this.isMobileMenuOpen ? 'close' : 'menu';
        }

        // Update aria-expanded attribute
        this.mobileMenuToggle.setAttribute('aria-expanded', this.isMobileMenuOpen.toString());
    }

    handleResize() {
        const isMobile = window.innerWidth < 768;

        if (this.mobileMenuToggle) {
            this.mobileMenuToggle.style.display = isMobile ? 'flex' : 'none';
        }

        // Close mobile menu on desktop
        if (!isMobile && this.isMobileMenuOpen) {
            this.toggleMobileMenu();
        }

        // Adjust header actions visibility on small screens
        this.adjustHeaderActions(window.innerWidth);
    }

    adjustHeaderActions(width) {
        if (!this.headerActions) return;

        const buttons = this.headerActions.querySelectorAll('.btn:not(.btn-icon)');

        if (width < 640) {
            // On very small screens, hide button text and show only icons
            buttons.forEach(btn => {
                // Store original text if not already stored
                if (!this.originalButtonTexts.has(btn)) {
                    const textNodes = Array.from(btn.childNodes).filter(node =>
                        node.nodeType === Node.TEXT_NODE && node.textContent.trim()
                    );
                    if (textNodes.length > 0) {
                        this.originalButtonTexts.set(btn, textNodes[0].textContent.trim());
                    }
                }

                // Hide button text
                const textNodes = Array.from(btn.childNodes).filter(node =>
                    node.nodeType === Node.TEXT_NODE
                );
                textNodes.forEach(textNode => {
                    textNode.textContent = '';
                });
                btn.classList.add('btn-icon-only');
            });
        } else {
            // Restore button text on larger screens
            buttons.forEach(btn => {
                btn.classList.remove('btn-icon-only');

                // Restore original text
                if (this.originalButtonTexts.has(btn)) {
                    const originalText = this.originalButtonTexts.get(btn);
                    // Find the last text node or create one if needed
                    const textNodes = Array.from(btn.childNodes).filter(node =>
                        node.nodeType === Node.TEXT_NODE
                    );

                    if (textNodes.length > 0) {
                        // Use the last text node (typically after the icon)
                        textNodes[textNodes.length - 1].textContent = originalText;
                    } else {
                        // Create a new text node if none exists
                        btn.appendChild(document.createTextNode(originalText));
                    }
                }
            });
        }
    }

    handleSave() {
        // This will be handled by the main app's save functionality
        // Just emit a custom event that the main app can listen to
        window.dispatchEvent(new CustomEvent('header:save'));
    }

    handleValidate() {
        // Emit validation event
        window.dispatchEvent(new CustomEvent('header:validate'));
    }

    handleBackup() {
        // Emit backup event
        window.dispatchEvent(new CustomEvent('header:backup'));
    }

    handleHelp() {
        // Emit help event
        window.dispatchEvent(new CustomEvent('header:help'));
    }

    // Public methods for external control
    updateSaveButtonState(enabled) {
        const saveBtn = document.getElementById('save-config-btn');
        if (saveBtn) {
            saveBtn.disabled = !enabled;
        }
    }

    updateHistoryButtonStates(canUndo, canRedo) {
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');

        if (undoBtn) undoBtn.disabled = !canUndo;
        if (redoBtn) redoBtn.disabled = !canRedo;
    }

    showLoadingState(button) {
        if (!button) return;

        const icon = button.querySelector('.material-icons');
        if (icon) {
            icon.textContent = 'hourglass_empty';
            icon.classList.add('rotating');
        }
        button.disabled = true;
    }

    hideLoadingState(button, originalIcon) {
        if (!button) return;

        const icon = button.querySelector('.material-icons');
        if (icon) {
            icon.textContent = originalIcon;
            icon.classList.remove('rotating');
        }
        button.disabled = false;
    }
}

// Initialize header component when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.headerComponent = new HeaderComponent();
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = HeaderComponent;
}
