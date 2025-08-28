/**
 * qBit Manage Web UI - Command Panel Component
 * Handles command execution and monitoring
 */

import { API } from '../api.js';
import { showToast } from '../utils/toast.js';
import { CLOSE_ICON_SVG } from '../utils/icons.js';

class CommandPanel {
    constructor(options = {}) {
        this.container = options.container;
        this.drawerContainer = options.drawerContainer;
        this.onCommandExecute = options.onCommandExecute || (() => {});

        this.api = new API();
        this.isVisible = false;
        this.runCommandsModal = null; // To store the reference to the run commands modal

        this.init();
    }

    init() {
        this.render();
        this.bindEvents();
        this.setupDrawer();
    }

    setupDrawer() {
        // Create the drawer container if it doesn't exist
        if (!this.drawerContainer) {
            this.drawerContainer = document.createElement('div');
            this.drawerContainer.className = 'command-panel-drawer hidden';
            document.body.appendChild(this.drawerContainer);
        }

        // Move the command panel content to the drawer
        this.renderDrawer();
        this.bindDrawerEvents();
    }

    render() {
        if (!this.container) return;

        // Render the toggle button in the footer
        this.container.innerHTML = `
            <div class="command-panel-toggle">
                <button type="button" class="btn btn-secondary command-panel-toggle-btn" id="toggle-command-panel-btn">
                    <svg class="icon" viewBox="0 0 24 24">
                        <path d="M7.41 15.41L12 10.83l4.59 4.58L18 14l-6-6-6 6z"/>
                    </svg>
                    Commands
                </button>
            </div>
        `;
    }

    renderDrawer() {
        if (!this.drawerContainer) return;

        this.drawerContainer.innerHTML = `
            <div class="command-panel-header">
                <h3>Command Execution</h3>
                <div class="command-panel-actions">
                    <button type="button" class="btn btn-primary" id="run-commands-btn">
                        ▶️ Run Commands
                    </button>
                    <button type="button" class="btn btn-icon btn-close-icon" id="close-command-panel-btn">
                        ${CLOSE_ICON_SVG}
                    </button>
                </div>
            </div>

            <div class="command-panel-content">
                <!-- Quick Actions -->
                <div class="quick-actions">
                    <div class="quick-actions-header">
                        <h4>Quick Actions</h4>
                        <div class="dry-run-toggle">
                            <label class="checkbox-label">
                                <input type="checkbox" id="dry-run-checkbox">
                                <span class="checkmark"></span>
                                Dry Run
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" id="quick-skip-cleanup-checkbox">
                                <span class="checkmark"></span>
                                Skip Cleanup
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" id="quick-skip-qb-version-check-checkbox">
                                <span class="checkmark"></span>
                                Skip qB Version Check
                            </label>
                            <div class="form-group form-group-inline">
                                <label for="quick-log-level-select" class="form-label">Log Level</label>
                                <select id="quick-log-level-select" class="form-select">
                                    <option value="">Default</option>
                                    <option value="INFO">Info</option>
                                    <option value="DEBUG">Debug</option>
                                    <option value="TRACE">Trace</option>
                                </select>
                            </div>
                        </div>
                    </div>
                    <div class="quick-action-buttons">
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="recheck">
                            🔄 Recheck
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="cat_update">
                            📁 Update Categories
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="tag_update">
                            🏷️ Update Tags
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="rem_unregistered">
                            🗑️ Remove Unregistered
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="tag_tracker_error">
                            ⚠️ Tag Tracker Errors
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="tag_nohardlinks">
                            🔗 Tag No Hard Links
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="share_limits">
                            ⚖️ Apply Share Limits
                        </button>
                        <button type="button" class="btn btn-outline quick-action-btn"
                                data-command="rem_orphaned">
                            🧹 Remove Orphaned
                        </button>
                    </div>
                </div>

            </div>
        `;

        // Load saved quick action values after rendering
        this.loadQuickActionValues();
    }

