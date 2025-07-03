/**
 * qBit Manage Web UI - Configuration Form Component
 * Dynamic form generation for different configuration sections
 */

import { API } from '../api.js';
import { showToast } from '../utils/toast.js';
import { get, query, queryAll } from '../utils/dom.js';
import { CLOSE_ICON_SVG, EYE_ICON_SVG, EYE_SLASH_ICON_SVG } from '../utils/icons.js';
import { generateSectionHTML } from '../utils/form-renderer.js';
import { getNestedValue, setNestedValue, isValidHost } from '../utils/utils.js';

// Import all section schemas
import { commandsSchema } from '../config-schemas/commands.js';
import { qbtSchema } from '../config-schemas/qbt.js';
import { settingsSchema } from '../config-schemas/settings.js';
import { directorySchema } from '../config-schemas/directory.js';
import { catSchema } from '../config-schemas/cat.js';
import { catChangeSchema } from '../config-schemas/cat_change.js';
import { trackerSchema } from '../config-schemas/tracker.js';
import { nohardlinksSchema } from '../config-schemas/nohardlinks.js';
import { shareLimitsSchema } from '../config-schemas/share_limits.js';
import { recyclebinSchema } from '../config-schemas/recyclebin.js';
import { orphanedSchema } from '../config-schemas/orphaned.js';
import { notificationsSchema } from '../config-schemas/notifications.js';
import { ShareLimitsComponent } from './share-limits.js';

class ConfigForm {
    constructor(options = {}) {
        this.container = options.container;
        this.onDataChange = options.onDataChange || (() => {});
        this.onValidationChange = options.onValidationChange || (() => {});

        this.api = new API();
        this.currentSection = null;
        this.currentData = {};
        this.originalData = {}; // Store original data for reset
        this.initialSectionData = {}; // Store initial data per section
        this.validationState = { valid: true, errors: [], warnings: [] };
        this.shareLimitsComponent = null; // Store reference to share limits component

        // Store bound function references for proper event listener management
        this.boundHandleInputChange = this.handleInputChange.bind(this);

        // Map section names to their imported schemas
        this.schemas = {
            commands: commandsSchema,
            qbt: qbtSchema,
            settings: settingsSchema,
            directory: directorySchema,
            cat: catSchema,
            cat_change: catChangeSchema,
            tracker: trackerSchema,
            nohardlinks: nohardlinksSchema,
            share_limits: shareLimitsSchema,
            recyclebin: recyclebinSchema,
            orphaned: orphanedSchema,
            notifications: notificationsSchema,
        };

        this.init();
        this.bindEvents(); // Bind events once during initialization
    }

    init() {
        // No schema loading needed, as they are imported directly
    }

    async loadSection(sectionName, data = {}) {
        this.currentSection = sectionName;
        // Deep copy and preprocess data to ensure 'tag' is always an array
        this.currentData = this._preprocessComplexObjectData(sectionName, data);

        // Store initial data only once per section
        if (!this.initialSectionData[sectionName]) {
            this.initialSectionData[sectionName] = JSON.parse(JSON.stringify(this.currentData));
        }

        // Always reset to initial data when loading a section
        this.originalData = JSON.parse(JSON.stringify(this.initialSectionData[sectionName]));

        // Store original format for nohardlinks for bidirectional conversion
        if (sectionName === 'nohardlinks' && Array.isArray(data.nohardlinks_categories)) {
            this.currentData._originalNohardlinksFormat = 'array';
        } else if (sectionName === 'nohardlinks' && typeof data.nohardlinks_categories === 'object' && data.nohardlinks_categories !== null) {
            this.currentData._originalNohardlinksFormat = 'object';
        }

        await this.renderSection();
        // Removed this.validateSection() from here to prevent premature validation display
    }

    async renderSection() {
        if (!this.container || !this.currentSection) return;

        const sectionConfig = this.schemas[this.currentSection];
        if (!sectionConfig) {
            console.error(`No schema found for section: ${this.currentSection}`);
            this.container.innerHTML = `<div class="alert alert-error">Error: Configuration schema not found for section "${this.currentSection}".</div>`;
            return;
        }

        const html = generateSectionHTML(sectionConfig, this.currentData);
        this.container.innerHTML = html;

        // Re-bind input events after rendering new content
        this._bindInputEvents();

        // Initialize ShareLimitsComponent for share_limits section
        if (this.currentSection === 'share_limits') {
            const shareLimitsContainer = this.container.querySelector('.share-limits-config');
            if (shareLimitsContainer) {
                this.shareLimitsComponent = new ShareLimitsComponent(
                    shareLimitsContainer,
                    this.currentData,
                    (newData) => {
                        this.currentData = newData;
                        this.onDataChange(this.currentData);
                        this._dispatchDirtyEvent();
                    }
                );
            }
        }
    }

