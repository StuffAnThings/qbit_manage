/**
 * Share Limits Component - Modernized
 * Handles the specialized Share Limits configuration interface with enhanced drag-and-drop and modal editing
 * Features: Modern animations, improved UX, better accessibility, and enhanced visual feedback
 */

import { showModal } from '../utils/modal.js';
import { showToast } from '../utils/toast.js';
import { generateShareLimitsHTML } from '../utils/form-renderer.js';
import { shareLimitsSchema } from '../config-schemas/share_limits.js';
import { getAvailableCategories, generateCategoryDropdownHTML } from '../utils/categories.js';

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
        this.addModernEnhancements();
    }

    addModernEnhancements() {
        // Add smooth scroll behavior for better UX
        if (this.container.querySelector('.share-limits-list')) {
            this.container.querySelector('.share-limits-list').style.scrollBehavior = 'smooth';
        }

        // Add keyboard navigation support
        this.addKeyboardSupport();

        // Add modern loading states
        this.addLoadingStates();
    }

    addKeyboardSupport() {
        this.container.addEventListener('keydown', (e) => {
            const focusedItem = document.activeElement.closest('.share-limit-group-item');
            if (!focusedItem) return;

            switch (e.key) {
                case 'Enter':
                case ' ':
                    e.preventDefault();
                    const key = focusedItem.querySelector('.share-limit-group-content').dataset.key;
                    this.editGroup(key);
                    break;
                case 'Delete':
                case 'Backspace':
                    e.preventDefault();
                    const deleteKey = focusedItem.querySelector('.remove-share-limit-group').dataset.key;
                    this.removeGroup(deleteKey);
                    break;
                case 'ArrowUp':
                case 'ArrowDown':
                    e.preventDefault();
                    this.navigateItems(focusedItem, e.key === 'ArrowUp' ? -1 : 1);
                    break;
            }
        });
    }

    navigateItems(currentItem, direction) {
        const items = Array.from(this.container.querySelectorAll('.share-limit-group-item'));
        const currentIndex = items.indexOf(currentItem);
        const nextIndex = currentIndex + direction;

        if (nextIndex >= 0 && nextIndex < items.length) {
            items[nextIndex].focus();
        }
    }

    addLoadingStates() {
        // Add loading state management for async operations
        this.isLoading = false;
    }

    setLoadingState(loading) {
        this.isLoading = loading;
        const addButton = this.container.querySelector('.add-share-limit-group-btn');
        if (addButton) {
            addButton.disabled = loading;
            addButton.innerHTML = loading ?
                '<span class="loading-spinner"></span> Creating...' :
                'Add New Group';
        }
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
            // Skip if click originated from drag handle
            if (e.target.closest('.share-limit-group-handle')) return;

            if (e.target.closest('.share-limit-group-content') && !e.target.closest('.remove-share-limit-group')) {
                const key = e.target.closest('.share-limit-group-content').dataset.key;
                this.editGroup(key);
            }
        });
    }

    initializeSortable() {
        const sortableList = this.container.querySelector('#share-limits-sortable');
        if (!sortableList) return;

        this.updateDragListeners();
    }

    updateDragListeners() {
        const groupItems = this.container.querySelectorAll('.share-limit-group-item');

        groupItems.forEach((item, index) => {
            // Make the handle draggable
            const handle = item.querySelector('.share-limit-group-handle');
            if (handle) {
                handle.setAttribute('draggable', 'true');
                handle.setAttribute('aria-label', 'Drag handle to reorder');

                // Add touch events for mobile drag support
                handle.addEventListener('touchstart', e => this.handleTouchStart(e, item), { passive: false });
                handle.addEventListener('touchmove', e => this.handleTouchMove(e, item), { passive: false });
                handle.addEventListener('touchend', e => this.handleTouchEnd(e, item), { passive: false });
            }

            // Set accessibility attributes on the item (remove tabindex to prevent mobile selection)
            item.removeAttribute('tabindex');
            item.setAttribute('role', 'listitem');
            item.setAttribute('aria-label', `Share limit group ${index + 1}. Press Enter to edit, Delete to remove.`);

            // Add all drag event listeners to the handle
            handle.addEventListener('dragstart', e => this.handleDragStart(e, item));

            // Add listeners to the item for drop zone behavior
            item.addEventListener('dragover', e => this.handleDragOver(e, item));
            item.addEventListener('dragleave', e => this.handleDragLeave(e, item));
            item.addEventListener('drop', e => this.handleDrop(e, item));
            item.addEventListener('dragend', e => this.handleDragEnd(e, item));
        });
    }

    handleDragStart(e, item) {
        this.draggedElement = item;
        // Use a timeout to avoid the dragged element disappearing
        setTimeout(() => item.classList.add('dragging'), 0);

        e.dataTransfer.effectAllowed = 'move';
        // You can set drag data, though we'll rely on the `this.draggedElement` reference
        e.dataTransfer.setData('text/plain', item.dataset.key);
    }

    handleDragOver(e, item) {
        e.preventDefault();

        // Add a class for visual feedback
        item.classList.add('drag-over');

        const container = this.container.querySelector('#share-limits-sortable');
        const afterElement = this.getDragAfterElement(container, e.clientY);

        // Insert the dragged element at the new position
        if (afterElement == null) {
            container.appendChild(this.draggedElement);
        } else {
            container.insertBefore(this.draggedElement, afterElement);
        }
    }

    handleDragLeave(e, item) {
        // Remove visual feedback when leaving a potential drop zone
        item.classList.remove('drag-over');
    }

    handleDrop(e, item) {
        e.preventDefault();
        item.classList.remove('drag-over');
        // The reordering is handled in `dragover`, so we just need to update priorities
        this.updatePriorities();
    }

    handleDragEnd(e, item) {
        // Always remove the dragging class to restore visibility
        this.draggedElement.classList.remove('dragging');

        // Clean up any remaining drag-over classes
        this.container.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));

        // Final priority update
        this.updatePriorities();
        this.draggedElement = null;
    }

    // Touch event handlers for mobile drag support
    handleTouchStart(e, item) {
        e.preventDefault();
        this.draggedElement = item;
        this.touchStartY = e.touches[0].clientY;
        this.touchStartX = e.touches[0].clientX;
        this.isDragging = false;

        // Add visual feedback
        setTimeout(() => item.classList.add('dragging'), 0);

        // Store initial position
        this.initialTouchPosition = {
            x: e.touches[0].clientX,
            y: e.touches[0].clientY
        };
    }

    handleTouchMove(e, item) {
        if (!this.draggedElement) return;

        e.preventDefault();

        const touch = e.touches[0];
        const deltaY = Math.abs(touch.clientY - this.touchStartY);
        const deltaX = Math.abs(touch.clientX - this.touchStartX);

        // Only start dragging if moved more than 10px vertically
        if (deltaY > 10 && deltaY > deltaX) {
            this.isDragging = true;

            const container = this.container.querySelector('#share-limits-sortable');
            const afterElement = this.getDragAfterElement(container, touch.clientY);

            // Insert the dragged element at the new position
            if (afterElement == null) {
                container.appendChild(this.draggedElement);
            } else {
                container.insertBefore(this.draggedElement, afterElement);
            }
        }
    }

    handleTouchEnd(e, item) {
        if (!this.draggedElement) return;

        // If we were dragging, update priorities
        if (this.isDragging) {
            this.updatePriorities();
        }

        // Clean up
        this.draggedElement.classList.remove('dragging');
        this.container.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));

        this.draggedElement = null;
        this.isDragging = false;
        this.touchStartY = null;
        this.touchStartX = null;
    }

    getDragAfterElement(container, y) {
        const draggableElements = [...container.querySelectorAll('.share-limit-group-item:not(.dragging)')];

        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            // Calculate the midpoint of the item
            const offset = y - box.top - box.height / 2;

            // We are looking for the element we are hovering over
            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            } else {
                return closest;
            }
        }, { offset: Number.NEGATIVE_INFINITY }).element;
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
        if (this.isLoading) return;

        this.setLoadingState(true);

        try {
            const groupName = await this.promptForGroupName();
            if (!groupName) {
                this.setLoadingState(false);
                return;
            }

            if (this.data[groupName]) {
                showToast('A group with this name already exists', 'error');
                this.setLoadingState(false);
                return;
            }

            // Find the next available priority
            const priorities = Object.values(this.data).map(group => group.priority || 999);
            const nextPriority = priorities.length > 0 ? Math.max(...priorities) + 1 : 1;

            // Create empty group - defaults will be applied when user saves
            // Only set priority as it's needed for ordering
            const newGroup = {
                priority: nextPriority
            };

            this.data[groupName] = newGroup;
            this.onDataChange(this.data);

            // Add smooth animation for new group
            await this.refreshDisplayWithAnimation();

            // Show success message
            showToast(`Share limit group "${groupName}" created successfully`, 'success');

            // Open the edit modal for the new group with a slight delay for better UX
            setTimeout(() => this.editGroup(groupName), 300);

        } catch (error) {
            console.error('Error adding new group:', error);
            showToast('Failed to create new group', 'error');
        } finally {
            this.setLoadingState(false);
        }
    }

    async refreshDisplayWithAnimation() {
        return new Promise((resolve) => {
            // Add fade-out animation
            this.container.style.opacity = '0.7';
            this.container.style.transform = 'scale(0.98)';
            this.container.style.transition = 'all 0.2s ease';

            setTimeout(() => {
                this.refreshDisplay();

                // Add fade-in animation
                this.container.style.opacity = '1';
                this.container.style.transform = 'scale(1)';

                setTimeout(resolve, 200);
            }, 100);
        });
    }

    async promptForGroupName() {
        return new Promise((resolve) => {
            const modalContent = `
                <div class="form-group">
                    <label for="group-name-input" class="form-label">Group Name</label>
                    <div class="floating-label-group">
                        <input type="text" id="group-name-input" class="form-input"
                               placeholder=" " autofocus maxlength="50"
                               pattern="[a-zA-Z0-9_\\-]+"
                               title="Only letters, numbers, underscores, and hyphens are allowed">
                        <label for="group-name-input" class="floating-label">Enter a unique group name</label>
                    </div>
                    <div class="form-help">
                        <span class="material-icons" style="font-size: 16px; vertical-align: middle;">info</span>
                        Use descriptive names like "High Priority", "Long Term", or "Quick Seed"
                    </div>
                </div>
            `;

            showModal('🎯 Add New Share Limit Group', modalContent, {
                confirmText: 'Create Group',
                cancelText: 'Cancel',
                className: 'modern-modal'
            }).then((confirmed) => {
                if (confirmed) {
                    const input = document.getElementById('group-name-input');
                    const value = input ? input.value.trim() : '';

                    // Validate input
                    if (value && !/^[a-zA-Z0-9_-]+$/.test(value)) {
                        showToast('Group name can only contain letters, numbers, underscores, and hyphens', 'error');
                        resolve(null);
                        return;
                    }

                    resolve(value || null);
                } else {
                    resolve(null);
                }
            });

            // Add real-time validation
            setTimeout(() => {
                const input = document.getElementById('group-name-input');
                if (input) {
                    input.addEventListener('input', (e) => {
                        const value = e.target.value;
                        const isValid = /^[a-zA-Z0-9_-]*$/.test(value);

                        if (!isValid && value) {
                            e.target.style.borderColor = 'var(--error)';
                            e.target.style.boxShadow = '0 0 0 3px rgba(239, 68, 68, 0.1)';
                        } else {
                            e.target.style.borderColor = '';
                            e.target.style.boxShadow = '';
                        }
                    });
                }
            }, 100);
        });
    }

    removeGroup(key) {
        // Create a modern confirmation dialog
        const modalContent = `
            <div class="confirmation-dialog">
                <div class="confirmation-icon">
                    <span class="material-icons" style="font-size: 48px; color: var(--warning);">warning</span>
                </div>
                <div class="confirmation-message">
                    <h4>Remove Share Limit Group</h4>
                    <p>Are you sure you want to remove the <strong>"${key}"</strong> share limit group?</p>
                    <p class="warning-text">
                        <span class="material-icons" style="font-size: 16px; vertical-align: middle;">info</span>
                        This action cannot be undone and will affect any torrents currently using this configuration.
                    </p>
                </div>
            </div>
        `;

        showModal('⚠️ Confirm Removal', modalContent, {
            confirmText: 'Remove Group',
            cancelText: 'Keep Group',
            className: 'danger-modal',
            confirmClass: 'btn-danger'
        }).then((confirmed) => {
            if (confirmed) {
                // Add removal animation
                const groupItem = this.container.querySelector(`[data-key="${key}"]`)?.closest('.share-limit-group-item');
                if (groupItem) {
                    groupItem.style.transition = 'all 0.3s ease';
                    groupItem.style.opacity = '0';
                    groupItem.style.transform = 'translateX(-100%) scale(0.8)';

                    setTimeout(() => {
                        delete this.data[key];
                        this.onDataChange(this.data);
                        this.refreshDisplay();
                        showToast(`Share limit group "${key}" removed successfully`, 'success');
                    }, 300);
                } else {
                    delete this.data[key];
                    this.onDataChange(this.data);
                    this.refreshDisplay();
                    showToast(`Share limit group "${key}" removed successfully`, 'success');
                }
            }
        });
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
                        <button type="button" class="btn btn-icon modal-close-btn btn-close-icon">
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

                // Check if this is a new group (only has priority field)
                const originalData = this.data[key];
                const isNewGroup = Object.keys(originalData).length === 1 && originalData.priority !== undefined;

                let cleanedData;

                if (isNewGroup) {
                    // For new groups, apply defaults for empty fields
                    cleanedData = this.applyDefaultsForNewGroup(formData);
                } else {
                    // For existing groups, filter out empty values and default values
                    const filteredData = this.filterFormData(formData);

                    // Start with a clean object and only add non-default, non-empty values
                    cleanedData = {};

                    // Always preserve priority as it's required
                    cleanedData.priority = filteredData.priority || formData.priority || originalData.priority || 1;

                    // Add other filtered values
                    Object.keys(filteredData).forEach(fieldKey => {
                        if (fieldKey !== 'priority') {
                            cleanedData[fieldKey] = filteredData[fieldKey];
                        }
                    });
                }

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

    applyDefaultsForNewGroup(formData) {
        // For new groups: priority always included, other fields only if non-default

        // Define all possible fields with their default values for comparison
        const allFieldDefaults = {
            priority: 1, // This will be overridden by form value which has the correct calculated priority
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

        const processedData = {};

        // Process each field
        Object.keys(allFieldDefaults).forEach(key => {
            const formValue = formData[key];

            if (key === 'priority') {
                // Priority always gets included (required for functionality)
                processedData[key] = formValue || allFieldDefaults[key];
            } else {
                // All other fields: only include if user provided a non-default value
                if (!this.isEmptyValue(formValue) && formValue !== undefined) {
                    const defaultValue = allFieldDefaults[key];
                    // Only include if the value is different from the default
                    if (formValue !== defaultValue &&
                        !(Array.isArray(formValue) && Array.isArray(defaultValue) && formValue.length === 0 && defaultValue.length === 0)) {
                        processedData[key] = formValue;
                    }
                }
                // Don't include the field at all if it's empty or matches default
            }
        });

        return processedData;
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
                const shouldUseCategoryDropdown = arrayField.dataset.useCategoryDropdown === 'true';

                const newItem = document.createElement('div');
                newItem.className = 'array-item modern-array-item';
                newItem.dataset.index = newIndex;

                if (shouldUseCategoryDropdown) {
                    const categories = getAvailableCategories();
                    const dropdownHTML = generateCategoryDropdownHTML(
                        `${fieldName}[${newIndex}]`,
                        '',
                        categories,
                        `form-input array-item-input`,
                        fieldName,
                        newIndex
                    );
                    newItem.innerHTML = `
                        <div class="array-item-input-group">
                            ${dropdownHTML}
                            <button type="button" class="btn btn-icon btn-close-icon remove-array-item"
                                    aria-label="Remove item">
                                <span class="material-icons">close</span>
                            </button>
                        </div>
                    `;
                } else {
                    newItem.innerHTML = `
                        <div class="array-item-input-group">
                            <input type="text" class="form-input array-item-input" value="" data-field="${fieldName}" data-index="${newIndex}" name="${fieldName}[${newIndex}]">
                            <button type="button" class="btn btn-icon btn-close-icon remove-array-item">
                                <svg class="icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                            </button>
                        </div>
                    `;
                }

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

                // For new groups (only have priority field), pre-populate basic configuration with defaults
                const isNewGroup = Object.keys(groupData).length === 1 && groupData.priority !== undefined;

                // Define which fields should get defaults for new groups (basic configuration)
                const basicConfigFields = ['priority', 'cleanup', 'resume_torrent_after_change', 'add_group_to_tag'];

                let value;
                if (isNewGroup) {
                    // For new groups: pre-populate basic configuration fields with defaults, leave others blank
                    if (basicConfigFields.includes(fieldName)) {
                        if (fieldName === 'priority') {
                            // Use the priority that was already calculated and set in addGroup
                            value = groupData.priority;
                        } else {
                            // Use schema defaults for other basic fields
                            value = fieldSchema.default ?? '';
                        }
                    } else {
                        // All other fields start blank for new groups
                        value = '';
                    }
                } else {
                    // For existing groups: use current value or default
                    value = groupData[fieldName] ?? fieldSchema.default ?? '';
                }
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
        let fieldIcon = this.getFieldIcon(fieldName);

        switch (field.type) {
            case 'boolean':
                inputHTML = `
                    <div class="modern-checkbox-wrapper">
                        <label class="modern-checkbox-label">
                            <input type="checkbox" id="${fieldId}" name="${fieldName}"
                                   ${value === true || value === 'true' ? 'checked' : ''} class="modern-checkbox">
                            <span class="checkbox-text">
                                ${fieldIcon} ${field.label}
                            </span>
                        </label>
                    </div>
                `;
                break;

            case 'number':
                inputHTML = `
                    <div class="floating-label-group">
                        <input type="number" id="${fieldId}" name="${fieldName}"
                               class="form-input modern-input" ${value !== '' ? `value="${value}"` : ''} placeholder=" "
                               ${field.min !== undefined ? `min="${field.min}"` : ''}
                               ${field.max !== undefined ? `max="${field.max}"` : ''}
                               ${field.step !== undefined ? `step="${field.step}"` : ''}
                               data-default="${field.default || ''}"
                               ${isRequired}>
                        <label for="${fieldId}" class="floating-label">
                            ${fieldIcon} ${field.label} ${requiredMark}
                        </label>
                        <div class="input-icon">
                            <span class="material-icons">tag</span>
                        </div>
                    </div>
                `;
                break;

            case 'array':
                const arrayValue = Array.isArray(value) ? value : [];
                const shouldUseCategoryDropdown = field.items && field.items.useCategoryDropdown;

                inputHTML = `
                    <div class="array-field-wrapper">
                        <label class="form-label ${isRequired}">
                            ${fieldIcon} ${field.label} ${requiredMark}
                        </label>
                        <div class="array-field modern-array-field" data-field="${fieldName}" ${shouldUseCategoryDropdown ? 'data-use-category-dropdown="true"' : ''}>
                            <div class="array-items">
                `;

                arrayValue.forEach((item, index) => {
                    if (shouldUseCategoryDropdown) {
                        const categories = getAvailableCategories();
                        const dropdownHTML = generateCategoryDropdownHTML(
                            `${fieldName}[${index}]`,
                            item,
                            categories,
                            `form-input array-item-input`,
                            fieldName,
                            index
                        );
                        inputHTML += `
                            <div class="array-item modern-array-item" data-index="${index}">
                                <div class="array-item-input-group">
                                    ${dropdownHTML}
                                    <button type="button" class="btn btn-icon btn-close-icon remove-array-item"
                                            aria-label="Remove item">
                                        <span class="material-icons">close</span>
                                    </button>
                                </div>
                            </div>
                        `;
                    } else {
                        inputHTML += `
                            <div class="array-item modern-array-item" data-index="${index}">
                                <div class="array-item-input-group">
                                    <input type="text" class="form-input array-item-input"
                                           value="${item}" data-field="${fieldName}" data-index="${index}"
                                           name="${fieldName}[${index}]" placeholder="Enter value">
                                    <button type="button" class="btn btn-icon btn-close-icon remove-array-item"
                                            aria-label="Remove item">
                                        <span class="material-icons">close</span>
                                    </button>
                                </div>
                            </div>
                        `;
                    }
                });

                inputHTML += `
                            </div>
                            <button type="button" class="btn btn-secondary add-array-item modern-add-btn"
                                    data-field="${fieldName}">
                                <span class="material-icons">add</span>
                                Add Item
                            </button>
                        </div>
                    </div>
                `;
                break;

            default: // text
                inputHTML = `
                    <div class="floating-label-group">
                        <input type="text" id="${fieldId}" name="${fieldName}"
                               class="form-input modern-input" ${value !== '' ? `value="${value}"` : ''} placeholder=" "
                               data-default="${field.default || ''}"
                               ${isRequired}>
                        <label for="${fieldId}" class="floating-label">
                            ${fieldIcon} ${field.label} ${requiredMark}
                        </label>
                        <div class="input-icon">
                            <span class="material-icons">edit</span>
                        </div>
                    </div>
                `;
                break;
        }

        return `
            <div class="form-group modern-form-group" data-field="${fieldName}">
                ${inputHTML}
                ${field.description ? `<div class="form-help modern-form-help">
                    <span class="material-icons">info</span>
                    ${field.description}
                </div>` : ''}
            </div>
        `;
    }

    getFieldIcon(fieldName) {
        const iconMap = {
            'priority': '<span class="material-icons">priority_high</span>',
            'max_ratio': '<span class="material-icons">share</span>',
            'max_seeding_time': '<span class="material-icons">schedule</span>',
            'min_seeding_time': '<span class="material-icons">timer</span>',
            'limit_upload_speed': '<span class="material-icons">upload</span>',
            'cleanup': '<span class="material-icons">cleaning_services</span>',
            'categories': '<span class="material-icons">category</span>',
            'custom_tag': '<span class="material-icons">label</span>',
            'include_all_tags': '<span class="material-icons">check_circle</span>',
            'include_any_tags': '<span class="material-icons">radio_button_checked</span>',
            'exclude_all_tags': '<span class="material-icons">block</span>',
            'exclude_any_tags': '<span class="material-icons">remove_circle</span>',
            'min_num_seeds': '<span class="material-icons">group</span>',
            'enable_group_upload_speed': '<span class="material-icons">speed</span>',
            'resume_torrent_after_change': '<span class="material-icons">play_arrow</span>',
            'add_group_to_tag': '<span class="material-icons">add_circle</span>',
            'max_last_active': '<span class="material-icons">access_time</span>',
            'min_last_active': '<span class="material-icons">history</span>'
        };

        return iconMap[fieldName] || '<span class="material-icons">settings</span>';
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