    bindEvents() {
        if (!this.container) return;

        // Toggle button in the footer
        const toggleBtn = this.container.querySelector('#toggle-command-panel-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                this.toggle();
            });
        }
    }

    bindDrawerEvents() {
        if (!this.drawerContainer) return;

        // Close button
        const closeBtn = this.drawerContainer.querySelector('#close-command-panel-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                this.hide();
            });
        }

        // Quick action buttons and other controls
        this.drawerContainer.addEventListener('click', (e) => {
            if (e.target.classList.contains('quick-action-btn')) {
                const command = e.target.dataset.command;
                this.executeQuickCommand(command);
            } else if (e.target.id === 'run-commands-btn') {
                this.showRunCommandsModal();
            }
        });

        // Bind quick action input change events for persistence
        this.bindQuickActionPersistence();
    }

    async executeQuickCommand(command) {
        try {
            const dryRunCheckbox = this.drawerContainer.querySelector('#dry-run-checkbox');
            const dryRun = dryRunCheckbox ? dryRunCheckbox.checked : false;
            const skipCleanupCheckbox = this.drawerContainer.querySelector('#quick-skip-cleanup-checkbox');
            const skipCleanup = skipCleanupCheckbox ? skipCleanupCheckbox.checked : false;
            const skipQbVersionCheckCheckbox = this.drawerContainer.querySelector('#quick-skip-qb-version-check-checkbox');
            const skipQbVersionCheck = skipQbVersionCheckCheckbox ? skipQbVersionCheckCheckbox.checked : false;
            const logLevelSelect = this.drawerContainer.querySelector('#quick-log-level-select');
            const logLevel = logLevelSelect ? logLevelSelect.value : '';
            const result = await this.onCommandExecute([command], {
                dryRun: dryRun,
                skip_cleanup: skipCleanup,
                skip_qb_version_check: skipQbVersionCheck,
                log_level: logLevel
            });
            this.showToast(`${command} command executed`, 'success');
        } catch (error) {
            console.error('Failed to execute quick command:', error);
            this.showToast(`Failed to execute ${command}`, 'error');
        }
    }

    showRunCommandsModal() {
        if (this.runCommandsModal) {
            // If modal already exists, just show it (it might be hidden)
            this.runCommandsModal.classList.remove('hidden');
            return;
        }

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>Run Commands</h3>
                    <button type="button" class="modal-close-btn btn btn-icon btn-close-icon">
                        ${CLOSE_ICON_SVG}
                    </button>
                </div>
                <div class="modal-content">
                    <div class="command-selection">
                        <h4>Select Commands to Execute</h4>
                        <div class="command-checkboxes">
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="recheck">
                                <span class="checkmark"></span>
                                Recheck torrents
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="cat_update">
                                <span class="checkmark"></span>
                                Update categories
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="tag_update">
                                <span class="checkmark"></span>
                                Update tags
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="rem_unregistered">
                                <span class="checkmark"></span>
                                Remove unregistered torrents
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="tag_tracker_error">
                                <span class="checkmark"></span>
                                Tag tracker errors
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="rem_orphaned">
                                <span class="checkmark"></span>
                                Remove orphaned files
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="tag_nohardlinks">
                                <span class="checkmark"></span>
                                Tag no hardlinks
                            </label>
                            <label class="checkbox-label">
                                <input type="checkbox" name="commands" value="share_limits">
                                <span class="checkmark"></span>
                                Apply share limits
                            </label>
                        </div>
                    </div>

                    <div class="execution-options">
                        <h4>Execution Options</h4>
                        <label class="checkbox-label">
                            <input type="checkbox" id="dry-run-option">
                            <span class="checkmark"></span>
                            Dry run (preview changes without executing)
                        </label>
                        <label class="checkbox-label">
                            <input type="checkbox" id="skip-cleanup-option">
                            <span class="checkmark"></span>
                            Skip cleanup
                        </label>
                        <label class="checkbox-label">
                            <input type="checkbox" id="skip-qb-version-check-option">
                            <span class="checkmark"></span>
                            Skip qBittorrent version check
                        </label>
                        <div class="form-group">
                             <label for="log-level-select" class="form-label">Log Level</label>
                             <select id="log-level-select" class="form-select">
                                 <option value="">Default</option>
                                 <option value="INFO">Info</option>
                                 <option value="DEBUG">Debug</option>
                                 <option value="TRACE">Trace</option>
                             </select>
                         </div>
                        <div class="form-group">
                            <label for="torrent-hashes" class="form-label">
                                Specific Torrent Hashes (optional)
                            </label>
                            <textarea id="torrent-hashes" class="form-textarea" rows="3"
                                      placeholder="Enter torrent hashes, one per line"></textarea>
                            <div class="form-help">
                                Leave empty to process all torrents, or enter specific hashes to process only those torrents
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary modal-cancel-btn">Cancel</button>
                    <button type="button" class="btn btn-primary modal-execute-btn">Execute Commands</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.runCommandsModal = modal; // Store reference to the modal

        // Load saved state
        const savedCommands = JSON.parse(localStorage.getItem('qbm-selected-commands') || '[]');
        const savedDryRun = localStorage.getItem('qbm-dry-run-option') === 'true';
        const savedSkipCleanup = localStorage.getItem('qbm-skip-cleanup-option') === 'true';
        const savedSkipQbVersionCheck = localStorage.getItem('qbm-skip-qb-version-check-option') === 'true';
        const savedLogLevel = localStorage.getItem('qbm-log-level-option') || '';

        // Set command checkboxes
        savedCommands.forEach(cmd => {
            const checkbox = modal.querySelector(`input[name="commands"][value="${cmd}"]`);
            if (checkbox) {
                checkbox.checked = true;
            }
        });

        // Set dry run checkbox
        modal.querySelector('#dry-run-option').checked = savedDryRun;
        modal.querySelector('#skip-cleanup-option').checked = savedSkipCleanup;
        modal.querySelector('#skip-qb-version-check-option').checked = savedSkipQbVersionCheck;
        modal.querySelector('#log-level-select').value = savedLogLevel;


        // Bind modal events
        const closeModal = () => {
            this.hideRunCommandsModal(); // Use the new hide method
        };

        modal.querySelector('.modal-close-btn').addEventListener('click', closeModal);
        modal.querySelector('.modal-cancel-btn').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        modal.querySelector('.modal-execute-btn').addEventListener('click', async () => {
            const selectedCommands = Array.from(modal.querySelectorAll('input[name="commands"]:checked'))
                .map(input => input.value);

            const dryRun = modal.querySelector('#dry-run-option').checked;
            const skipCleanup = modal.querySelector('#skip-cleanup-option').checked;
            const skipQbVersionCheck = modal.querySelector('#skip-qb-version-check-option').checked;
            const hashesText = modal.querySelector('#torrent-hashes').value.trim();
            const hashes = hashesText ? hashesText.split('\n').map(h => h.trim()).filter(h => h) : [];
            const logLevel = modal.querySelector('#log-level-select').value;

            if (selectedCommands.length === 0) {
                this.showToast('Please select at least one command', 'warning');
                return;
            }

            // Save current selections to localStorage
            localStorage.setItem('qbm-selected-commands', JSON.stringify(selectedCommands));
            localStorage.setItem('qbm-dry-run-option', dryRun);
            localStorage.setItem('qbm-skip-cleanup-option', skipCleanup);
            localStorage.setItem('qbm-skip-qb-version-check-option', skipQbVersionCheck);
            localStorage.setItem('qbm-log-level-option', logLevel);

            this.hideRunCommandsModal(); // Use the new hide method

            try {
                await this.onCommandExecute(selectedCommands, {
                    dryRun,
                    hashes,
                    skip_cleanup: skipCleanup,
                    skip_qb_version_check: skipQbVersionCheck,
                    log_level: logLevel
                });
            } catch (error) {
                console.error('Failed to execute commands:', error);
                this.showToast('Failed to execute commands', 'error');
            }
        });
    }


    hideRunCommandsModal() {
        if (this.runCommandsModal) {
            // Save current selections before hiding
            const selectedCommands = Array.from(this.runCommandsModal.querySelectorAll('input[name="commands"]:checked'))
                .map(input => input.value);
            const dryRun = this.runCommandsModal.querySelector('#dry-run-option').checked;
            const skipCleanup = this.runCommandsModal.querySelector('#skip-cleanup-option').checked;
            const skipQbVersionCheck = this.runCommandsModal.querySelector('#skip-qb-version-check-option').checked;
            const logLevel = this.runCommandsModal.querySelector('#log-level-select').value;

            localStorage.setItem('qbm-selected-commands', JSON.stringify(selectedCommands));
            localStorage.setItem('qbm-dry-run-option', dryRun);
            localStorage.setItem('qbm-skip-cleanup-option', skipCleanup);
            localStorage.setItem('qbm-skip-qb-version-check-option', skipQbVersionCheck);
            localStorage.setItem('qbm-log-level-option', logLevel);

            this.runCommandsModal.parentNode.removeChild(this.runCommandsModal);
            this.runCommandsModal = null;
        }
    }

    toggleRunCommandsModal() {
        if (this.runCommandsModal && this.runCommandsModal.parentNode) {
            // If modal exists and is in DOM, hide it
            this.hideRunCommandsModal();
        } else {
            // Otherwise, show it
            this.showRunCommandsModal();
        }
    }

    showToast(message, type = 'info') {
        // This would typically call a global toast function
        // For now, we'll use console.log
        console.log(`[${type.toUpperCase()}] ${message}`);

        // If there's a global toast function available, use it
        if (window.qbitManageApp && window.qbitManageApp.showToast) {
            window.qbitManageApp.showToast(message, type);
        }
    }

    // Show the command panel drawer
    show() {
        if (!this.drawerContainer) return;

        this.isVisible = true;
        this.drawerContainer.classList.remove('hidden');

        // Allow the display property to take effect before starting the transition
        setTimeout(() => {
            this.drawerContainer.classList.add('active');
        }, 10);


        // Update toggle button state
        const toggleBtn = this.container.querySelector('#toggle-command-panel-btn');
        if (toggleBtn) {
            toggleBtn.classList.add('active');
        }
    }

    // Hide the command panel drawer
    hide() {
        if (!this.drawerContainer) return;

        this.isVisible = false;
        this.drawerContainer.classList.remove('active');

        // Hide with delay to allow transition to complete
        setTimeout(() => {
            this.drawerContainer.classList.add('hidden');
        }, 300); // Should match the transition duration in CSS

        // Update toggle button state
        const toggleBtn = this.container.querySelector('#toggle-command-panel-btn');
        if (toggleBtn) {
            toggleBtn.classList.remove('active');
        }
    }

    // Toggle the command panel drawer visibility
    toggle() {
        if (this.isVisible) {
            this.hide();
        } else {
            this.show();
        }
    }

    // Load saved quick action values from localStorage
    loadQuickActionValues() {
        if (!this.drawerContainer) return;

        // Get saved values, defaulting dry run to true if not previously saved
        const savedDryRunValue = localStorage.getItem('qbm-quick-dry-run');
        const savedDryRun = savedDryRunValue !== null ? savedDryRunValue === 'true' : true; // Default to true
        const savedSkipCleanup = localStorage.getItem('qbm-quick-skip-cleanup') === 'true';
        const savedSkipQbVersionCheck = localStorage.getItem('qbm-quick-skip-qb-version-check') === 'true';
        const savedLogLevel = localStorage.getItem('qbm-quick-log-level') || '';

        const dryRunCheckbox = this.drawerContainer.querySelector('#dry-run-checkbox');
        const skipCleanupCheckbox = this.drawerContainer.querySelector('#quick-skip-cleanup-checkbox');
        const skipQbVersionCheckCheckbox = this.drawerContainer.querySelector('#quick-skip-qb-version-check-checkbox');
        const logLevelSelect = this.drawerContainer.querySelector('#quick-log-level-select');

        if (dryRunCheckbox) dryRunCheckbox.checked = savedDryRun;
        if (skipCleanupCheckbox) skipCleanupCheckbox.checked = savedSkipCleanup;
        if (skipQbVersionCheckCheckbox) skipQbVersionCheckCheckbox.checked = savedSkipQbVersionCheck;
        if (logLevelSelect) logLevelSelect.value = savedLogLevel;

        // Save the default value if it was set
        if (savedDryRunValue === null) {
            localStorage.setItem('qbm-quick-dry-run', 'true');
        }
    }

    // Save quick action values to localStorage
    saveQuickActionValues() {
        if (!this.drawerContainer) return;

        const dryRunCheckbox = this.drawerContainer.querySelector('#dry-run-checkbox');
        const skipCleanupCheckbox = this.drawerContainer.querySelector('#quick-skip-cleanup-checkbox');
        const skipQbVersionCheckCheckbox = this.drawerContainer.querySelector('#quick-skip-qb-version-check-checkbox');
        const logLevelSelect = this.drawerContainer.querySelector('#quick-log-level-select');

        const dryRun = dryRunCheckbox ? dryRunCheckbox.checked : false;
        const skipCleanup = skipCleanupCheckbox ? skipCleanupCheckbox.checked : false;
        const skipQbVersionCheck = skipQbVersionCheckCheckbox ? skipQbVersionCheckCheckbox.checked : false;
        const logLevel = logLevelSelect ? logLevelSelect.value : '';

        localStorage.setItem('qbm-quick-dry-run', dryRun);
        localStorage.setItem('qbm-quick-skip-cleanup', skipCleanup);
        localStorage.setItem('qbm-quick-skip-qb-version-check', skipQbVersionCheck);
        localStorage.setItem('qbm-quick-log-level', logLevel);
    }

    // Bind event listeners for quick action persistence
    bindQuickActionPersistence() {
        if (!this.drawerContainer) return;

        // Bind checkbox change events
        const checkboxes = this.drawerContainer.querySelectorAll('#dry-run-checkbox, #quick-skip-cleanup-checkbox, #quick-skip-qb-version-check-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.saveQuickActionValues();
            });
        });

        // Bind select change event
        const logLevelSelect = this.drawerContainer.querySelector('#quick-log-level-select');
        if (logLevelSelect) {
            logLevelSelect.addEventListener('change', () => {
                this.saveQuickActionValues();
            });
        }
    }
}

export { CommandPanel };
