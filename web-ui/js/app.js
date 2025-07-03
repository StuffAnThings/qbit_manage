/**
 * qBit Manage Web UI - Main Application
 * Modern configuration management interface for qBit Manage
 */

import { API } from './api.js';
import { ConfigForm } from './components/config-form.js';
import { CommandPanel } from './components/command-panel.js';
import { LogViewer } from './components/log-viewer.js';
import { get, query, queryAll, show, hide, showLoading, hideLoading } from './utils/dom.js';
import { initModal, showModal, hideModal } from './utils/modal.js';
import { showToast } from './utils/toast.js';
import { debounce } from './utils/utils.js';
import { HistoryManager } from './utils/history-manager.js';

class QbitManageApp {
    constructor() {
        this.api = new API();
        this.currentConfig = null;
        this.currentSection = 'commands';
        this.configData = {};
        this.initialConfigData = {}; // Store initial loaded config for dirty checking
        this.validationState = {};
        this.isDirty = false;

        // Component instances
        this.configForm = null;
        this.commandPanel = null;
        this.logViewer = null;
        this.helpModal = null; // To store the reference to the help modal
        this.historyManager = new HistoryManager(this.api); // Initialize history manager

        // Theme management
        this.theme = localStorage.getItem('qbm-theme') || 'auto';

        this.init();
    }

    async init() {
        try {
            // Initialize theme
            this.initTheme();

            // Initialize modal system
            initModal();

            // Initialize components
            this.initComponents();

            // Bind event listeners
            this.bindEvents();

            // Load initial data
            await this.loadConfigs();


            // Determine initial section from URL hash or default to 'commands'
            const initialSection = window.location.hash ? window.location.hash.substring(1) : 'commands';
            this.currentSection = initialSection; // Set currentSection based on URL hash or default
            this.showSection(initialSection);

            // Listen for hash changes to update the section
            window.addEventListener('hashchange', () => {
                const sectionFromHash = window.location.hash ? window.location.hash.substring(1) : 'commands';
                if (sectionFromHash !== this.currentSection) {
                    this.showSection(sectionFromHash);
                }
            });

            console.log('qBit Manage Web UI initialized successfully');
        } catch (error) {
            console.error('Failed to initialize application:', error);
            showToast('Failed to initialize application', 'error');
        }
    }

