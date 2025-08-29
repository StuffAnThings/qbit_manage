/**
 * qBit Manage Web UI - Scheduler Control Component
 * Handles dynamic scheduler management with real-time updates and persistence
 */

import { API } from '../api.js';
import { showToast } from '../utils/toast.js';
import { get, query, queryAll } from '../utils/dom.js';
import { CLOSE_ICON_SVG } from '../utils/icons.js';

class SchedulerControl {
    constructor(options = {}) {
        this.container = options.container;
        this.onScheduleChange = options.onScheduleChange || (() => {});

        this.api = new API();
        this.currentStatus = {
            current_schedule: null,
            next_run: null,
            next_run_str: null
        };

        // Validation patterns
        // Simplified cron pattern that allows common formats including comma-separated values
        this.cronPattern = /^(\*|\*\/\d+|\d+(-\d+)?(,\d+(-\d+)?)*) (\*|\*\/\d+|\d+(-\d+)?(,\d+(-\d+)?)*) (\*|\*\/\d+|\d+(-\d+)?(,\d+(-\d+)?)*) (\*|\*\/\d+|\d+(-\d+)?(,\d+(-\d+)?)*) (\*|\*\/\d+|\d+(-\d+)?(,\d+(-\d+)?)*)$/;
        this.intervalPattern = /^\d+$/;

        this.init();
    }

    init() {
        if (!this.container) {
            console.error('SchedulerControl: Container element is required');
            return;
        }

        this.render();
        this.bindEvents();
        this.loadCurrentStatus();
    }

