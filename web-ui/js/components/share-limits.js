/**
 * Share Limits Component
 * Handles the specialized Share Limits configuration interface with drag-and-drop and modal editing
 */

import { showModal, hideModal } from '../utils/modal.js';
import { showToast } from '../utils/toast.js';
import { get, query, queryAll } from '../utils/dom.js';
import { generateFieldHTML, generateShareLimitsHTML } from '../utils/form-renderer.js';
import { shareLimitsSchema } from '../config-schemas/share_limits.js';

export class ShareLimitsComponent {
    constructor(container, data = {}, onDataChange = () => {}) {
        this.container = container;
        this.data = data;
        this.onDataChange = onDataChange;
        this.draggedElement = null;
        this.schema = shareLimitsSchema.fields[0].properties; // Get the properties schema

        // Clean up any existing modals before initializing
        this.closeExistingModals();

        this.init();
    }

    init() {
        this.bindEvents();
        this.initializeSortable();
    }

    bindEvents() {
        // Add new group button
        this.container.addEventListener('click', (e) => {
            if (e.target.classList.contains('add-share-limit-group-btn')) {
                this.addNewGroup();
            }
        });

        // Remove group button
        this.container.addEventListener('click', (e) => {
            if (e.target.closest('.remove-share-limit-group')) {
                const key = e.target.closest('.remove-share-limit-group').dataset.key;
                this.removeGroup(key);
            }
        });

        // Edit group (click on group content)
        this.container.addEventListener('click', (e) => {
            if (e.target.closest('.share-limit-group-content') && !e.target.closest('.remove-share-limit-group')) {
                const key = e.target.closest('.share-limit-group-content').dataset.key;
                this.editGroup(key);
            }
        });
    }

    initializeSortable() {
        const sortableList = this.container.querySelector('#share-limits-sortable');
        if (!sortableList) return;

        // Add drag event listeners to all group items
        this.updateDragListeners();
    }

    updateDragListeners() {
        const groupItems = this.container.querySelectorAll('.share-limit-group-item');

        groupItems.forEach(item => {
            const handle = item.querySelector('.share-limit-group-handle');

            // Remove existing listeners
            handle.removeEventListener('mousedown', this.handleMouseDown);

            // Add new listeners
            handle.addEventListener('mousedown', (e) => this.handleMouseDown(e, item));

            // Make items draggable
            item.draggable = true;
            item.addEventListener('dragstart', (e) => this.handleDragStart(e, item));
            item.addEventListener('dragover', (e) => this.handleDragOver(e));
            item.addEventListener('drop', (e) => this.handleDrop(e, item));
            item.addEventListener('dragend', (e) => this.handleDragEnd(e));
        });
    }

    handleMouseDown(e, item) {
        e.preventDefault();
        this.draggedElement = item;
    }

    handleDragStart(e, item) {
        this.draggedElement = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', item.outerHTML);
    }

    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        // Create placeholder if it doesn't exist
        if (!this.placeholder) {
            this.placeholder = document.createElement('div');
            this.placeholder.classList.add('share-limit-group-placeholder');
            this.container.querySelector('#share-limits-sortable').appendChild(this.placeholder);
        }

        // Find closest item to mouse position
        const container = this.container.querySelector('#share-limits-sortable');
        const items = Array.from(container.querySelectorAll('.share-limit-group-item:not(.dragging)'));
        const mouseY = e.clientY;

        let closestItem = null;
        let closestOffset = Number.NEGATIVE_INFINITY;

        items.forEach(item => {
            const rect = item.getBoundingClientRect();
            const offset = mouseY - rect.top - rect.height / 2;

            if (offset < 0 && offset > closestOffset) {
                closestOffset = offset;
                closestItem = item;
            }
        });

        // Position placeholder before closest item or at end
        if (closestItem) {
            container.insertBefore(this.placeholder, closestItem);
        } else {
            container.appendChild(this.placeholder);
        }