    bindEvents() {
        if (!this.container) return;

        this._bindInputEvents();
        this._bindClickEvents();
    }

    // This function should only be called once during initialization
    _bindClickEvents() {
        this.container.addEventListener('click', (e) => {
            // Handle clicks on SVG elements inside buttons by finding the closest button
            let targetElement = e.target;
            if (e.target.tagName === 'svg' || e.target.tagName === 'path') {
                const closestButton = e.target.closest('button');
                if (closestButton) {
                    targetElement = closestButton;
                }
            }

            if (targetElement.classList.contains('add-array-item')) {
                this.addArrayItem(targetElement.dataset.field);
            } else if (targetElement.classList.contains('remove-array-item')) {
                this.removeArrayItem(targetElement.closest('.array-item'));
            } else if (targetElement.classList.contains('add-category-btn')) {
                if (this.schemas[this.currentSection].type === 'dynamic-key-value-list') {
                    this.addCategory();
                }
            } else if (targetElement.classList.contains('remove-category-btn')) {
                if (this.schemas[this.currentSection].type === 'dynamic-key-value-list') {
                    this.removeCategory(targetElement.closest('.key-value-item'));
                }
            } else if (targetElement.classList.contains('password-toggle')) {
                this.togglePasswordVisibility(targetElement.dataset.target);
            } else if (targetElement.classList.contains('add-complex-object-item-btn')) {
                this.addComplexObjectItem();
            } else if (targetElement.classList.contains('remove-complex-object-item')) {
                this.removeComplexObjectItem(targetElement.dataset.key);
            } else if (targetElement.id === 'reset-section-btn') {
                this.resetSection();
            } else if (targetElement.id === 'validate-section-btn') {
                this.validateSection();
            } else if (targetElement.classList.contains('apply-to-all-btn')) {
                e.preventDefault();
                e.stopPropagation();
                const action = targetElement.dataset.action;
                if (action === 'apply-to-all') {
                    this.applyToAllWebhooks();
                }
            }
        });
    }

    _bindInputEvents() {
        // Remove existing listeners to prevent duplicates
        this.container.removeEventListener('input', this.boundHandleInputChange);
        this.container.removeEventListener('change', this.boundHandleInputChange);

        // Add new listeners using the stored bound reference
        this.container.addEventListener('input', this.boundHandleInputChange);
        this.container.addEventListener('change', this.boundHandleInputChange);

    }

    _bindClickEvents() {
        this.container.addEventListener('click', (e) => {
            // Handle clicks on SVG elements inside buttons by finding the closest button
            let targetElement = e.target;
            if (e.target.tagName === 'svg' || e.target.tagName === 'path') {
                const closestButton = e.target.closest('button');
                if (closestButton) {
                    targetElement = closestButton;
                }
            }

            if (targetElement.classList.contains('add-array-item')) {
                this.addArrayItem(targetElement.dataset.field);
            } else if (targetElement.classList.contains('remove-array-item')) {
                this.removeArrayItem(targetElement.closest('.array-item'));
            } else if (targetElement.classList.contains('add-category-btn')) {
                if (this.schemas[this.currentSection].type === 'dynamic-key-value-list') {
                    this.addCategory();
                }
            } else if (targetElement.classList.contains('remove-category-btn')) {
                if (this.schemas[this.currentSection].type === 'dynamic-key-value-list') {
                    this.removeCategory(targetElement.closest('.key-value-item'));
                }
            } else if (targetElement.classList.contains('password-toggle')) {
                this.togglePasswordVisibility(targetElement.dataset.target);
            } else if (targetElement.classList.contains('add-complex-object-item-btn')) {
                this.addComplexObjectItem();
            } else if (targetElement.classList.contains('remove-complex-object-item')) {
                this.removeComplexObjectItem(targetElement.dataset.key);
            } else if (targetElement.id === 'reset-section-btn') {
                this.resetSection();
            } else if (targetElement.id === 'validate-section-btn') {
                this.validateSection();
            } else if (targetElement.classList.contains('apply-to-all-btn')) {
                e.preventDefault();
                e.stopPropagation();
                const action = targetElement.dataset.action;
                if (action === 'apply-to-all') {
                    this.applyToAllWebhooks();
                }
            }
        });
    }