    render() {
        this.container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Scheduler Control</h2>
                <p class="section-description">Configure and manage the dynamic scheduler for automated task execution.</p>
            </div>

            <!-- Current Schedule Display -->
            <div class="current-schedule-section scheduler-section">
                <h4>Current Schedule</h4>
                <div class="schedule-info" id="current-schedule-info" role="region" aria-labelledby="current-schedule-heading">
                    <div class="schedule-type">
                        <label>Type:</label>
                        <span id="current-schedule-type" aria-live="polite">-</span>
                    </div>
                    <div class="schedule-value">
                        <label>Value:</label>
                        <span id="current-schedule-value" aria-live="polite">-</span>
                    </div>
                    <div class="schedule-source">
                        <label>Source:</label>
                        <span id="schedule-source" aria-live="polite">-</span>
                    </div>
                    <div class="next-run">
                        <label>Next Run:</label>
                        <span id="next-run-time" aria-live="polite">-</span>
                    </div>
                </div>
            </div>

            <!-- Schedule Update Form -->
            <div class="schedule-form-section scheduler-section">
                <h4>Update Schedule</h4>
                <form id="schedule-form" class="schedule-form" role="form" aria-labelledby="schedule-form-heading">
                    <div class="form-group">
                        <fieldset>
                            <legend class="form-label">Schedule Type</legend>
                            <div class="schedule-type-selector" role="radiogroup" aria-labelledby="schedule-type-legend">
                                <label class="radio-label">
                                    <input type="radio" name="schedule-type" value="cron" id="schedule-type-cron" checked aria-describedby="cron-help">
                                    <span class="radio-mark" aria-hidden="true"></span>
                                    Cron Expression
                                </label>
                                <label class="radio-label">
                                    <input type="radio" name="schedule-type" value="interval" id="schedule-type-interval" aria-describedby="interval-help">
                                    <span class="radio-mark" aria-hidden="true"></span>
                                    Interval (minutes)
                                </label>
                            </div>
                        </fieldset>
                    </div>

                    <div class="form-group">
                        <label for="schedule-input" class="form-label required">Schedule Value</label>
                        <div class="input-group">
                            <input
                                type="text"
                                id="schedule-input"
                                class="form-input"
                                placeholder="*/15 * * * *"
                                aria-describedby="schedule-help schedule-error schedule-success"
                                aria-required="true"
                                aria-invalid="false"
                                autocomplete="off"
                            >
                            <button type="button" class="btn btn-secondary" id="validate-schedule-btn" aria-describedby="validate-help">
                                Validate
                            </button>
                        </div>
                        <div class="form-help" id="schedule-help">
                            <div class="help-cron" id="cron-help">
                                Enter a cron expression (e.g., "*/15 * * * *" for every 15 minutes)
                            </div>
                            <div class="help-interval" id="interval-help" style="display: none;">
                                Enter interval in minutes (e.g., "15" for every 15 minutes)
                            </div>
                            <div id="validate-help" style="display: none;">
                                Click to validate your schedule expression
                            </div>
                        </div>
                        <div class="form-error" id="schedule-error" style="display: none;" role="alert" aria-live="assertive">
                            <span class="error-icon" aria-hidden="true">⚠</span>
                            <span class="error-message"></span>
                        </div>
                        <div class="form-success" id="schedule-success" style="display: none;" role="status" aria-live="polite">
                            <span class="success-icon" aria-hidden="true">✓</span>
                            <span class="success-message"></span>
                        </div>
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary" id="update-schedule-btn" disabled aria-describedby="update-help">
                            <span class="btn-text">Save Schedule</span>
                            <span class="btn-loading" style="display: none;" aria-hidden="true">
                                <span class="spinner spinner-sm spinner-button" aria-hidden="true"></span>
                                Saving...
                            </span>
                        </button>
                        <button type="button" class="btn btn-secondary" id="reset-form-btn" aria-describedby="reset-help">
                            Reset
                        </button>
                        <button type="button" class="btn btn-outline btn-danger" id="delete-schedule-btn" aria-describedby="delete-help">
                            Disable Persistent Schedule
                        </button>
                        <div id="update-help" class="sr-only">Saves the schedule persistently across restarts</div>
                        <div id="reset-help" class="sr-only">Resets the form to its default state</div>
                        <div id="delete-help" class="sr-only">Toggles persistent schedule enable/disable</div>
                    </div>
                </form>
            </div>

            <!-- Quick Presets -->
            <div class="schedule-presets-section scheduler-section">
                <h4 id="presets-heading">Quick Presets</h4>
                <div class="preset-buttons" role="group" aria-labelledby="presets-heading">
                    <button type="button" class="btn btn-outline preset-btn" data-type="interval" data-value="30" aria-label="Set schedule to every 30 minutes">
                        Every 30min
                    </button>
                    <button type="button" class="btn btn-outline preset-btn" data-type="cron" data-value="0 * * * *" aria-label="Set schedule to run hourly">
                        Hourly
                    </button>
                    <button type="button" class="btn btn-outline preset-btn" data-type="cron" data-value="0 0,6,12,18 * * *" aria-label="Set schedule to run four times a day">
                        Four times a day
                    </button>
                    <button type="button" class="btn btn-outline preset-btn" data-type="cron" data-value="0 0,12 * * *" aria-label="Set schedule to run twice a day">
                        Twice a Day
                    </button>
                    <button type="button" class="btn btn-outline preset-btn" data-type="cron" data-value="0 0 * * *" aria-label="Set schedule to run daily">
                        Daily
                    </button>
                    <button type="button" class="btn btn-outline preset-btn" data-type="cron" data-value="0 0 * * 0" aria-label="Set schedule to run weekly">
                        Weekly
                    </button>
                </div>
            </div>
        `;
    }

    bindEvents() {
        const form = this.container.querySelector('#schedule-form');
        const scheduleInput = this.container.querySelector('#schedule-input');
        const validateBtn = this.container.querySelector('#validate-schedule-btn');
        const resetBtn = this.container.querySelector('#reset-form-btn');
        const deleteBtn = this.container.querySelector('#delete-schedule-btn');
        const typeRadios = this.container.querySelectorAll('input[name="schedule-type"]');
        const presetButtons = this.container.querySelectorAll('.preset-btn');

        // Form submission
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleScheduleUpdate();
            });
        }

        // Real-time validation on input
        if (scheduleInput) {
            scheduleInput.addEventListener('input', () => {
                this.validateScheduleInput();
            });

            scheduleInput.addEventListener('blur', () => {
                this.validateScheduleInput(true);
            });
        }

        // Manual validation button
        if (validateBtn) {
            validateBtn.addEventListener('click', () => {
                this.validateScheduleInput(true);
            });
        }

        // Reset form
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetForm();
            });
        }

        // Toggle persistent schedule (disable/enable without deleting file)
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                this.handlePersistenceToggle();
            });
        }

        // Schedule type change
        typeRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                this.handleScheduleTypeChange();
            });
        });

        // Preset buttons
        presetButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                this.applyPreset(btn.dataset.type, btn.dataset.value);
            });
        });
    }

    async loadCurrentStatus() {
        try {
            // Load complete scheduler status (now includes all persistence info)
            const schedulerStatus = await this.api.get('/scheduler').catch(() => ({
                current_schedule: null,
                next_run: null,
                next_run_str: null,
                is_running: false,
                source: null,
                persistent: false,
                file_exists: false
            }));

            this.updateStatus(schedulerStatus);
        } catch (error) {
            console.error('Failed to load scheduler status:', error);
            this.showError('Failed to load current scheduler status');
        }
    }

    updateStatus(status) {
        this.currentStatus = status;

        // Update current schedule info
        const scheduleType = this.container.querySelector('#current-schedule-type');
        const scheduleValue = this.container.querySelector('#current-schedule-value');
        const scheduleSource = this.container.querySelector('#schedule-source');
        const nextRunTime = this.container.querySelector('#next-run-time');
        const deleteBtn = this.container.querySelector('#delete-schedule-btn');

        if (scheduleType && scheduleValue && nextRunTime) {
            if (status.current_schedule) {
                scheduleType.textContent = status.current_schedule.type || '-';
                scheduleValue.textContent = status.current_schedule.value || '-';
            } else {
                scheduleType.textContent = '-';
                scheduleValue.textContent = '-';
            }

            if (status.next_run) {
                const nextRun = new Date(status.next_run);
                nextRunTime.textContent = nextRun.toLocaleString();
                nextRunTime.title = nextRun.toISOString();
            } else {
                nextRunTime.textContent = '-';
                nextRunTime.title = '';
            }
        }

        // Update source info
        if (scheduleSource) {
            scheduleSource.textContent = status.source || '-';
        }

        // Show & update toggle button state
        if (deleteBtn) {
            const disabled = !!status.disabled;
            const fileExists = !!status.file_exists;
            // Show button if a file exists OR currently disabled (so user can re-enable)
            deleteBtn.style.display = (fileExists || disabled) ? 'inline-block' : 'none';
            if (disabled) {
                deleteBtn.textContent = 'Enable Persistent Schedule';
                deleteBtn.classList.remove('btn-danger');
                deleteBtn.classList.add('btn-success');
            } else {
                deleteBtn.textContent = 'Disable Persistent Schedule';
                deleteBtn.classList.add('btn-danger');
                deleteBtn.classList.remove('btn-success');
            }
        }

        // Pre-populate the form with current schedule values
        this.populateFormWithCurrentSchedule(status);

        // Notify parent component
        this.onScheduleChange(status);
    }

    handleScheduleTypeChange() {
        const cronRadio = this.container.querySelector('#schedule-type-cron');
        const intervalRadio = this.container.querySelector('#schedule-type-interval');
        const scheduleInput = this.container.querySelector('#schedule-input');
        const helpCron = this.container.querySelector('.help-cron');
        const helpInterval = this.container.querySelector('.help-interval');

        const isCron = cronRadio?.checked;

        // Update placeholder and help text
        if (scheduleInput) {
            scheduleInput.placeholder = isCron ? '*/15 * * * *' : '15';
            // Only clear value if this is a manual type change, not during form population
            if (!this._isPopulatingForm) {
                scheduleInput.value = '';
            }
        }

        // Toggle help text
        if (helpCron && helpInterval) {
            helpCron.style.display = isCron ? 'block' : 'none';
            helpInterval.style.display = isCron ? 'none' : 'block';
        }

        // Clear validation state only if not populating form
        if (!this._isPopulatingForm) {
            this.clearValidation();
        }
    }

    validateScheduleInput(showFeedback = false) {
        const scheduleInput = this.container.querySelector('#schedule-input');
        const cronRadio = this.container.querySelector('#schedule-type-cron');
        const updateBtn = this.container.querySelector('#update-schedule-btn');

        if (!scheduleInput || !cronRadio || !updateBtn) return false;

        const value = scheduleInput.value.trim();
        const isCron = cronRadio.checked;

        // Clear previous validation state
        this.clearValidation();

        if (!value) {
            if (showFeedback) {
                this.showValidationError('Schedule value is required');
            }
            updateBtn.disabled = true;
            return false;
        }

        let isValid = false;
        let errorMessage = '';
        let successMessage = '';

        if (isCron) {
            isValid = this.cronPattern.test(value);
            if (!isValid) {
                errorMessage = 'Invalid cron expression. Use format: minute hour day month weekday';
            } else {
                successMessage = 'Valid cron expression';
            }
        } else {
            isValid = this.intervalPattern.test(value) && parseInt(value) > 0;
            if (!isValid) {
                errorMessage = 'Invalid interval. Must be a positive number (minutes)';
            } else {
                const minutes = parseInt(value);
                successMessage = `Valid interval: ${minutes} minute${minutes !== 1 ? 's' : ''}`;
            }
        }

        if (showFeedback) {
            if (isValid) {
                this.showValidationSuccess(successMessage);
            } else {
                this.showValidationError(errorMessage);
            }
        }

        updateBtn.disabled = !isValid;
        return isValid;
    }

    showValidationError(message) {
        const errorDiv = this.container.querySelector('#schedule-error');
        const successDiv = this.container.querySelector('#schedule-success');
        const scheduleInput = this.container.querySelector('#schedule-input');

        if (errorDiv) {
            errorDiv.querySelector('.error-message').textContent = message;
            errorDiv.style.display = 'flex';
        }

        if (successDiv) {
            successDiv.style.display = 'none';
        }

        if (scheduleInput) {
            scheduleInput.classList.add('error');
            scheduleInput.setAttribute('aria-invalid', 'true');
        }
    }

    showValidationSuccess(message) {
        const errorDiv = this.container.querySelector('#schedule-error');
        const successDiv = this.container.querySelector('#schedule-success');
        const scheduleInput = this.container.querySelector('#schedule-input');

        if (successDiv) {
            successDiv.querySelector('.success-message').textContent = message;
            successDiv.style.display = 'flex';
        }

        if (errorDiv) {
            errorDiv.style.display = 'none';
        }

        if (scheduleInput) {
            scheduleInput.classList.remove('error');
            scheduleInput.setAttribute('aria-invalid', 'false');
        }
    }

    clearValidation() {
        const errorDiv = this.container.querySelector('#schedule-error');
        const successDiv = this.container.querySelector('#schedule-success');
        const scheduleInput = this.container.querySelector('#schedule-input');

        if (errorDiv) {
            errorDiv.style.display = 'none';
        }

        if (successDiv) {
            successDiv.style.display = 'none';
        }

        if (scheduleInput) {
            scheduleInput.classList.remove('error');
            scheduleInput.setAttribute('aria-invalid', 'false');
        }
    }

    async handleScheduleUpdate() {
        const scheduleInput = this.container.querySelector('#schedule-input');
        const cronRadio = this.container.querySelector('#schedule-type-cron');
        const updateBtn = this.container.querySelector('#update-schedule-btn');

        if (!this.validateScheduleInput(true)) {
            return;
        }

        const value = scheduleInput.value.trim();
        const isCron = cronRadio.checked;

        // Show loading state
        this.setButtonLoading(updateBtn, true);

        try {
            console.log('Updating persistent schedule:', { schedule: value, type: isCron ? 'cron' : 'interval' });

            // Use the new persistent schedule API
            const response = await this.api.put('/schedule', {
                schedule: value,
                type: isCron ? 'cron' : 'interval'
            });

            console.log('Schedule persistence response:', response);

            if (response.success) {
                showToast('Schedule saved successfully and will persist across restarts', 'success');

                // Reload the current status to get the updated information
                await this.loadCurrentStatus();

            } else {
                throw new Error(response.error || response.message || 'Failed to save schedule');
            }

        } catch (error) {
            console.error('Failed to save schedule:', error);
            const errorMessage = error.message || 'Failed to save schedule';
            showToast(errorMessage, 'error');
            this.showValidationError(errorMessage);
        } finally {
            this.setButtonLoading(updateBtn, false);
        }
    }

    async handlePersistenceToggle() {
        const status = this.currentStatus || {};
        const currentlyDisabled = !!status.disabled;
        const promptMsg = currentlyDisabled
            ? 'Re-enable persistent schedule (will resume using schedule.yml contents)?'
            : 'Disable persistent schedule (file retained; environment fallback used if set)?';
        if (!confirm(promptMsg)) {
            return;
        }

        const btn = this.container.querySelector('#delete-schedule-btn');
        this.setButtonLoading(btn, true);

        try {
            console.log('Toggling persistent schedule disabled_before=', currentlyDisabled);
            // New endpoint replaces legacy DELETE /schedule?confirm=1
            const response = await this.api.post('/schedule/persistence/toggle', {});
            console.log('Persistence toggle response:', response);

            if (response.success) {
                const action = response.action || (response.disabled ? 'disabled' : 'enabled');
                const toastMsg = action === 'disabled'
                    ? 'Persistent schedule disabled (metadata retained)'
                    : 'Persistent schedule re-enabled';
                showToast(toastMsg, 'success');
                await this.loadCurrentStatus();
            } else {
                const msg = response.error || response.message || 'Failed to toggle persistence';
                showToast(msg, 'error');
                throw new Error(msg);
            }
        } catch (error) {
            console.error('Failed to toggle persistent schedule:', error);
            const errorMessage = error.message || 'Failed to toggle persistent schedule';
            showToast(errorMessage, 'error');
        } finally {
            this.setButtonLoading(btn, false);
        }
    }

    applyPreset(type, value) {
        const cronRadio = this.container.querySelector('#schedule-type-cron');
        const intervalRadio = this.container.querySelector('#schedule-type-interval');
        const scheduleInput = this.container.querySelector('#schedule-input');

        // Set the appropriate radio button
        if (type === 'cron' && cronRadio) {
            cronRadio.checked = true;
        } else if (type === 'interval' && intervalRadio) {
            intervalRadio.checked = true;
        }

        // Update the form based on type change
        this.handleScheduleTypeChange();

        // Set the value
        if (scheduleInput) {
            scheduleInput.value = value;
            scheduleInput.focus();
        }

        // Validate the preset value
        this.validateScheduleInput(true);
    }

    populateFormWithCurrentSchedule(status) {
        if (!status.current_schedule) {
            // No current schedule - leave form in default state (cron, empty value)
            console.log('No current schedule to populate form with');
            return;
        }

        const cronRadio = this.container.querySelector('#schedule-type-cron');
        const intervalRadio = this.container.querySelector('#schedule-type-interval');
        const scheduleInput = this.container.querySelector('#schedule-input');

        if (!cronRadio || !intervalRadio || !scheduleInput) {
            return;
        }

        // Set flag to prevent clearing values during type change
        this._isPopulatingForm = true;

        try {
            const scheduleType = status.current_schedule.type;
            const scheduleValue = status.current_schedule.value;

            // Set the appropriate radio button
            if (scheduleType === 'cron') {
                cronRadio.checked = true;
            } else if (scheduleType === 'interval') {
                intervalRadio.checked = true;
            }

            // Update form based on type
            this.handleScheduleTypeChange();

            // Set the value
            scheduleInput.value = scheduleValue;

            // Validate the current value
            this.validateScheduleInput();

        } finally {
            // Clear the flag
            this._isPopulatingForm = false;
        }
    }

    resetForm() {
        const cronRadio = this.container.querySelector('#schedule-type-cron');
        const scheduleInput = this.container.querySelector('#schedule-input');
        const updateBtn = this.container.querySelector('#update-schedule-btn');

        if (cronRadio) {
            cronRadio.checked = true;
        }

        if (scheduleInput) {
            scheduleInput.value = '';
        }

        if (updateBtn) {
            updateBtn.disabled = true;
        }

        this.handleScheduleTypeChange();
        this.clearValidation();
    }

    setButtonLoading(button, loading) {
        if (!button) return;

        const btnText = button.querySelector('.btn-text');
        const btnLoading = button.querySelector('.btn-loading');

        if (loading) {
            button.disabled = true;
            if (btnText) btnText.style.display = 'none';
            if (btnLoading) btnLoading.style.display = 'inline-flex';
        } else {
            button.disabled = false;
            if (btnText) btnText.style.display = 'inline';
            if (btnLoading) btnLoading.style.display = 'none';
        }
    }

    showError(message) {
        showToast(message, 'error');
    }

    show() {
        if (this.container) {
            this.container.style.display = 'block';
        }
    }

    hide() {
        if (this.container) {
            this.container.style.display = 'none';
        }
    }

    destroy() {
        if (this.container) {
            this.container.innerHTML = '';
        }
    }

    getCurrentStatus() {
        return this.currentStatus;
    }
}

export { SchedulerControl };