        // Highlight potential drop targets
        items.forEach(item => {
            item.classList.remove('drop-target');
        });
        if (closestItem) {
            closestItem.classList.add('drop-target');
        }
    }

    handleDrop(e, targetItem) {
        e.preventDefault();

        // Remove placeholder and drop target highlights
        if (this.placeholder && this.placeholder.parentNode) {
            this.placeholder.parentNode.removeChild(this.placeholder);
        }
        this.placeholder = null;
        this.container.querySelectorAll('.share-limit-group-item').forEach(item => {
            item.classList.remove('drop-target');
        });

        if (this.draggedElement) {
            // If placeholder exists, drop before it
            if (this.placeholder) {
                const container = this.placeholder.parentNode;
                container.insertBefore(this.draggedElement, this.placeholder);
                container.removeChild(this.placeholder);
            }
            // Otherwise use existing logic
            else if (this.draggedElement !== targetItem) {
                const container = targetItem.parentNode;
                const draggedIndex = Array.from(container.children).indexOf(this.draggedElement);
                const targetIndex = Array.from(container.children).indexOf(targetItem);

                if (draggedIndex < targetIndex) {
                    container.insertBefore(this.draggedElement, targetItem.nextSibling);
                } else {
                    container.insertBefore(this.draggedElement, targetItem);
                }
            }

            this.updatePriorities();
        }
    }

    handleDragEnd(e) {
        e.target.classList.remove('dragging');
        this.draggedElement = null;

        // Clean up placeholder if exists
        if (this.placeholder && this.placeholder.parentNode) {
            this.placeholder.parentNode.removeChild(this.placeholder);
        }
        this.placeholder = null;

        // Remove drop target highlights
        this.container.querySelectorAll('.share-limit-group-item').forEach(item => {
            item.classList.remove('drop-target');
        });
    }

    updatePriorities() {
        const groupItems = this.container.querySelectorAll('.share-limit-group-item');
        const newData = { ...this.data };

        groupItems.forEach((item, index) => {
            const key = item.dataset.key;
            if (newData[key]) {
                newData[key].priority = index + 1;
                // Update the display
                const priorityElement = item.querySelector('.share-limit-group-priority');
                if (priorityElement) {
                    priorityElement.textContent = `Priority: ${index + 1}`;
                }
            }
        });

        this.data = newData;
        this.onDataChange(this.data);
    }

    async addNewGroup() {
        const groupName = await this.promptForGroupName();
        if (!groupName) return;

        if (this.data[groupName]) {
            showToast('A group with this name already exists', 'error');
            return;
        }

        // Find the next available priority
        const priorities = Object.values(this.data).map(group => group.priority || 999);
        const nextPriority = priorities.length > 0 ? Math.max(...priorities) + 1 : 1;

        const newGroup = {
            priority: nextPriority,
            max_ratio: -1,
            max_seeding_time: '-1',
            max_last_active: '-1',
            min_seeding_time: '0',
            min_last_active: '0',
            limit_upload_speed: -1,
            enable_group_upload_speed: false,
            cleanup: false,
            resume_torrent_after_change: true,
            add_group_to_tag: true,
            min_num_seeds: 0,
            custom_tag: '',
            include_all_tags: [],
            include_any_tags: [],
            exclude_all_tags: [],
            exclude_any_tags: [],
            categories: []
        };

        this.data[groupName] = newGroup;
        this.onDataChange(this.data);
        this.refreshDisplay();

        // Open the edit modal for the new group
        setTimeout(() => this.editGroup(groupName), 100);
    }

    async promptForGroupName() {
        return new Promise((resolve) => {
            const modalContent = `
                <div class="form-group">
                    <label for="group-name-input" class="form-label">Group Name</label>
                    <input type="text" id="group-name-input" class="form-input" placeholder="Enter group name" autofocus>
                </div>
            `;

            showModal('Add New Share Limit Group', modalContent, {
                confirmText: 'Create',
                cancelText: 'Cancel'
            }).then((confirmed) => {
                if (confirmed) {
                    const input = document.getElementById('group-name-input');
                    const value = input ? input.value.trim() : '';
                    resolve(value || null);
                } else {
                    resolve(null);
                }
            });
        });
    }

    removeGroup(key) {
        if (confirm(`Are you sure you want to remove the "${key}" share limit group?`)) {
            delete this.data[key];
            this.onDataChange(this.data);
            this.refreshDisplay();
            showToast(`Share limit group "${key}" removed`, 'success');
        }
    }

    async editGroup(key) {
        const groupData = this.data[key];
        if (!groupData) return;

        // Remove any existing modals first to prevent conflicts
        this.closeExistingModals();

        const modalContent = this.generateGroupEditForm(groupData);
        const modalId = `share-limit-edit-modal-${Date.now()}`;

        const modalElement = document.createElement('div');
        modalElement.innerHTML = `
            <div class="modal-overlay share-limit-modal" id="${modalId}">
                <div class="modal">
                    <div class="modal-header">
                        <h3>Edit Share Limit Group: ${key}</h3>
                        <button type="button" class="btn btn-icon modal-close-btn">
                            <svg class="icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                        </button>
                    </div>
                    <div class="modal-content">
                        ${modalContent}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary modal-cancel-btn">Cancel</button>
                        <button type="button" class="btn btn-primary modal-save-btn">Save Changes</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modalElement);

        // Show modal
        const modal = modalElement.querySelector('.modal-overlay');
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.remove('hidden'), 10);

        // Bind modal events
        this.bindModalEvents(modalElement, key, groupData);
    }

    closeExistingModals() {
        // Remove any existing share limit modals
        const existingModals = document.querySelectorAll('.share-limit-modal');
        existingModals.forEach(modal => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        });
    }

    bindModalEvents(modalElement, key, originalData) {
        const modal = modalElement.querySelector('.modal-overlay');
        const modalDialog = modalElement.querySelector('.modal');
        const closeBtn = modalElement.querySelector('.modal-close-btn');
        const cancelBtn = modalElement.querySelector('.modal-cancel-btn');
        const saveBtn = modalElement.querySelector('.modal-save-btn');

        const closeModal = () => {
            modal.classList.add('hidden');
            setTimeout(() => {
                if (modalElement.parentNode) {
                    modalElement.parentNode.removeChild(modalElement);
                }
            }, 300);
        };

        // Ensure buttons exist before adding event listeners
        if (closeBtn) {
            closeBtn.addEventListener('click', closeModal);
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', closeModal);
        }

        // Click outside to close
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                const formData = this.collectFormData(modalElement);

                // Validate priority uniqueness
                const newPriority = formData.priority;
                const priorityError = this.validatePriorityUniqueness(newPriority, key);
                if (priorityError) {
                    showToast(priorityError, 'error');
                    return;
                }

                // Validate share limits configuration
                const shareLimitsError = this.validateShareLimitsConfiguration(formData);
                if (shareLimitsError) {
                    showToast(shareLimitsError, 'error');
                    return;
                }

                // Filter out empty values and default values before saving
                const filteredData = this.filterFormData(formData);

                // Start with a clean object and only add non-default, non-empty values
                const cleanedData = {};

                // Always preserve priority as it's required
                cleanedData.priority = filteredData.priority || formData.priority || originalData.priority || 1;

                // Add other filtered values
                Object.keys(filteredData).forEach(fieldKey => {
                    if (fieldKey !== 'priority') {
                        cleanedData[fieldKey] = filteredData[fieldKey];
                    }
                });

                this.data[key] = cleanedData;
                this.onDataChange(this.data);
                closeModal();

                // Refresh display after modal is closed to avoid timing issues
                setTimeout(() => {
                    this.refreshDisplay();
                    showToast(`Share limit group "${key}" updated`, 'success');
                }, 350); // Wait for modal close animation to complete
            });
        }

        // FIX: Add checkbox change event listener to prevent modal collapse
        const enableGroupUploadSpeedCheckbox = modalElement.querySelector('input[name="enable_group_upload_speed"]');
        if (enableGroupUploadSpeedCheckbox) {
            enableGroupUploadSpeedCheckbox.addEventListener('change', (e) => {
                // Prevent modal collapse by stabilizing layout after checkbox change
                modalDialog.style.minHeight = modalDialog.offsetHeight + 'px';

                // Reset after a brief moment to allow natural sizing
                setTimeout(() => {
                    modalDialog.style.minHeight = '400px';
                }, 100);
            });
        }

        // Handle array field events
        this.bindArrayFieldEvents(modalElement);
    }

    collectFormData(modalElement) {
        const formData = {};
        const inputs = modalElement.querySelectorAll('input, select, textarea');

        // Collect array field names to avoid duplicates
        const arrayFieldNames = new Set();
        const arrayFields = modalElement.querySelectorAll('.array-field');
        arrayFields.forEach(arrayField => {
            arrayFieldNames.add(arrayField.dataset.field);
        });

        inputs.forEach(input => {
            const name = input.name;
            if (!name) return;

            // Skip individual array inputs (they have [index] notation) - we'll handle arrays separately
            if (name.includes('[') && name.includes(']')) {
                return;
            }

            // Skip if this is an array field that we'll handle separately
            if (arrayFieldNames.has(name)) {
                return;
            }

            if (input.type === 'checkbox') {
                formData[name] = input.checked;
            } else if (input.type === 'number') {
                formData[name] = input.value ? parseFloat(input.value) : (input.dataset.default ? parseFloat(input.dataset.default) : 0);
            } else {
                formData[name] = input.value || input.dataset.default || '';
            }
        });

        // Handle array fields separately
        arrayFields.forEach(arrayField => {
            const fieldName = arrayField.dataset.field;
            const items = arrayField.querySelectorAll('.array-item-input');
            const arrayValues = Array.from(items)
                .map(item => item.value.trim())
                .filter(value => value.length > 0);

            // Include array fields (filtering will happen later in filterFormData)
            formData[fieldName] = arrayValues;
        });

        return formData;
    }

    filterFormData(formData) {
        // Define default values based on the schema and YAML config
        const defaultValues = {
            priority: 999,
            max_ratio: -1,
            cleanup: false,
            max_seeding_time: '-1',
            resume_torrent_after_change: true,
            add_group_to_tag: true,
            max_last_active: '-1',
            min_seeding_time: '0',
            min_last_active: '0',
            min_num_seeds: 0,
            limit_upload_speed: -1,
            enable_group_upload_speed: false,
            custom_tag: '',
            include_all_tags: [],
            include_any_tags: [],
            exclude_all_tags: [],
            exclude_any_tags: [],
            categories: []
        };

        const filteredData = {};

        Object.keys(formData).forEach(key => {
            const value = formData[key];
            const defaultValue = defaultValues[key];

            // Skip if value is empty
            if (this.isEmptyValue(value)) {
                return;
            }

            // Skip if value equals default value
            if (this.isDefaultValue(value, defaultValue)) {
                return;
            }

            // Include the value if it's not empty and not default
            filteredData[key] = value;
        });

        return filteredData;
    }

    isEmptyValue(value) {
        // Check for empty strings
        if (typeof value === 'string' && value.trim() === '') {
            return true;
        }

        // Check for empty arrays
        if (Array.isArray(value) && value.length === 0) {
            return true;
        }

        return false;
    }

    isDefaultValue(value, defaultValue) {
        // Handle array comparison
        if (Array.isArray(value) && Array.isArray(defaultValue)) {
            return value.length === defaultValue.length &&
                   value.every((val, index) => val === defaultValue[index]);
        }

        // Handle primitive value comparison
        return value === defaultValue;
    }

    validatePriorityUniqueness(newPriority, currentKey) {
        // Check if the priority is already used by another group
        for (const [groupKey, groupData] of Object.entries(this.data)) {
            if (groupKey !== currentKey && groupData.priority === newPriority) {
                return `Priority ${newPriority} is already used by group "${groupKey}". Please choose a different priority.`;
            }
        }
        return null; // No error
    }

    validateShareLimitsConfiguration(formData) {
        // Helper function to parse time values and convert to minutes
        const parseTimeToMinutes = (timeStr) => {
            if (!timeStr || timeStr === '' || timeStr === '-1' || timeStr === '-2' || timeStr === '0') {
                return timeStr === '0' ? 0 : -1;
            }

            // Parse time format like "32m", "2h32m", "3d2h32m", "1w3d2h32m"
            const timeRegex = /^(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$/;
            const match = timeStr.trim().match(timeRegex);

            if (!match || (!match[1] && !match[2] && !match[3] && !match[4])) {
                // If it's just a number, treat it as minutes
                const numValue = parseInt(timeStr);
                return isNaN(numValue) ? 0 : numValue;
            }

            const weeks = parseInt(match[1]) || 0;
            const days = parseInt(match[2]) || 0;
            const hours = parseInt(match[3]) || 0;
            const minutes = parseInt(match[4]) || 0;

            return weeks * 7 * 24 * 60 + days * 24 * 60 + hours * 60 + minutes;
        };

        // Get values from form data
        const minSeedingTimeStr = formData.min_seeding_time || '0';
        const maxSeedingTimeStr = formData.max_seeding_time || '-1';
        const maxRatio = parseFloat(formData.max_ratio);

        // Parse time values
        const minSeedingTime = parseTimeToMinutes(minSeedingTimeStr);
        const maxSeedingTime = parseTimeToMinutes(maxSeedingTimeStr);

        console.log('Validation Debug:', {
            minSeedingTimeStr,
            maxSeedingTimeStr,
            maxRatio,
            minSeedingTime,
            maxSeedingTime
        });

        // Rule 1: If min_seeding_time > 0, then max_ratio must be > 0
        if (minSeedingTime > 0 && (isNaN(maxRatio) || maxRatio <= 0)) {
            return 'MANDATORY: When minimum seeding time is greater than 0, maximum share ratio must also be set to a value greater than 0.';
        }

        // Rule 2: If both min_seeding_time and max_seeding_time are used, max_seeding_time must be greater than min_seeding_time
        if (minSeedingTime > 0 && maxSeedingTime > 0 && maxSeedingTime <= minSeedingTime) {
            return 'Maximum seeding time must be greater than minimum seeding time when both are specified.';
        }

        return null; // No error
    }

    bindArrayFieldEvents(modalElement) {
        // Add array item buttons
        modalElement.addEventListener('click', (e) => {
            if (e.target.classList.contains('add-array-item')) {
                const fieldName = e.target.dataset.field;
                const arrayField = modalElement.querySelector(`.array-field[data-field="${fieldName}"]`);
                const itemsContainer = arrayField.querySelector('.array-items');
                const newIndex = itemsContainer.children.length;

                const newItem = document.createElement('div');
                newItem.className = 'array-item';
                newItem.innerHTML = `
                    <div class="array-item-input-group">
                        <input type="text" class="form-input array-item-input" value="" data-field="${fieldName}" data-index="${newIndex}" name="${fieldName}[${newIndex}]">
                        <button type="button" class="btn btn-icon btn-close-icon remove-array-item">
                            <svg class="icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                        </button>
                    </div>
                `;

                itemsContainer.appendChild(newItem);
            }
        });

        // Remove array item buttons
        modalElement.addEventListener('click', (e) => {
            if (e.target.closest('.remove-array-item')) {
                const arrayItem = e.target.closest('.array-item');
                arrayItem.remove();
            }
        });
    }

    generateGroupEditForm(groupData) {
        const sections = [
            {
                title: 'Basic Configuration',
                fields: ['priority', 'cleanup', 'resume_torrent_after_change', 'add_group_to_tag']
            },
            {
                title: 'Share Limits',
                fields: ['max_ratio', 'max_seeding_time', 'max_last_active', 'min_seeding_time', 'min_last_active', 'min_num_seeds']
            },
            {
                title: 'Upload Speed Limits',
                fields: ['limit_upload_speed', 'enable_group_upload_speed']
            },
            {
                title: 'Tag Filters',
                fields: ['include_all_tags', 'include_any_tags', 'exclude_all_tags', 'exclude_any_tags']
            },
            {
                title: 'Category Filters',
                fields: ['categories']
            },
            {
                title: 'Advanced',
                fields: ['custom_tag']
            }
        ];

        let html = '';

        sections.forEach(section => {
            html += `<div class="form-section">`;
            html += `<h4 class="form-section-title">${section.title}</h4>`;

            section.fields.forEach(fieldName => {
                const fieldSchema = this.schema[fieldName];
                if (!fieldSchema) return;

                const value = groupData[fieldName] ?? fieldSchema.default ?? '';
                html += this.generateModalFieldHTML(fieldSchema, value, fieldName);
            });

            html += `</div>`;
        });

        return html;
    }

    generateModalFieldHTML(field, value, fieldName) {
        const fieldId = `modal-field-${fieldName}`;
        const isRequired = field.required ? 'required' : '';
        const requiredMark = field.required ? '<span class="required-mark">*</span>' : '';

        let inputHTML = '';

        switch (field.type) {
            case 'boolean':
                inputHTML = `
                    <label class="checkbox-label">
                        <input type="checkbox" id="${fieldId}" name="${fieldName}"
                               ${value === true ? 'checked' : ''} class="form-checkbox">
                        <span class="checkmark"></span>
                        ${field.label}
                    </label>
                `;
                break;

            case 'number':
                inputHTML = `
                    <label for="${fieldId}" class="form-label ${isRequired}">
                        ${field.label} ${requiredMark}
                    </label>
                    <input type="number" id="${fieldId}" name="${fieldName}"
                           class="form-input" value="${value}"
                           ${field.min !== undefined ? `min="${field.min}"` : ''}
                           ${field.max !== undefined ? `max="${field.max}"` : ''}
                           ${field.step !== undefined ? `step="${field.step}"` : ''}
                           data-default="${field.default || ''}"
                           ${isRequired}>
                `;
                break;

            case 'array':
                const arrayValue = Array.isArray(value) ? value : [];
                inputHTML = `
                    <label class="form-label ${isRequired}">
                        ${field.label} ${requiredMark}
                    </label>
                    <div class="array-field" data-field="${fieldName}">
                        <div class="array-items">
                `;

                arrayValue.forEach((item, index) => {
                    inputHTML += `
                        <div class="array-item" data-index="${index}">
                            <div class="array-item-input-group">
                                <input type="text" class="form-input array-item-input"
                                       value="${item}" data-field="${fieldName}" data-index="${index}"
                                       name="${fieldName}[${index}]">
                                <button type="button" class="btn btn-icon btn-close-icon remove-array-item">
                                    <svg class="icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                                </button>
                            </div>
                        </div>
                    `;
                });

                inputHTML += `
                        </div>
                        <button type="button" class="btn btn-secondary add-array-item"
                                data-field="${fieldName}">
                            Add Item
                        </button>
                    </div>
                `;
                break;

            default: // text
                inputHTML = `
                    <label for="${fieldId}" class="form-label ${isRequired}">
                        ${field.label} ${requiredMark}
                    </label>
                    <input type="text" id="${fieldId}" name="${fieldName}"
                           class="form-input" value="${value}"
                           data-default="${field.default || ''}"
                           ${field.placeholder ? `placeholder="${field.placeholder}"` : ''}
                           ${isRequired}>
                `;
                break;
        }

        return `
            <div class="form-group" data-field="${fieldName}">
                ${inputHTML}
                ${field.description ? `<div class="form-help">${field.description}</div>` : ''}
            </div>
        `;
    }

    refreshDisplay() {
        // Re-render the entire component with updated data
        this.updateHTML();
    }

    updateHTML() {
        // Close any existing modals before updating HTML
        this.closeExistingModals();

        // Generate new HTML with current data
        const newHTML = generateShareLimitsHTML({ type: 'share-limits-config' }, this.data);

        // Update the container's innerHTML
        this.container.innerHTML = newHTML;

        // Re-initialize event listeners and sortable functionality
        this.bindEvents();
        this.initializeSortable();
    }
}