    handleInputChange(e) {
        // Ignore events from section headers
        if (e.target.classList.contains('section-subheader')) {
            return;
        }

        // Handle category key/value inputs specifically, only if the current section is a dynamic-key-value-list
        if ((e.target.classList.contains('category-key') || e.target.classList.contains('category-value')) &&
            this.schemas[this.currentSection].type === 'dynamic-key-value-list') {
            this.updateCategoryValue(e.target);
            return; // Exit after handling category specific logic
        }

        // Handle dynamic_select_text field changes
        if (e.target.classList.contains('dynamic-select')) {
            this.handleDynamicSelectChange(e.target);
            return;
        }

        // Handle complex object key input specifically
        if (e.target.classList.contains('complex-object-key')) {
            this.updateComplexObjectKey(e.target);
            return; // Exit after handling complex object key specific logic
        }

        const fieldName = e.target.name || e.target.dataset.field;
        if (!fieldName) {
            return;
        }



        // Check if this is a complex object field (e.g., "trackerKey::propName")
        const isComplexObjectField = fieldName.includes('::');
        let entryKey, propName;
        if (isComplexObjectField) {
            [entryKey, propName] = fieldName.split('::');

        }

        let value;

        if (e.target.type === 'checkbox') {
            value = e.target.checked;
        } else if (e.target.type === 'number') {
            value = e.target.value ? parseFloat(e.target.value) : null;
        } else if (e.target.classList.contains('array-item-input')) {
            // Extract base fieldName (e.g., "trackerKey::propName") and index from name (e.g., "trackerKey::propName[index]")
            const fullFieldName = e.target.name;
            const match = fullFieldName.match(/(.*)\[(\d+)\]$/);
            if (match) {
                const baseFieldName = match[1]; // e.g., "animebytes.tv::tag"
                const index = match[2];        // e.g., "0"
                this.updateArrayValue(baseFieldName, index, e.target.value);
            } else {
                // Fallback if name doesn't match expected array format (shouldn't happen if form-renderer is correct)
                this.updateArrayValue(fieldName, e.target.dataset.index, e.target.value);
            }
            return;
        } else {
            value = e.target.value;
        }

        if (isComplexObjectField) {
            if (!this.currentData[entryKey]) {
                this.currentData[entryKey] = {};
            }
            this.currentData[entryKey][propName] = value;
        } else {

            // Handle complex object fields (containing ::) directly
            if (fieldName.includes('::')) {
                const [entryKey, propName] = fieldName.split('::');
                if (!this.currentData[entryKey]) {
                    this.currentData[entryKey] = {};
                }

                // Remove empty string values instead of setting them
                if (value === '' || value === null || value === undefined) {
                    delete this.currentData[entryKey][propName];
                    // If the entry object is now empty, remove it entirely
                    if (Object.keys(this.currentData[entryKey]).length === 0) {
                        delete this.currentData[entryKey];
                    }
                } else {
                    this.currentData[entryKey][propName] = value;
                }
            } else {
                // For regular fields, remove empty values instead of setting them
                if (value === '' || value === null || value === undefined) {
                    // Use the existing setNestedValue logic to delete the field
                    setNestedValue(this.currentData, fieldName, null);
                } else {
                    setNestedValue(this.currentData, fieldName, value);
                }
            }
        }



        this.onDataChange(this.currentData);
        this.validateField(fieldName, value);

        // Dispatch an event to notify that the form section is dirty
        this._dispatchDirtyEvent();
    }

    _dispatchDirtyEvent() {
        const dirtyEvent = new CustomEvent('form-dirty', {
            detail: { section: this.currentSection },
            bubbles: true,
            composed: true
        });
        this.container.dispatchEvent(dirtyEvent);
    }