    initTheme() {
        // Apply saved theme or detect system preference
        if (this.theme === 'auto') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
        } else {
            document.documentElement.setAttribute('data-theme', this.theme);
        }

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (this.theme === 'auto') {
                document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
            }
        });
    }

    initComponents() {
        // Initialize form component
        this.configForm = new ConfigForm({
            container: get('section-content'),
            onDataChange: (data) => this.handleConfigChange(data),
            onValidationChange: (validation) => this.handleValidationChange(validation)
        });

        // Initialize command panel
        this.commandPanel = new CommandPanel({
            container: query('.command-panel'),
            drawerContainer: get('command-panel-drawer'),
            onCommandExecute: (commands, options) => this.executeCommands(commands, options)
        });

        // Initialize log viewer
        this.logViewer = new LogViewer({
            container: get('logs-section') // Render into the new logs section
        });
        // Initialize the LogViewer component
        this.logViewer.init();
    }

    bindEvents() {
        this._bindHeaderEvents();
        this._bindNavigationEvents();
        this._bindFooterEvents();
        this._bindWindowEvents();

        // Listen for form dirty events
        document.addEventListener('form-dirty', (e) => {
            this.updateSectionDirtyIndicator(e.detail.section, true);
        });

        // Listen for form reset events
        document.addEventListener('form-reset', (e) => {
            this.updateSectionDirtyIndicator(e.detail.section, false);
        });
    }

    _bindHeaderEvents() {
        // Config selector
        const configSelect = get('config-select');
        configSelect.addEventListener('change', (e) => {
            this.loadConfig(e.target.value);
            localStorage.setItem('qbm-last-selected-config', e.target.value);
        });

        // New config button
        const newConfigBtn = get('new-config-btn');
        if (newConfigBtn) {
            newConfigBtn.addEventListener('click', () => {
                this.showNewConfigModal();
            });
        }

        // Save config button
        get('save-config-btn').addEventListener('click', () => {
            this.saveConfig();
        });

        // Validate config button
        get('validate-config-btn').addEventListener('click', () => {
            this.validateConfig();
        });

        // Backup config button
        get('backup-config-btn').addEventListener('click', () => {
            this.backupConfig();
        });

        // Theme toggle
        get('theme-toggle').addEventListener('click', debounce(() => {
            this.toggleTheme();
        }, 300)); // Debounce with 300ms delay

        // Undo button
        const undoBtn = get('undo-btn');
        if (undoBtn) {
            undoBtn.addEventListener('click', () => {
                this.undoConfig();
            });
        }

        // Redo button
        const redoBtn = get('redo-btn');
        if (redoBtn) {
            redoBtn.addEventListener('click', () => {
                this.redoConfig();
            });
        }
    }

    _bindNavigationEvents() {
        // Navigation menu
        get('nav-menu').addEventListener('click', (e) => {
            const navLink = e.target.closest('.nav-link');
            if (navLink) {
                e.preventDefault();
                const section = navLink.getAttribute('href').substring(1);
                this.showSection(section);
            }
        });
    }

    _bindFooterEvents() {
        // YAML preview toggle
        get('yaml-preview-btn').addEventListener('click', () => {
            this.toggleYamlPreview();
        });

        // Close YAML preview
        get('close-preview-btn').addEventListener('click', () => {
            this.hideYamlPreview();
        });

        // Help button
        get('help-btn').addEventListener('click', () => {
            this.showHelpModal();
        });


    }

    _bindWindowEvents() {
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // Window events
        window.addEventListener('beforeunload', (e) => {
            if (this.isDirty) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            }
        });

        // Mobile menu toggle (for responsive design)
        const mobileMenuToggle = query('.mobile-menu-toggle');
        if (mobileMenuToggle) {
            mobileMenuToggle.addEventListener('click', () => {
                this.toggleMobileMenu();
            });
        }

        // Listen for history state changes
        document.addEventListener('history-state-change', (e) => {
            if (e.detail.configName === this.currentConfig) {
                this.configData = e.detail.data;
                this.showSection(this.currentSection);
                this.updateHistoryButtons();
            }
        });
    }

    async loadConfigs() {
        try {
            const response = await this.api.listConfigs();
            const configSelect = get('config-select');

            // Clear existing options
            configSelect.innerHTML = '';

            if (response.configs.length === 0) {
                configSelect.innerHTML = '<option value="">No configurations found</option>';
                return;
            }

            // Add config options
            response.configs.forEach(config => {
                const option = document.createElement('option');
                option.value = config;
                option.textContent = config;
                if (config === response.default_config) {
                    option.selected = true;
                }
                configSelect.appendChild(option);
            });

            // Attempt to load the last selected config from localStorage
            const lastSelectedConfig = localStorage.getItem('qbm-last-selected-config');
            let configToLoad = response.default_config;

            if (lastSelectedConfig && response.configs.includes(lastSelectedConfig)) {
                configToLoad = lastSelectedConfig;
            }

            // Set the selected option in the dropdown
            configSelect.value = configToLoad;

            // Load the determined config
            if (configToLoad) {
                await this.loadConfig(configToLoad);
            }
        } catch (error) {
            console.error('Failed to load configs:', error);
            showToast('Failed to load configurations', 'error');
        }
    }

    async loadConfig(filename) {
        if (!filename) return;

        try {
            showLoading(get('section-content'));
            const response = await this.api.getConfig(filename);

            this.currentConfig = filename;
            this.configData = response.data || {};
            this.initialConfigData = JSON.parse(JSON.stringify(this.configData)); // Deep copy for dirty checking
            this.isDirty = false;

            // Initialize history manager for this config with initial data
            await this.historyManager.initializeFromBackups(filename, this.configData);

            // Update UI
            this.updateSaveButton();
            this.updateProgressIndicator();
            this.clearAllDirtyIndicators();
            this.updateHistoryButtons();

            // Load current section
            const sectionData = this.configForm.schemas[this.currentSection]?.type === 'multi-root-object'
                ? this.configData
                : this.configData[this.currentSection] || {};
            await this.configForm.loadSection(this.currentSection, sectionData);

            hideLoading();
            showToast(`Configuration "${filename}" loaded successfully`, 'success');
        } catch (error) {
            console.error('Failed to load config:', error);
            hideLoading();
            showToast(`Failed to load configuration "${filename}"`, 'error');
        }
    }

    async saveConfig() {
        if (!this.currentConfig) {
            showToast('No configuration selected', 'warning');
            return;
        }

        try {
            const processedData = this.configForm._postprocessDataForSave(this.currentSection, this.configForm.currentData);

            const isMultiRoot = this.configForm.schemas[this.currentSection]?.type === 'multi-root-object';
            const dataToSave = isMultiRoot ? processedData : { [this.currentSection]: processedData };

            const fullConfigData = { ...this.configData, ...dataToSave };

            // Remove UI-only fields that should never be saved
            delete fullConfigData.apply_to_all_value;

            // Clean up empty values before saving
            const cleanedConfigData = this.configForm.cleanupEmptyValues(fullConfigData);

            // Create history checkpoint with the NEW state after saving
            await this.historyManager.createCheckpoint(
                this.currentConfig,
                cleanedConfigData, // Use the new state after changes
                `Updated ${this.currentSection} section`,
                true // Mark as save point
            );

            showLoading(get('section-content'));
            await this.api.updateConfig(this.currentConfig, { data: cleanedConfigData || {} });

            // Reload the configuration from the server to get the actual saved data
            // This ensures we have the correct data that was actually written to the file
            const reloadedConfig = await this.api.getConfig(this.currentConfig);
            this.configData = reloadedConfig.data || {};
            this.initialConfigData = JSON.parse(JSON.stringify(this.configData)); // Update initial data after save
            this.isDirty = false;
            this.updateSaveButton();
            this.clearAllDirtyIndicators();

            // Re-render the current section to hide the loading spinner and show updated data
            const sectionDataForReload = isMultiRoot ? this.configData : this.configData[this.currentSection] || {};
            await this.configForm.loadSection(this.currentSection, sectionDataForReload);

            hideLoading();
            showToast(`Configuration "${this.currentConfig}" saved successfully`, 'success');
        } catch (error) {
            console.error('Failed to save config:', error);
            hideLoading();
            showToast(`Failed to save configuration "${this.currentConfig}"`, 'error');
        }
    }

    async undoConfig() {
        if (!this.currentConfig) {
            showToast('No configuration selected', 'warning');
            return;
        }

        try {
            if (!this.historyManager.canUndo(this.currentConfig)) {
                showToast('Nothing to undo', 'info');
                return;
            }

            showLoading(get('section-content'));
            const result = await this.historyManager.undo(this.currentConfig);

            if (result) {
                // Update the configuration data directly without creating a backup
                this.configData = result.data || {};
                this.initialConfigData = JSON.parse(JSON.stringify(this.configData));
                this.isDirty = false;
                this.updateSaveButton();
                this.clearAllDirtyIndicators();

                // Force full form reload with new data
                const isMultiRoot = this.configForm.schemas[this.currentSection]?.type === 'multi-root-object';
                const sectionData = isMultiRoot ? this.configData : this.configData[this.currentSection] || {};
                await this.configForm.loadSection(this.currentSection, sectionData);

                hideLoading();
                showToast(`Undone: ${result.description}`, 'undo');
            } else {
                hideLoading();
                showToast(`Cannot undo: ${result.error}`, 'error');
            }
        } catch (error) {
            console.error('Failed to undo config:', error);
            hideLoading();
            showToast('Failed to undo configuration changes', 'error');
        }
        this.updateHistoryButtons();
    }

    async redoConfig() {
        if (!this.currentConfig) {
            showToast('No configuration selected', 'warning');
            return;
        }

        try {
            if (!this.historyManager.canRedo(this.currentConfig)) {
                showToast('Nothing to redo', 'info');
                return;
            }

            showLoading(get('section-content'));
            const result = await this.historyManager.redo(this.currentConfig);

            if (result) {
                // Update the configuration data directly without creating a backup
                this.configData = result.data || {};
                this.initialConfigData = JSON.parse(JSON.stringify(this.configData));
                this.isDirty = false;
                this.updateSaveButton();
                this.clearAllDirtyIndicators();

                // Force full form reload with new data
                const isMultiRoot = this.configForm.schemas[this.currentSection]?.type === 'multi-root-object';
                const sectionData = isMultiRoot ? this.configData : this.configData[this.currentSection] || {};
                await this.configForm.loadSection(this.currentSection, sectionData);

                hideLoading();
                showToast(`Redone: ${result.description}`, 'redo');
            } else {
                hideLoading();
                showToast('Nothing to redo', 'info');
            }
        } catch (error) {
            console.error('Failed to redo config:', error);
            hideLoading();
            showToast('Failed to redo configuration changes', 'error');
        }
        this.updateHistoryButtons();
    }

    updateHistoryButtons() {
        const undoBtn = get('undo-btn');
        const redoBtn = get('redo-btn');

        if (!this.currentConfig) {
            if (undoBtn) undoBtn.disabled = true;
            if (redoBtn) redoBtn.disabled = true;
            return;
        }

        const canUndo = this.historyManager.canUndo(this.currentConfig);
        const canRedo = this.historyManager.canRedo(this.currentConfig);

        if (undoBtn) undoBtn.disabled = !canUndo;
        if (redoBtn) redoBtn.disabled = !canRedo;
    }

    async validateConfig() {
        if (!this.currentConfig) {
            showToast('No configuration selected', 'warning');
            return;
        }

        try {
            showLoading(get('section-content'));
            const response = await this.api.validateConfig(this.currentConfig, { data: this.configData });

            hideLoading();

            if (response.valid) {
                showToast('Configuration is valid', 'success');
            } else {
                // Pass the errors array directly instead of converting to string
                this.showValidationModal('Configuration Validation Failed', response.errors, response.warnings);
            }
        } catch (error) {
            console.error('Failed to validate config:', error);
            hideLoading();
            showToast('Failed to validate configuration', 'error');
        }
    }

    async backupConfig() {
        if (!this.currentConfig) {
            showToast('No configuration selected', 'warning');
            return;
        }

        try {
            showLoading(get('section-content'));
            const response = await this.api.backupConfig(this.currentConfig);

            // Create a history checkpoint for the manual backup
            this.historyManager.createCheckpoint(
                this.currentConfig,
                this.configData,
                `Manual Backup: ${response.backup_file}`,
                true // isSavePoint
            );

            hideLoading();
            showToast(`Manual backup created: ${response.backup_file}`, 'success');
        } catch (error) {
            console.error('Failed to create backup:', error);
            hideLoading();
            showToast('Failed to create configuration backup', 'error');
        }
    }

    showSection(sectionName) {
        // Update URL hash
        if (window.location.hash.substring(1) !== sectionName) {
            window.location.hash = sectionName;
        }

        // Update navigation
        queryAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        const activeLink = query(`[href="#${sectionName}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        // Update section title
        const sectionTitle = get('section-title');
        const sectionNames = {
            commands: 'Commands',
            qbt: 'qBittorrent Connection',
            settings: 'Settings',
            directory: 'Directory Paths',
            cat: 'Categories',
            cat_change: 'Category Changes',
            tracker: 'Tracker Configuration',
            nohardlinks: 'No Hard Links',
            share_limits: 'Share Limits',
            recyclebin: 'Recycle Bin',
            orphaned: 'Orphaned Files',
            notifications: 'Notifications',
            logs: 'Logs'
        };

        sectionTitle.textContent = sectionNames[sectionName] || 'Configuration';

        // Toggle visibility of content sections
        const mainContentSection = get('section-content');
        const logsSection = get('logs-section');

        if (sectionName === 'logs') {
            if (mainContentSection) hide(mainContentSection);
            this.logViewer.show(); // Use the LogViewer's show method
        } else {
            if (mainContentSection) show(mainContentSection);
            this.logViewer.hide(); // Use the LogViewer's hide method
            // Load current section for config forms
            if (this.configData) {
                const sectionData = this.configForm.schemas[sectionName]?.type === 'multi-root-object'
                    ? this.configData
                    : this.configData[sectionName] || {};
                this.configForm.loadSection(sectionName, sectionData);
            }
        }

        this.currentSection = sectionName;
    }

    handleConfigChange(sectionData) {

        const isMultiRoot = this.configForm.schemas[this.currentSection]?.type === 'multi-root-object';
        if (isMultiRoot) {
            Object.assign(this.configData, sectionData);
        } else {
            const isMultiRoot = this.configForm.schemas[this.currentSection]?.type === 'multi-root-object';
            if (isMultiRoot) {
                Object.assign(this.configData, sectionData);
            } else {
                this.configData[this.currentSection] = sectionData;
            }
        }
        this.isDirty = JSON.stringify(this.configData) !== JSON.stringify(this.initialConfigData);

        this.updateSaveButton();
        this.updateProgressIndicator();
    }

    handleValidationChange(validation) {
        this.validationState[this.currentSection] = validation;
        this.updateValidationIndicators();
    }

    updateSaveButton() {
        const saveBtn = get('save-config-btn');
        saveBtn.disabled = !this.isDirty || !this.currentConfig;

        if (this.isDirty) {
            saveBtn.classList.add('btn-warning');
            saveBtn.classList.remove('btn-primary');
        } else {
            saveBtn.classList.add('btn-primary');
            saveBtn.classList.remove('btn-warning');
        }
    }

    updateProgressIndicator() {
        const sections = ['commands', 'qbt', 'settings', 'directory', 'cat', 'cat_change',
                         'tracker', 'nohardlinks', 'share_limits', 'recyclebin', 'orphaned', 'notifications'];

        let completedSections = 0;
        sections.forEach(section => {
            if (this.configData[section] && Object.keys(this.configData[section]).length > 0) {
                completedSections++;
            }
        });

        const progressFill = get('config-progress');
        const progressText = get('progress-text');

        const percentage = (completedSections / sections.length) * 100;
        progressFill.style.width = `${percentage}%`;
        progressText.textContent = `${completedSections}/${sections.length} sections`;
    }

    updateValidationIndicators() {
        Object.keys(this.validationState).forEach(section => {
            const navItem = query(`[data-section="${section}"]`);
            if (navItem) {
                const indicator = navItem.querySelector('.validation-indicator');
                const validation = this.validationState[section];

                indicator.classList.remove('valid', 'invalid', 'warning');

                if (validation.errors && validation.errors.length > 0) {
                    indicator.classList.add('invalid');
                } else if (validation.warnings && validation.warnings.length > 0) {
                    indicator.classList.add('warning');
                } else if (validation.valid) {
                    indicator.classList.add('valid');
                }
            }
        });
    }

    updateSectionDirtyIndicator(sectionName, isDirty) {
        const navLink = query(`.nav-link[href="#${sectionName}"]`);
        if (navLink) {
            if (isDirty) {
                navLink.classList.add('dirty');
            } else {
                navLink.classList.remove('dirty');
            }
        }
    }

    clearAllDirtyIndicators() {
        queryAll('.nav-link.dirty').forEach(link => {
            link.classList.remove('dirty');
        });
    }

    toggleTheme() {
        const oldTheme = this.theme;
        if (this.theme === 'light') {
            this.theme = 'dark';
        } else if (this.theme === 'dark') {
            this.theme = 'auto';
        } else { // current theme is 'auto'
            this.theme = 'light';
        }
        localStorage.setItem('qbm-theme', this.theme);
        this.initTheme(); // Re-apply theme based on new setting

        let toastMessage = `Theme set to ${this.theme.charAt(0).toUpperCase() + this.theme.slice(1)}`;
        if (this.theme === 'auto') {
            toastMessage += ' (system preference)';
        }
        showToast(toastMessage, 'info');
    }

    toggleYamlPreview() {
        const previewContainer = get('yaml-preview');
        const mainContent = query('.main-content');

        if (!previewContainer.classList.contains('hidden')) {
            this.hideYamlPreview();
        } else {
            this.showYamlPreview();
        }
    }

    showYamlPreview() {
        const previewContainer = get('yaml-preview');
        const yamlContent = get('yaml-content');
        const mainContent = query('.main-content');
        const yamlString = this.generateYamlString(this.configData);

        yamlContent.textContent = yamlString;
        previewContainer.classList.remove('hidden');
        if (mainContent) {
            mainContent.classList.add('yaml-preview-active');
        }
    }

    hideYamlPreview() {
        const previewContainer = get('yaml-preview');
        const mainContent = query('.main-content');

        previewContainer.classList.add('hidden');
        if (mainContent) {
            mainContent.classList.remove('yaml-preview-active');
        }
    }

    toggleLogPanel() {
        const logDrawer = get('command-panel-drawer');
        logDrawer.classList.toggle('show');
    }

    hideLogPanel() {
        const logDrawer = get('command-panel-drawer');
        logDrawer.classList.remove('show');
    }

    toggleMobileMenu() {
        const sidebar = query('.sidebar');
        sidebar.classList.toggle('show');
    }

    /**
     * Converts a JSON object to a YAML-formatted string.
     * @param {object} data - The JSON object to convert.
     * @returns {string} The YAML-formatted string.
     */
    generateYamlString(data) {
        if (!data) return '';

        const processValue = (value, indent = 0) => {
            const indentStr = '  '.repeat(indent);
            if (value === null) {
                return 'null';
            }
            if (typeof value === 'object') {
                if (Array.isArray(value)) {
                    if (value.length === 0) return '[]'; // Represent empty array explicitly
                    return value.map(item => `\n${indentStr}- ${processValue(item, indent)}`).join('');
                } else {
                    return Object.entries(value)
                        .map(([key, val]) => `\n${indentStr}${key}: ${processValue(val, indent + 1)}`)
                        .join('');
                }
            }
            return value;
        };

        return Object.entries(data)
            .map(([key, value]) => `${key}: ${processValue(value, 1)}`)
            .join('\n');
    }

    handleKeyboardShortcuts(e) {
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            this.saveConfig();
        }
        if (e.ctrlKey && e.key === 'r') {
            e.preventDefault();
            this.commandPanel.toggleRunCommandsModal();
        }
        if (e.ctrlKey && e.key === 'z' && !e.shiftKey) { // Ctrl + Z (undo)
            e.preventDefault();
            this.undoConfig();
        }
        if (e.ctrlKey && e.key === 'y') { // Ctrl + Y (redo)
            e.preventDefault();
            this.redoConfig();
        }
        if (e.ctrlKey && e.key === '/' && !e.shiftKey) { // Ctrl + /
            e.preventDefault();
            this.toggleHelpModal();
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'p') { // Ctrl+P or Cmd+P for YAML Preview
            e.preventDefault();
            this.toggleYamlPreview();
        }
        if (e.key === 'Escape') {
            // Attempt to close the share limits edit modal if it's open
            const shareLimitsModal = document.querySelector('.share-limit-modal');
            if (shareLimitsModal && shareLimitsModal.parentNode) {
                shareLimitsModal.parentNode.removeChild(shareLimitsModal);
                // Also clear the helpModal reference if it was the share limits modal (unlikely but safe)
                if (this.helpModal === shareLimitsModal) {
                    this.helpModal = null;
                }
                // Do NOT return here, allow other escape actions to proceed
            }

            // Close other modals/panels
            this.hideYamlPreview();
            this.hideLogPanel();
            // Check if the global modal is open and close it
            const globalModalOverlay = document.getElementById('modal-overlay');
            if (this.helpModal && this.helpModal.parentNode) {
                 // If the help modal is open, close it
                 this.hideHelpModal();
            }
            if (globalModalOverlay && globalModalOverlay.style.display !== 'none') {
                 hideModal(); // Use the utility function for the global modal
                 this.hideHelpModal();
            }
        }
    }

    async executeCommands(commands, options) {
        try {
            this.showSection('logs');
            this.logViewer.clearLogs();
            this.logViewer.log('info', `Executing commands: ${commands.join(', ')} with options: ${JSON.stringify(options)}`);

            const response = await this.api.runCommand({
                commands: commands,
                config_file: this.currentConfig,
                hashes: options.hashes || [],
                dry_run: options.dryRun, // Map dryRun from options to dry_run for the API
            });

            this.logViewer.log('info', 'Commands executed successfully.');
            
            // Display the API response in the log viewer
            if (response) {
                this.logViewer.log('info', `Response: ${JSON.stringify(response, null, 2)}`);
            }
        } catch (error) {
            console.error('Command execution failed:', error);
            this.logViewer.log('error', `Command execution failed: ${error.message}`);
            
            // Refresh logs even on error to show any server-side logs
            await this.logViewer.loadRecentLogs();
        }
    }

    async showNewConfigModal() {
        const modalContent = `
            <div class="form-group">
                <label for="new-config-name" class="form-label">New Configuration Name</label>
                <input type="text" id="new-config-name" class="form-input" placeholder="e.g., config_new.yml">
            </div>
        `;
        
        const confirmed = await showModal('Create New Configuration', modalContent, {
            confirmText: 'Create',
            cancelText: 'Cancel',
            showCancel: true
        });
        
        if (confirmed) {
            const newConfigName = get('new-config-name').value;
            if (newConfigName) {
                try {
                    // Ensure name ends with .yml
                    const finalName = newConfigName.endsWith('.yml') ? newConfigName : `${newConfigName}.yml`;

                    // Create an empty config file
                    await this.api.createConfig(finalName, { data: {} });

                    showToast(`Configuration "${finalName}" created successfully`, 'success');

                    // Reload the config list to show the new config
                    await this.loadConfigs();

                    // Select the new config in the dropdown
                    const configSelect = get('config-select');
                    configSelect.value = finalName;

                    // Manually trigger the change event to load the new config
                    configSelect.dispatchEvent(new Event('change'));

                } catch (error) {
                    console.error('Failed to create new config:', error);
                    showToast('Failed to create new configuration', 'error');
                }
            } else {
                showToast('Please enter a name for the new configuration.', 'warning');
            }
        }
    }

    showValidationModal(title, errors, warnings = []) {
        const errorList = errors && errors.length > 0 ? `<h3 class="validation-subheader">Errors:</h3><ul class="validation-list">${errors.map(e => `<li>${e}</li>`).join('')}</ul>` : '';
        const warningList = warnings.length > 0 ? `<h3 class="validation-subheader">Warnings:</h3><ul class="validation-list">${warnings.map(w => `<li>${w}</li>`).join('')}</ul>` : '';
        const modalContent = `<div class="validation-results">${errorList}${warningList}</div>`;

        showModal(title, modalContent, {
            confirmText: 'Close',
            showCancel: false
        });
    }

    hideHelpModal() {
        if (this.helpModal && this.helpModal.parentNode) {
            this.helpModal.parentNode.removeChild(this.helpModal);
            this.helpModal = null;
        }
    }

    toggleHelpModal() {
        if (this.helpModal && this.helpModal.parentNode) {
            // If modal exists and is in DOM, hide it
            this.hideHelpModal();
        } else {
            // Otherwise, show it
            this.showHelpModal();
        }
    }

    showHelpModal() {
        // Ensure any previous modal is removed before creating a new one
        if (this.helpModal && this.helpModal.parentNode) {
            this.helpModal.parentNode.removeChild(this.helpModal);
        }
        this.helpModal = null; // Reset to null before creating a new one

        const modal = document.createElement('div');
        modal.className = 'modal-overlay'; // Use the same class as other modals
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>Help & Shortcuts</h3>
                    <button type="button" class="modal-close-btn btn btn-icon btn-close-icon">
                        <svg class="icon" viewBox="0 0 24 24">
                            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                        </svg>
                    </button>
                </div>
                <div class="modal-content">
                    <h3 class="help-title">Keyboard Shortcuts</h3>
                    <ul class="key-value-list">
                        <li class="key-value-item">
                            <span class="key-name">Ctrl + S</span>
                            <span class="value-name">Save current configuration</span>
                        </li>
                        <li class="key-value-item">
                            <span class="key-name">Ctrl + Z</span>
                            <span class="value-name">Undo last configuration change</span>
                        </li>
                        <li class="key-value-item">
                            <span class="key-name">Ctrl + Y</span>
                            <span class="value-name">Redo configuration change</span>
                        </li>
                        <li class="key-value-item">
                            <span class="key-name">Ctrl + R</span>
                            <span class="value-name">Toggle commands modal</span>
                        </li>
                        <li class="key-value-item">
                            <span class="key-name">Ctrl + /</span>
                            <span class="value-name">Toggle keyboard shortcuts help</span>
                        </li>
                        <li class="key-value-item">
                            <span class="key-name">Ctrl + P</span>
                            <span class="value-name">Toggle YAML preview</span>
                        </li>
                        <li class="key-value-item">
                            <span class="key-name">Esc</span>
                            <span class="value-name">Close modals, YAML preview, and log panel</span>
                        </li>
                    </ul>
                    <h3 class="help-title">Need More Help?</h3>
                    <p>For more detailed documentation and support, please visit the
                        <a href="https://github.com/StuffAnThings/qbit_manage/wiki" target="_blank" rel="noopener noreferrer">
                            Official GitHub Repository
                        </a>.
                    </p>
                    <h3 class="help-title">Developer Resources</h3>
                    <p>For API documentation and technical details:
                        <br>
                        <a href="/docs" target="_blank" rel="noopener noreferrer">
                            📚 Interactive API Documentation (Swagger UI)
                        </a>
                        <br>
                        <a href="/redoc" target="_blank" rel="noopener noreferrer">
                            📖 Alternative API Documentation (ReDoc)
                        </a>
                    </p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary modal-cancel-btn">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        this.helpModal = modal; // Store reference to the modal

        // Bind modal events
        const closeModal = () => {
            this.hideHelpModal();
        };

        modal.querySelector('.modal-close-btn').addEventListener('click', closeModal);
        modal.querySelector('.modal-cancel-btn').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    showRunCommandsModal() {
        if (!this.commandPanel.schema || this.commandPanel.schema.length === 0) {
            showToast('No commands available to run.', 'warning');
            return;
        }

        const commandOptions = this.commandPanel.schema.map(cmd => {
            return `
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="command" value="${cmd.name}" class="form-checkbox">
                        <span class="checkmark"></span>
                        ${cmd.name}
                         <small class="command-description">${cmd.description}</small>
                    </label>
                </div>
            `;
        }).join('');

        const dryRunOption = `
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" id="dry-run-checkbox" class="form-checkbox">
                     <span class="checkmark"></span>
                    Dry Run
                    <small class="command-description">Preview changes without applying them.</small>
                </label>
            </div>
        `;

        const modalContent = `
            <div class="run-commands-modal">
                <p>Select the commands you want to run.</p>
                <div class="command-list">${commandOptions}</div>
                <hr>
                ${dryRunOption}
            </div>
        `;

        showModal('Run Commands', modalContent, [
            { label: 'Cancel', classes: 'btn-secondary', action: hideModal },
            {
                label: 'Run Selected',
                classes: 'btn-primary',
                action: async () => {
                    const selectedCommands = Array.from(queryAll('input[name="command"]:checked')).map(cb => cb.value);
                    const isDryRun = get('dry-run-checkbox').checked;

                    if (selectedCommands.length > 0) {
                        this.executeCommands(selectedCommands, { 'dry_run': isDryRun });
                        hideModal();
                    } else {
                        showToast('No commands selected.', 'warning');
                    }
                }
            }
        ]);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new QbitManageApp();
});