    updateArrayValue(fieldName, index, value) {

        // Check if this is a complex object field (e.g., "trackerKey::propName")
        const isComplexObjectField = fieldName.includes('::');
        let currentArray;

        if (isComplexObjectField) {
            const [entryKey, propName] = fieldName.split('::');


            if (!this.currentData[entryKey]) {
                this.currentData[entryKey] = {};
            }
            currentArray = this.currentData[entryKey][propName] || [];

            currentArray[parseInt(index)] = value;
            this.currentData[entryKey][propName] = currentArray;
        } else {
            // Handle complex object fields (containing ::) directly
            if (fieldName.includes('::')) {
                const [entryKey, propName] = fieldName.split('::');
                if (!this.currentData[entryKey]) {
                    this.currentData[entryKey] = {};
                }
                currentArray = this.currentData[entryKey][propName] || [];
                currentArray[parseInt(index)] = value;
                this.currentData[entryKey][propName] = currentArray;
            } else {
                currentArray = getNestedValue(this.currentData, fieldName) || [];
                currentArray[parseInt(index)] = value;
                setNestedValue(this.currentData, fieldName, currentArray);
            }
        }
        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    updateCategoryValue(input) {
        const item = input.closest('.key-value-item');
        const keyInput = item.querySelector('.category-key');
        const valueInput = item.querySelector('.category-value');

        const oldKey = item.dataset.key;
        const newKey = keyInput.value;
        const value = valueInput.value;

        if (!this.currentData) {
            this.currentData = {};
        }

        // Remove old key if changed
        if (oldKey && oldKey !== newKey) {
            delete this.currentData[oldKey];
        }

        // Set new value
        if (newKey) {
            this.currentData[newKey] = value;
            item.dataset.key = newKey;
        }

        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    addArrayItem(fieldName) {
        const arrayField = this.container.querySelector(`[data-field="${fieldName}"] .array-items`);
        let currentArray;

        // Handle complex object fields (containing ::) directly
        if (fieldName.includes('::')) {
            const [entryKey, propName] = fieldName.split('::');
            if (!this.currentData[entryKey]) {
                this.currentData[entryKey] = {};
            }
            currentArray = this.currentData[entryKey][propName] || [];
            const newIndex = currentArray.length;

            currentArray.push('');
            this.currentData[entryKey][propName] = currentArray;
        } else {
            currentArray = getNestedValue(this.currentData, fieldName) || [];
            const newIndex = currentArray.length;

            currentArray.push('');
            setNestedValue(this.currentData, fieldName, currentArray);
        }

        const newIndex = currentArray.length - 1;

        const itemHTML = `
            <div class="array-item" data-index="${newIndex}">
                <input type="text" class="form-input array-item-input"
                       value="" data-field="${fieldName}" data-index="${newIndex}">
                <button type="button" class="btn btn-icon btn-close-icon remove-array-item">
                    ${CLOSE_ICON_SVG}
                </button>
            </div>
        `;

        arrayField.insertAdjacentHTML('beforeend', itemHTML);
        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    removeArrayItem(item) {
        const fieldName = item.querySelector('.array-item-input').dataset.field;
        const index = parseInt(item.dataset.index);

        // Handle complex object fields (containing ::) directly
        if (fieldName.includes('::')) {
            const [entryKey, propName] = fieldName.split('::');
            if (!this.currentData[entryKey]) {
                this.currentData[entryKey] = {};
            }
            const currentArray = this.currentData[entryKey][propName] || [];
            currentArray.splice(index, 1);
            this.currentData[entryKey][propName] = currentArray;

        } else {
            const currentArray = getNestedValue(this.currentData, fieldName) || [];
            currentArray.splice(index, 1);
            setNestedValue(this.currentData, fieldName, currentArray);
        }

        item.remove();

        // Update indices for remaining items
        const arrayItems = this.container.querySelectorAll(`[data-field="${fieldName}"] .array-item`);
        arrayItems.forEach((arrayItem, newIndex) => {
            arrayItem.dataset.index = newIndex;
            const input = arrayItem.querySelector('.array-item-input');
            input.dataset.index = newIndex;
        });

        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    addCategory() {
        const categoriesContainer = this.container.querySelector('.key-value-items');
        const newKey = `category-${Date.now()}`;

        const itemHTML = `
            <div class="key-value-item category-row" data-key="${newKey}">
                <div class="category-inputs">
                    <div class="form-group category-name-group">
                        <label class="form-label">${this.currentSection === 'cat_change' ? 'Old Category' : 'Category Name'}</label>
                        <input type="text" class="form-input category-key" value=""
                               name="category-key-${newKey}">
                    </div>
                    <div class="form-group category-path-group">
                        <label class="form-label">${this.currentSection === 'cat_change' ? 'New Category' : 'Save Path'}</label>
                        <input type="text" class="form-input category-value"
                               value=""
                               placeholder="${this.currentSection === 'cat_change' ? 'New Category Name' : '/path/to/category'}"
                               name="category-value-${newKey}">
                    </div>
                </div>
                <button type="button" class="btn btn-icon btn-close-icon remove-category-btn">
                    ${CLOSE_ICON_SVG}
                </button>
            </div>
        `;

        categoriesContainer.insertAdjacentHTML('beforeend', itemHTML);

        if (!this.currentData) {
            this.currentData = {};
        }
        this.currentData[newKey] = '';

        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    removeCategory(item) {
        const key = item.dataset.key;
        if (this.currentData && key) {
            delete this.currentData[key];
        }
        item.remove();
        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    async applyToAllWebhooks() {
        // Get the selected value from the dropdown
        const valueField = this.container.querySelector('[name="apply_to_all_value"]');
        if (!valueField) {
            showToast('Could not find apply to all value field', 'error');
            return;
        }

        let value;
        if (valueField.value === 'custom') {
            // Only show one prompt for custom URL
            const customUrl = prompt('Enter custom webhook URL:');
            if (customUrl === null) return;
            value = customUrl;
        } else {
            value = valueField.value;
        }

        // Combine both regular and function webhooks
        const fields = [
            'webhooks.error',
            'webhooks.run_start',
            'webhooks.run_end',
            'webhooks.function.recheck',
            'webhooks.function.cat_update',
            'webhooks.function.tag_update',
            'webhooks.function.rem_unregistered',
            'webhooks.function.rem_orphaned',
            'webhooks.function.tag_nohardlinks',
            'webhooks.function.empty_recyclebin',
            'webhooks.function.tag_tracker_error',
            'webhooks.function.share_limits',
            'webhooks.function.cleanup_dirs'
        ];

        fields.forEach(field => {
            setNestedValue(this.currentData, field, value);
        });

        // Notify of data change and mark as dirty
        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();

        // Re-render the form to reflect changes
        await this.renderSection();
        showToast('Applied to all webhooks!', 'success');
    }

    async addComplexObjectItem() {
        const sectionConfig = this.schemas[this.currentSection];
        if (sectionConfig.type !== 'object' && sectionConfig.type !== 'complex-object') {
            console.error('addComplexObjectItem called for a non-object or non-complex-object schema type.');
            return;
        }

        const newKey = prompt('Enter the Tracker URL:');
        if (!newKey || this.currentData[newKey]) {
            if (this.currentData[newKey]) {
                showToast('A Tracker URL with this name already exists.', 'error');
            }
            return;
        }

        // Initialize with default values based on schema
        const newEntry = {};
        if (this.currentSection === 'nohardlinks') {
            newEntry.exclude_tags = [];
            newEntry.ignore_root_dir = true;
        } else {
            const defaultSchema = sectionConfig.additionalProperties || sectionConfig.patternProperties["^(?!other$).*$"];
            if (defaultSchema && defaultSchema.properties) {
                Object.entries(defaultSchema.properties).forEach(([propName, propSchema]) => {
                    if (propSchema.default !== undefined) {
                        newEntry[propName] = propSchema.default;
                    } else if (propSchema.type === 'array') {
                        newEntry[propName] = [];
                    } else if (propSchema.oneOf) { // For 'tag' field
                        const stringSchema = propSchema.oneOf.find(s => s.type === 'string');
                        if (stringSchema && stringSchema.default !== undefined) {
                            newEntry[propName] = stringSchema.default;
                        } else {
                            newEntry[propName] = ''; // Default to empty string for 'tag'
                        }
                    } else {
                        newEntry[propName] = ''; // Default to empty string for other types
                    }
                });
            }
        }

        this.currentData[newKey] = newEntry;
        await this.renderSection(); // Re-render to show the new item
        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    async removeComplexObjectItem(keyToRemove) {
        if (confirm(`Are you sure you want to remove the entry "${keyToRemove}"?`)) {
            delete this.currentData[keyToRemove];
            await this.renderSection(); // Re-render to remove the item
            this.onDataChange(this.currentData);
            this._dispatchDirtyEvent();
        }
    }

    updateComplexObjectKey(input) {
        const item = input.closest('.complex-object-item');
        const originalKey = input.dataset.originalKey;
        const newKey = input.value;

        if (originalKey === newKey) return;

        if (this.currentData[newKey]) {
            showToast('An entry with this key already exists. Please choose a different key.', 'error');
            input.value = originalKey; // Revert input
            return;
        }

        // Create a new object with the updated key
        const updatedData = {};
        Object.entries(this.currentData).forEach(([key, value]) => {
            if (key === originalKey) {
                updatedData[newKey] = value;
            } else {
                updatedData[key] = value;
            }
        });
        this.currentData = updatedData;
        item.dataset.key = newKey; // Update data-key attribute
        input.dataset.originalKey = newKey; // Update original-key dataset

        this.onDataChange(this.currentData);
        this._dispatchDirtyEvent();
    }

    togglePasswordVisibility(targetId) {
        const input = get(targetId);
        const button = query(`[data-target="${targetId}"]`);

        if (!input) {
            console.error('Password input not found:', targetId);
            return;
        }

        if (!button) {
            console.error('Password toggle button not found for input:', targetId);
            return;
        }



        if (input.type === 'password') {
            input.type = 'text';
            button.innerHTML = EYE_SLASH_ICON_SVG;

        } else {
            input.type = 'password';
            button.innerHTML = EYE_ICON_SVG;

        }
    }

    handleDynamicSelectChange(selectElement) {
        const container = selectElement.closest('.dynamic-select-text-group');
        if (!container) {
            return;
        }

        const textInput = container.querySelector('.dynamic-text-input');
        const hiddenInput = container.querySelector('.dynamic-hidden-input');

        if (!textInput || !hiddenInput) {
            console.log('Missing inputs:', { textInput, hiddenInput });
            return;
        }

        const updateValue = () => {
            if (selectElement.value === 'webhook') {
                textInput.style.display = 'block';
                textInput.required = true;
                hiddenInput.value = textInput.value;
            } else {
                textInput.style.display = 'none';
                textInput.required = false;
                textInput.value = '';
                hiddenInput.value = selectElement.value;
            }
        };

        // Update the display and values
        updateValue();

        // Add input listener to text field if not already added
        if (!textInput.hasAttribute('data-listener-added')) {
            textInput.addEventListener('input', () => {
                if (selectElement.value === 'webhook') {
                    hiddenInput.value = textInput.value;
                }
            });
            textInput.setAttribute('data-listener-added', 'true');
        }

        // Trigger form change event for the hidden input
        const changeEvent = new Event('input', { bubbles: true });
        hiddenInput.dispatchEvent(changeEvent);
    }

    resetSection() {
        if (confirm('Are you sure you want to reset this section? All changes will be lost.')) {
            this.currentData = JSON.parse(JSON.stringify(this.originalData)); // Revert to original data
            this.loadSection(this.currentSection, this.originalData); // Load section with original data
            this.onDataChange(this.currentData);

            // Dispatch an event to notify that the form section has been reset
            const resetEvent = new CustomEvent('form-reset', {
                detail: { section: this.currentSection },
                bubbles: true,
                composed: true
            });
            this.container.dispatchEvent(resetEvent);
        }
    }

    /**
     * Preprocesses complex object data to ensure array fields (like 'tag') are always arrays.
     * @param {string} sectionName - The name of the current section.
     * @param {object} data - The raw data loaded for the section.
     * @returns {object} The preprocessed data.
     */
    _preprocessComplexObjectData(sectionName, data) {
        const processedData = JSON.parse(JSON.stringify(data)); // Deep copy to avoid modifying original data

        // Skip preprocessing for multi-root-object sections
        const sectionConfig = this.schemas[sectionName];
        if (sectionConfig && sectionConfig.type === 'multi-root-object') {
            return processedData;
        }

        if (sectionConfig && sectionConfig.type === 'fixed-object-config') {
            const mainFieldName = sectionConfig.fields[0]?.name;
            const mainFieldProperties = sectionConfig.fields[0]?.properties || {};
            const sectionData = data[mainFieldName] || {};

            if (sectionName === 'nohardlinks') {
                if (Array.isArray(sectionData)) {
                    // Handle array format: ["RadarrComplete", "RadarrComplete4k", ...]
                    const newNohardlinksCategories = {};
                    sectionData.forEach(categoryItem => {
                        if (typeof categoryItem === 'string') {
                            // Simple string category name
                            newNohardlinksCategories[categoryItem] = {
                                exclude_tags: [],
                                ignore_root_dir: true
                            };
                        } else if (typeof categoryItem === 'object') {
                            // Object with category name as key and properties as value
                            // Format: [{ "RadarrComplete": { exclude_tags: [...], ignore_root_dir: true } }]
                            for (const [categoryName, categoryProps] of Object.entries(categoryItem)) {
                                newNohardlinksCategories[categoryName] = {
                                    exclude_tags: categoryProps?.exclude_tags || [],
                                    ignore_root_dir: categoryProps?.ignore_root_dir !== undefined ? categoryProps.ignore_root_dir : true
                                };
                            }
                        }
                    });
                    processedData[mainFieldName] = newNohardlinksCategories;
                } else if (typeof sectionData === 'object' && sectionData !== null) {
                    // Handle object format: { "RadarrComplete": { ... }, ... }
                    const newNohardlinksCategories = {};
                    Object.entries(sectionData).forEach(([categoryName, categoryProps]) => {
                        newNohardlinksCategories[categoryName] = {
                            exclude_tags: categoryProps?.exclude_tags || [],
                            ignore_root_dir: categoryProps?.ignore_root_dir !== undefined ? categoryProps.ignore_root_dir : true
                        };
                    });
                    processedData[mainFieldName] = newNohardlinksCategories;
                }
            } else if (mainFieldName) {
                 // For other fixed-object-config sections, iterate through properties
                 Object.entries(sectionData).forEach(([entryKey, entryValue]) => {
                    const entryProperties = mainFieldProperties[entryKey]?.properties;
                    if (entryProperties) {
                        Object.entries(entryValue).forEach(([propName, propValue]) => {
                            if (entryProperties[propName]?.type === 'array' && !Array.isArray(propValue)) {
                                processedData[mainFieldName][entryKey][propName] = propValue ? [propValue] : [];
                            }
                        });
                    }
                });
            }
        } else if (sectionConfig && sectionConfig.type === 'complex-object' && sectionConfig.patternProperties) {
            // This is for sections like 'tracker'
            Object.entries(processedData).forEach(([entryKey, entryValue]) => {
                if (entryValue && typeof entryValue === 'object') {
                    // Find the matching schema for the current entry
                    let schemaProperties;
                    if (entryKey === 'other' && sectionConfig.patternProperties.other) {
                        schemaProperties = sectionConfig.patternProperties.other.properties;
                    } else if (sectionConfig.patternProperties["^(?!other$).*$"]) {
                        schemaProperties = sectionConfig.patternProperties["^(?!other$).*$"].properties;
                    } else if (sectionConfig.patternProperties[".*"]) {
                        schemaProperties = sectionConfig.patternProperties[".*"].properties;
                    }

                    if (schemaProperties) {
                        Object.entries(schemaProperties).forEach(([propName, propSchema]) => {
                            if (propSchema.type === 'array' && !Array.isArray(entryValue[propName])) {
                                entryValue[propName] = entryValue[propName] ? [entryValue[propName]] : [];
                            } else if (propSchema.oneOf) { // Handle fields like 'tag'
                                const isArray = propSchema.oneOf.some(s => s.type === 'array');
                                if (isArray && !Array.isArray(entryValue[propName])) {
                                    entryValue[propName] = entryValue[propName] ? [entryValue[propName]] : [];
                                }
                            }
                        });
                    }
                }
            });
        }

        return processedData;
    }

    _postprocessDataForSave(sectionName, data) {
        const sectionConfig = this.schemas[sectionName];
        if (sectionConfig && sectionConfig.type === 'multi-root-object') {
            const finalData = {};
            Object.keys(data).forEach(key => {
                // Filter out UI-only fields for notifications section
                if (sectionName === 'notifications' && key === 'apply_to_all_value') {
                    return; // Skip this field
                }
                this._setNestedValue(finalData, key, data[key]);
            });
            return finalData;
        }

        const processedData = { ...data };

        // Filter out UI-only fields for notifications section
        if (sectionName === 'notifications') {
            delete processedData.apply_to_all_value;
        }

        if (sectionName === 'nohardlinks' && processedData._originalNohardlinksFormat === 'array' && typeof processedData.nohardlinks_categories === 'object') {
            processedData.nohardlinks_categories = Object.keys(processedData.nohardlinks_categories);
        }
        delete processedData._originalNohardlinksFormat;
        return processedData;
    }

    /**
     * Helper method to flatten nested objects into dot notation
     * @param {object} obj - The object to flatten
     * @param {string} prefix - The prefix for the keys
     * @param {object} result - The result object to populate
     */
    _flattenObject(obj, prefix, result) {
        Object.keys(obj).forEach(key => {
            const value = obj[key];
            const newKey = prefix ? `${prefix}.${key}` : key;

            if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
                // Recursively flatten nested objects
                this._flattenObject(value, newKey, result);
            } else {
                // Set the flattened key-value pair
                result[newKey] = value;
            }
        });
    }

    /**
     * Helper method to set nested values in an object using dot notation
     * @param {object} obj - The target object
     * @param {string} path - The dot notation path (e.g., 'function.cat_update')
     * @param {*} value - The value to set
     */
    _setNestedValue(obj, path, value) {
        const parts = path.split('.');
        let current = obj;

        for (let i = 0; i < parts.length - 1; i++) {
            const part = parts[i];
            // If the current part doesn't exist, create a new object
            if (!current[part]) {
                current[part] = {};
            }
            // If the current part exists but is not an object, preserve the existing value
            else if (typeof current[part] !== 'object' || current[part] === null) {
                // Save the existing value under a special key
                current[part] = {
                    _value: current[part]
                };
            }
            current = current[part];
        }

        current[parts[parts.length - 1]] = value;
    }

    /**
     * Recursively removes empty strings, empty objects, and empty arrays from a configuration object.
     * @param {object} obj - The object to clean up.
     * @returns {object} The cleaned up object.
     */
    cleanupEmptyValues(obj) {
        if (obj === null || obj === undefined) {
            return null;
        }
        if (typeof obj !== 'object') {
            return obj;
        }

        if (Array.isArray(obj)) {
            const newArr = obj
                .map(v => this.cleanupEmptyValues(v))
                .filter(v => v !== null && v !== '' && (!Array.isArray(v) || v.length > 0));
            return newArr.length > 0 ? newArr : null;
        }

        const newObj = {};
        for (const key in obj) {
            if (Object.prototype.hasOwnProperty.call(obj, key)) {
                // Skip internal properties and UI-only fields
                if (key === '_originalNohardlinksFormat' || key === 'apply_to_all_value') continue;

                const value = this.cleanupEmptyValues(obj[key]);

                // Special handling for notification sections - preserve them even if they appear empty
                // This ensures that sections like 'notifiarr', 'apprise', 'webhooks' are not removed
                if (['notifiarr', 'apprise', 'webhooks'].includes(key)) {
                    // Always preserve these sections, even if they appear empty
                    newObj[key] = value || {};
                } else if (value !== null && value !== '' && (!Array.isArray(value) || value.length > 0)) {
                    newObj[key] = value;
                }
            }
        }

        // Don't return null for empty objects if they contain notification sections
        // or if this might be a root-level config object
        const hasNotificationSections = ['notifiarr', 'apprise', 'webhooks'].some(section => section in newObj);
        if (hasNotificationSections || Object.keys(newObj).length > 0) {
            return newObj;
        }

        return null;
    }

    validateSection() {
        const sectionConfig = this.schemas[this.currentSection];
        this.validationState = { valid: true, errors: [], warnings: [] };

        if (!sectionConfig) {
            this.updateValidationDisplay();
            return;
        }

        // We will validate the entire currentData object, as some sections
        // are nested (e.g., nohardlinks.nohardlinks_categories)
        const dataToValidate = this.currentData;

        (sectionConfig.fields || []).forEach(field => {
            this.validateField(field.name, getNestedValue(dataToValidate, field.name));
        });

        // Specific validation for complex object types
        if (sectionConfig.type === "complex-object") {
            // Find properties to validate
        }

        this.onValidationChange(this.validationState);
        this.updateValidationDisplay();

        if (this.validationState.errors.length === 0) {
            showToast('Section is valid!', 'success');
        }
    }

    validateField(fieldName, value) {
        // This is a simplified validation logic.
        // A more robust implementation would deeply check the schema.
        const sectionConfig = this.schemas[this.currentSection];
        if (!sectionConfig) return;

        let fieldSchema;
        if (sectionConfig.type === 'fixed-object-config') {
            // For schemas like nohardlinks, the fields are under a nested property
            const mainFieldName = sectionConfig.fields[0]?.name;
            const mainFieldProperties = sectionConfig.fields[0]?.properties || {};
            // This is still not quite right for deeply nested fields.
            // For now, let's assume simple structure within fixed-object-config
            fieldSchema = mainFieldProperties[fieldName];
        } else {
            fieldSchema = sectionConfig.fields?.find(f => f.name === fieldName);
        }

        if (fieldSchema && fieldSchema.required && (value === null || value === undefined || value === '')) {
            const error = `Field "${fieldSchema.label}" is required.`;
            if (!this.validationState.errors.includes(error)) {
                this.validationState.errors.push(error);
            }
            this.validationState.valid = false;
        }

        // Example custom validation for qbt host
        if (this.currentSection === 'qbt' && fieldName === 'host' && value && !isValidHost(value)) {
            const error = `Invalid host format for "${fieldName}". Should be http(s)://hostname:port.`;
            if (!this.validationState.errors.includes(error)) {
                this.validationState.errors.push(error);
            }
             this.validationState.valid = false;
        }
    }

    updateValidationDisplay() {
        // Clear previous messages
        queryAll('.field-validation').forEach(el => el.textContent = '');
        const sectionValidationEl = this.container.querySelector('.section-validation');
        if (sectionValidationEl) {
            sectionValidationEl.innerHTML = '';
        }

        if (this.validationState.errors.length > 0) {
            const errorList = this.validationState.errors.map(err => `<li>${err}</li>`).join('');
            if (sectionValidationEl) {
                sectionValidationEl.innerHTML = `<div class="alert alert-error"><ul>${errorList}</ul></div>`;
            }
        }

         if (this.validationState.warnings.length > 0) {
            const warningList = this.validationState.warnings.map(warn => `<li>${warn}</li>`).join('');
            if (sectionValidationEl) {
                sectionValidationEl.innerHTML += `<div class="alert alert-warning"><ul>${warningList}</ul></div>`;
            }
        }
    }
}

export { ConfigForm };
