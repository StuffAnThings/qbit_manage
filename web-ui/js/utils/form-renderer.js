/**
 * Form Renderer Utility Module
 * Responsible for generating HTML forms based on schema definitions.
 */

import { getNestedValue } from './utils.js';
import { CLOSE_ICON_SVG } from './icons.js';
import { generateCategoryDropdownHTML } from './categories.js';

/**
 * Generates attributes to prevent password manager detection and autofill
 * Only applied to specific fields that cause performance issues
 * @param {string} inputType - The type of input ('password', 'text', etc.)
 * @returns {string} HTML attributes string
 */
function getPasswordManagerPreventionAttributes(inputType = 'text') {
    const attributes = [
        'autocomplete="off"',
        'data-lpignore="true"',
        'data-form-type="other"',
        'data-1p-ignore="true"',
        'data-bwignore="true"',
        'spellcheck="false"'
    ];

    // For password fields, use more specific autocomplete value
    if (inputType === 'password') {
        attributes[0] = 'autocomplete="new-password"';
    }

    return attributes.join(' ');
}

/**
 * Determines if a field should have password manager prevention attributes
 * Only applies to the specific fields that cause performance issues
 * @param {string} fieldName - The field name
 * @param {object} field - The field definition
 * @returns {boolean} Whether to apply prevention attributes
 */
function shouldPreventPasswordManager(fieldName, field) {
    if (!fieldName) return false;

    // Only these exact fields need password manager prevention
    const targetFields = [
        'notifiarr.apikey',  // Notifiarr API key (password field)
        'user',              // qBittorrent username (text field)
        'pass'               // qBittorrent password (password field)
    ];

    return targetFields.includes(fieldName);
}

/**
 * Generates the HTML for a given section.
 * @param {object} config - The configuration object for the section.
 * @param {object} data - The current data for the section.
 * @returns {string} The HTML string for the section.
 */
export function generateSectionHTML(config, data) {
    let html = `
        <div class="section-header">
            <h2 class="section-title">${config.title}</h2>
            <p class="section-description">${config.description || ''}</p>
        </div>
        <div class="section-content">
    `;

    if (config.type === 'dynamic-key-value-list') {
        // Process documentation fields first
        if (config.fields) {
            const docFields = config.fields.filter(field => field.type === 'documentation');
            html += generateFieldsHTML(docFields, data);
        }
        html += generateDynamicKeyValueListHTML(config, data);
    } else if (config.type === 'fixed-object-config') {
        // For fixed-object-config, render fields of the first (and usually only) field directly
        // The schema for fixed-object-config should have a single field which is an object
        const mainField = config.fields[0];
        html += generateFieldsHTML(Object.values(mainField.properties), data[mainField.name] || {}, mainField.name);
    } else if (config.type === 'share-limits-config') {
        // Process documentation fields first
        if (config.fields) {
            const docFields = config.fields.filter(field => field.type === 'documentation');
            html += generateFieldsHTML(docFields, data);
        }
        html += generateShareLimitsHTML(config, data);
    } else if (config.type === 'complex-object') {
        // Process documentation fields first
        if (config.fields) {
            const docFields = config.fields.filter(field => field.type === 'documentation');
            html += generateFieldsHTML(docFields, data);
        }
        html += generateComplexObjectHTML(config, data);
    } else if (config.type === 'multi-root-object') {
        // For multi-root-object, render fields directly without nesting under section name
        // Performance optimization for notifications section
        if (config.title === 'Notifications') {
            html += generateNotificationsFieldsHTML(config.fields, data);
        } else {
            html += generateFieldsHTML(config.fields, data);
        }
    } else {
        html += generateFieldsHTML(config.fields, data);
    }

    html += `
        </div>
        <div class="section-actions">
            <button type="button" class="btn btn-secondary" id="reset-section-btn">
                Reset Section
            </button>
        </div>
    `;

    return html;
}

/**
 * Generates HTML for a list of fields.
 * @param {Array<object>} fields - An array of field definitions.
 * @param {object} data - The current data for the section.
 * @param {string} [prefix=''] - Prefix for field names (for nested fields).
 * @returns {string} The HTML string for the fields.
 */
function generateFieldsHTML(fields, data, prefix = '') {
    return fields.map(field => {
        if (field.type === 'section_header') {
            return generateFieldHTML(field, null, null); // No value or fieldName needed for section_header
        }
        let fieldName, value;
        if (field.name) {
            fieldName = prefix ? `${prefix}.${field.name}` : field.name;
            value = getNestedValue(data, fieldName) ?? field.default ?? '';
        } else {
            fieldName = null;
            value = null;
        }

        return generateFieldHTML(field, value, fieldName);
    }).join('');
}

/**
 * Optimized field generation for notifications section to reduce DOM complexity
 * @param {Array<object>} fields - An array of field definitions.
 * @param {object} data - The current data for the section.
 * @returns {string} The HTML string for the fields.
 */
function generateNotificationsFieldsHTML(fields, data) {
    // Render fields in their original order to preserve documentation placement
    let html = '';
    let functionWebhooksFields = [];
    let inFunctionWebhooks = false;

    fields.forEach(field => {
        // Check if we're entering the Function Specific Webhooks section
        if (field.type === 'section_header' && field.label.includes('Function Specific')) {
            inFunctionWebhooks = true;
            // Start the lazy loading container for function webhooks
            html += `<div class="webhook-sections-container">`;
            html += `<div class="function-webhooks-lazy" data-section="function-webhooks">`;
            html += `<div class="lazy-load-placeholder">Click to load Function Specific Webhooks...</div>`;
            html += `<div class="lazy-content hidden">`;
        }

        if (inFunctionWebhooks) {
            // Collect function webhook fields for lazy loading
            functionWebhooksFields.push(field);
        } else {
            // Render field normally in original order
            if (field.type === 'section_header') {
                html += generateFieldHTML(field, null, null);
            } else {
                let fieldName, value;
                if (field.name) {
                    fieldName = field.name;
                    value = getNestedValue(data, fieldName) ?? field.default ?? '';
                } else {
                    fieldName = null;
                    value = null;
                }
                html += generateFieldHTML(field, value, fieldName);
            }
        }
    });

    // Render function webhooks in lazy loading container
    if (functionWebhooksFields.length > 0) {
        functionWebhooksFields.forEach(field => {
            if (field.type === 'section_header') {
                html += generateFieldHTML(field, null, null);
            } else {
                let fieldName, value;
                if (field.name) {
                    fieldName = field.name;
                    value = getNestedValue(data, fieldName) ?? field.default ?? '';
                } else {
                    fieldName = null;
                    value = null;
                }
                html += generateFieldHTML(field, value, fieldName);
            }
        });
        html += `</div></div></div>`;
    }

    return html;
}

/**
 * Renders a section of fields with performance optimizations
 */
function renderFieldSection(fields, data, sectionId) {
    if (!fields.length) return '';

    return `<div class="field-section" id="${sectionId}">` +
           fields.map(field => {
               if (field.type === 'section_header') {
                   return generateFieldHTML(field, null, null);
               }
               let fieldName, value;
               if (field.name) {
                   fieldName = field.name;
                   value = getNestedValue(data, fieldName) ?? field.default ?? '';
               } else {
                   fieldName = null;
                   value = null;
               }
               return generateFieldHTML(field, value, fieldName);
           }).join('') +
           `</div>`;
}

/**
 * Generates HTML for a single field.
 * @param {object} field - The field definition.
 * @param {*} value - The current value of the field.
 * @param {string} fieldName - The full name of the field (e.g., 'parent.child').
 * @returns {string} The HTML string for the field.
 */
export function generateFieldHTML(field, value, fieldName) {
    const fieldId = fieldName ? `field-${fieldName.replace(/\./g, '-')}` : '';
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

        case 'section_header':
            inputHTML = `
                <h3 class="section-subheader">${field.label}</h3>
            `;
            break;

        case 'documentation':
            // Create a placeholder div that will be replaced with the documentation component
            const docId = `doc-${Math.random().toString(36).substr(2, 9)}`;
            inputHTML = `<div id="${docId}" class="documentation-placeholder"
                              data-title="${field.title || 'Documentation'}"
                              data-file-path="${field.filePath || ''}"
                              data-section="${field.section || ''}"
                              data-heading-level="${field.headingLevel || 2}"
                              data-default-expanded="${field.defaultExpanded || false}"></div>`;

            // Schedule the documentation component creation for after DOM insertion
            setTimeout(() => {
                const placeholder = document.getElementById(docId);
                if (placeholder && window.DocumentationViewer) {
                    window.DocumentationViewer.createDocumentationSection({
                        title: placeholder.dataset.title,
                        filePath: placeholder.dataset.filePath,
                        section: placeholder.dataset.section || null,
                        headingLevel: parseInt(placeholder.dataset.headingLevel),
                        defaultExpanded: placeholder.dataset.defaultExpanded === 'true'
                    }).then(docSection => {
                        placeholder.parentNode.replaceChild(docSection, placeholder);
                    }).catch(error => {
                        console.error('Failed to create documentation section:', error);
                        placeholder.innerHTML = '<div class="documentation-error">Failed to load documentation</div>';
                    });
                }
            }, 100);
            break;

        case 'button':
            inputHTML = `
                <button type="button" class="btn btn-secondary apply-to-all-btn"
                        data-action="${field.action}">
                    ${field.label}
                </button>
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
                       ${field.placeholder ? `placeholder="${field.placeholder}"` : ''}
                       ${isRequired}>
            `;
            break;

        case 'password':
            // Import the eye icons at the top of the file
            const EYE_ICON_SVG = `<svg class="icon" viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>`;

            inputHTML = `
                <label for="${fieldId}" class="form-label ${isRequired}">
                    ${field.label} ${requiredMark}
                </label>
                <div class="password-input-group">
                    <input type="password" id="${fieldId}" name="${fieldName}"
                           class="form-input ${shouldPreventPasswordManager(fieldName, field) ? 'hide-password-toggle' : ''}" value="${value}"
                           ${field.placeholder ? `placeholder="${field.placeholder}"` : ''}
                           ${shouldPreventPasswordManager(fieldName, field) ? getPasswordManagerPreventionAttributes('password') : ''}
                           ${isRequired}>
                    <button type="button" class="btn btn-icon password-toggle"
                            data-target="${fieldId}">
                        ${EYE_ICON_SVG}
                    </button>
                </div>
            `;
            break;

        case 'select':
            const options = field.options || [];
            inputHTML = `
                <label for="${fieldId}" class="form-label ${isRequired}">
                    ${field.label} ${requiredMark}
                </label>
                <select id="${fieldId}" name="${fieldName}" class="form-select" ${isRequired}>
                    ${field.placeholder ? `<option value="">${field.placeholder}</option>` : ''}
                    ${options.map(option => {
                        const optionValue = typeof option === 'object' ? option.value : option;
                        const optionLabel = typeof option === 'object' ? option.label : option;
                        const selected = value === optionValue ? 'selected' : '';
                        return `<option value="${optionValue}" ${selected}>${optionLabel}</option>`;
                    }).join('')}
                </select>
            `;
            break;

        case 'dynamic_select_text':
            const selectOptions = field.options || ['apprise', 'notifiarr', 'webhook'];
            let selectedOption = '';
            let customValue = '';

            // Determine which option is selected based on the current value
            if (value === 'apprise' || value === 'notifiarr') {
                selectedOption = value;
            } else if (value && value !== '' && !['apprise', 'notifiarr'].includes(value)) {
                // If value is not empty and not one of the predefined options, it's a custom URL
                selectedOption = 'webhook';
                customValue = value;
            }

            inputHTML = `
                <label for="${fieldId}" class="form-label ${isRequired}">
                    ${field.label} ${requiredMark}
                </label>
                <div class="dynamic-select-text-group" data-field="${fieldName}">
                    <select id="${fieldId}" name="${fieldName}_type" class="form-select dynamic-select" ${isRequired}>
                        <option value="">Select type...</option>
                        ${selectOptions.map(option => {
                            const selected = selectedOption === option ? 'selected' : '';
                            const label = option === 'webhook' ? 'Custom URL' : option;
                            return `<option value="${option}" ${selected}>${label}</option>`;
                        }).join('')}
                    </select>
                    <input type="text" name="${fieldName}"
                           class="form-input dynamic-text-input"
                           value="${customValue}"
                           placeholder="Enter webhook URL"
                           id="${fieldId}_custom_url"
                           style="display: ${selectedOption === 'webhook' ? 'block' : 'none'}; margin-top: 8px;">
                   <input type="hidden" name="${fieldName}" value="${value}" class="dynamic-hidden-input">
                </div>
            `;


            break;

        case 'textarea':
            inputHTML = `
                <label for="${fieldId}" class="form-label ${isRequired}">
                    ${field.label} ${requiredMark}
                </label>
                <textarea id="${fieldId}" name="${fieldName}" class="form-textarea"
                          ${field.placeholder ? `placeholder="${field.placeholder}"` : ''}
                          ${field.rows ? `rows="${field.rows}"` : 'rows="4"'}
                          ${isRequired}>${value}</textarea>
            `;
            break;

        case 'array':
            inputHTML = generateArrayFieldHTML(field, value, fieldName);
            break;

        default: // text
            // Check if this field should use category dropdown
            if (field.useCategoryDropdown) {
                inputHTML = `
                    <label for="${fieldId}" class="form-label ${isRequired}">
                        ${field.label} ${requiredMark}
                    </label>
                    <select id="${fieldId}" name="${fieldName}" class="form-select category-dropdown" ${isRequired}>
                        <option value="${value}" selected>${value || 'Select Category'}</option>
                    </select>
                `;
            } else {
                inputHTML = `
                    <label for="${fieldId}" class="form-label ${isRequired}">
                        ${field.label} ${requiredMark}
                    </label>
                    <input type="text" id="${fieldId}" name="${fieldName}"
                           class="form-input" value="${value}"
                           ${field.placeholder ? `placeholder="${field.placeholder}"` : ''}
                           ${shouldPreventPasswordManager(fieldName, field) ? getPasswordManagerPreventionAttributes('text') : ''}
                           ${isRequired}>
                `;
            }
            break;
    }

    return `
        <div class="form-group" data-field="${fieldName}">
            ${inputHTML}
            ${field.description ? `<div class="form-help">${field.description}</div>` : ''}
            <div class="field-validation"></div>
        </div>
    `;
}

/**
 * Generates HTML for an array field.
 * @param {object} field - The field definition for the array.
 * @param {Array<string>} value - The current array values.
 * @param {string} fieldName - The full name of the array field.
 * @returns {string} The HTML string for the array field.
 */
function generateArrayFieldHTML(field, value, fieldName) {
    const fieldId = `field-${fieldName.replace(/\./g, '-')}`;
    const arrayValue = Array.isArray(value) ? value : [];
    const requiredMark = field.required ? '<span class="required-mark">*</span>' : '';

    let html = `
        <label class="form-label ${field.required ? 'required' : ''}">
            ${field.label} ${requiredMark}
        </label>
        <div class="array-field" data-field="${fieldName}">
            <div class="array-items">
    `;

    arrayValue.forEach((item, index) => {
        // Check if array items should use category dropdown
        const useDropdown = field.items && field.items.useCategoryDropdown;

        let inputHTML;
        if (useDropdown) {
            inputHTML = `
                <select class="form-select category-dropdown array-item-input"
                        id="${fieldId}-item-${index}"
                        data-field="${fieldName}" data-index="${index}"
                        name="${fieldName}[${index}]">
                    <option value="${item}" selected>${item || 'Select Category'}</option>
                </select>
            `;
        } else {
            inputHTML = `
                <input type="text" class="form-input array-item-input"
                       id="${fieldId}-item-${index}"
                       value="${item}" data-field="${fieldName}" data-index="${index}"
                       name="${fieldName}[${index}]">
            `;
        }

        html += `
            <div class="array-item" data-index="${index}">
                <label for="${fieldId}-item-${index}" class="form-label sr-only">Item ${index + 1}</label>
                <div class="array-item-input-group">
                    ${inputHTML}
                     <button type="button" class="btn btn-icon btn-close-icon remove-array-item">
                         ${CLOSE_ICON_SVG}
                    </button>
                </div>
            </div>
        `;
    });

    html += `
            </div>
            <button type="button" class="btn btn-secondary add-array-item"
                    data-field="${fieldName}">
                Add Item
            </button>
        </div>
    `;

    return html;
}

/**
 * Generates HTML for a key-value list (e.g., Categories, Category Changes).
 * @param {object} config - The section configuration.
 * @param {object} data - The current data for the section.
 * @returns {string} The HTML string for the key-value list.
 */
function generateDynamicKeyValueListHTML(config, data) {
    const categories = data || {};
    const isCatChange = config.title.includes('Category Change');

    let html = `
        <div class="key-value-list">
            <div class="key-value-header">
                <h3>${isCatChange ? 'Category Changes' : 'Categories'}</h3>
                <button type="button" class="btn btn-primary add-category-btn">
                    Add ${isCatChange ? 'Category Change' : 'Category'}
                </button>
            </div>
            <div class="key-value-items">
    `;

    Object.entries(categories).forEach(([key, value]) => {
        // Check if this config should use category dropdowns
        const useDropdownForKey = config.useCategoryDropdown && isCatChange;
        const useDropdownForValue = isCatChange && config.fields && config.fields[0] &&
                                   config.fields[0].properties && config.fields[0].properties.new_category &&
                                   config.fields[0].properties.new_category.useCategoryDropdown;

        let keyInputHTML, valueInputHTML;

        // Generate key input (old category)
        if (useDropdownForKey) {
            keyInputHTML = `
                <select class="form-select category-dropdown category-key" name="category-key-${key}">
                    <option value="${key}" selected>${key}</option>
                </select>
            `;
        } else {
            keyInputHTML = `
                <input type="text" class="form-input category-key" value="${key}"
                       name="category-key-${key}">
            `;
        }

        // Generate value input (new category or save path)
        if (useDropdownForValue) {
            valueInputHTML = `
                <select class="form-select category-dropdown category-value" name="category-value-${key}">
                    <option value="${value || ''}" selected>${value || 'Select Category'}</option>
                </select>
            `;
        } else {
            valueInputHTML = `
                <input type="text" class="form-input category-value"
                       value="${value || ''}"
                       placeholder="${isCatChange ? 'New Category Name' : '/path/to/category'}"
                       name="category-value-${key}">
            `;
        }

        html += `
            <div class="key-value-item category-row" data-key="${key}">
                <div class="category-inputs">
                    <div class="form-group category-name-group">
                        <label class="form-label">${isCatChange ? 'Old Category' : 'Category Name'}</label>
                        ${keyInputHTML}
                    </div>
                    <div class="form-group category-path-group">
                        <label class="form-label">${isCatChange ? 'New Category' : 'Save Path'}</label>
                        ${valueInputHTML}
                    </div>
                </div>
                <button type="button" class="btn btn-icon btn-close-icon remove-category-btn">
                    ${CLOSE_ICON_SVG}
                </button>
            </div>
        `;
    });

    html += `
            </div>
        </div>
    `;

    return html;
}

/**
 * Generates HTML for complex objects (currently a placeholder).
 * @param {object} config - The section configuration.
 * @param {object} data - The current data for the section.
 * @returns {string} The HTML string for the complex object.
 */
function generateComplexObjectHTML(config, data) {
    const complexObjectData = data || {};
    let html = `
        <div class="complex-object">
    `;

    // Documentation is now handled in generateSectionHTML, so we don't need to duplicate it here

    html += `
            <div class="complex-object-header">
                <h3>${config.title}</h3>
                <button type="button" class="btn btn-primary add-complex-object-item-btn">
                    Add New Entry
                </button>
            </div>
            <div class="complex-object-items">
    `;

    Object.entries(complexObjectData).forEach(([key, value]) => {
        html += generateComplexObjectEntryHTML(key, value, config);
    });

    html += `
            </div>
        </div>
    `;
    return html;
}

/**
 * Generates HTML for a single complex object entry (e.g., a tracker entry).
 * @param {string} entryKey - The key of the complex object entry (e.g., tracker URL).
 * @param {object} entryValue - The value object of the complex object entry (e.g., {tag, cat, notifiarr}).
 * @param {object} config - The schema configuration for the complex object.
 * @returns {string} The HTML string for the complex object entry.
 */
function generateComplexObjectEntryHTML(entryKey, entryValue, config) {

    const isOther = entryKey === 'other';

    // Handle flat string values (like categories: "category_name": "/path/to/save")
    if (config.flatStringValues && (typeof entryValue === 'string' || Array.isArray(entryValue))) {
        const keyLabel = config.keyLabel || 'Key';
        const valueSchema = config.patternProperties?.[".*"] || config.additionalProperties;
        const valueLabel = valueSchema?.label || 'Value';
        const valueDescription = valueSchema?.description || '';

        let valueInputHTML;

        if (entryKey === 'Uncategorized') {
            const arrayValue = Array.isArray(entryValue) ? entryValue : (entryValue ? [entryValue] : []);
            const fieldId = `field-${entryKey.replace(/\./g, '-')}`;
            let itemsHTML = '';
            arrayValue.forEach((item, index) => {
                itemsHTML += `
                    <div class="array-item" data-index="${index}">
                        <label for="${fieldId}-item-${index}" class="form-label sr-only">Item ${index + 1}</label>
                        <div class="array-item-input-group">
                            <input type="text" class="form-input array-item-input"
                                   id="${fieldId}-item-${index}"
                                   value="${item}" data-field="${entryKey}" data-index="${index}"
                                   name="${entryKey}[${index}]">
                             <button type="button" class="btn btn-icon btn-close-icon remove-array-item">
                                 ${CLOSE_ICON_SVG}
                            </button>
                        </div>
                    </div>
                `;
            });

            valueInputHTML = `
                <div class="array-field" data-field="${entryKey}">
                    <div class="array-items">
                        ${itemsHTML}
                    </div>
                    <button type="button" class="btn btn-secondary add-array-item"
                            data-field="${entryKey}">
                        Add Path
                    </button>
                </div>
                ${valueDescription ? `<div class="form-help">${valueDescription}</div>` : ''}
            `;
        } else if (typeof entryValue === 'string') {
            valueInputHTML = `
                <input type="text" class="form-input" name="${entryKey}::value" value="${entryValue}">
                ${valueDescription ? `<div class="form-help">${valueDescription}</div>` : ''}
                <div class="field-validation"></div>
            `;
        } else {
            valueInputHTML = `<div class="alert alert-error">Invalid value for ${entryKey}. Expected a string.</div>`;
        }

        let html = `
            <div class="complex-object-item complex-object-entry-card" data-key="${entryKey}">
                <div class="complex-object-item-content">
                    <div class="category-inputs">
                        <div class="category-labels-row">
                            <div class="category-name-group">
                                <label class="form-label">${keyLabel}</label>
                            </div>
                            <div class="category-path-group">
                                <label class="form-label">${valueLabel}</label>
                            </div>
                        </div>
                        <div class="category-inputs-row">
                            <div class="form-group category-name-group">
                                <input type="text" class="form-input complex-object-key" value="${entryKey}" data-original-key="${entryKey}" ${isOther || entryKey === 'Uncategorized' ? 'readonly' : ''}>
                            </div>
                            <div class="form-group category-path-group">
                                ${valueInputHTML}
                            </div>
                        </div>
                    </div>
                    <button type="button" class="btn btn-icon btn-close-icon remove-complex-object-item" data-key="${entryKey}">
                        ${CLOSE_ICON_SVG}
                    </button>
                </div>
            </div>
        `;
        return html;
    }

    // Original logic for object-based entries
    let schemaProperties;
    if (config.patternProperties) {
        if (isOther && config.patternProperties.other) {
            schemaProperties = config.patternProperties.other.properties;
        } else if (config.patternProperties["^(?!other$).*$"]) {
            schemaProperties = config.patternProperties["^(?!other$).*$"].properties;
        } else if (config.patternProperties[".*"]) {
            // For nohardlinks schema which uses ".*" pattern
            schemaProperties = config.patternProperties[".*"].properties;
        } else {
            console.error("Could not find matching pattern properties for complex object entry:", config);
            return '';
        }
    } else if (config.fields && config.fields.length > 0 && config.fields[0].properties) {
        // Fallback for old field-based schemas
        schemaProperties = config.fields[0].properties;
    } else {
        console.error("Could not determine schema properties for complex object entry:", config);
        return ''; // Or handle error appropriately
    }

    // Use custom key label if provided, otherwise default to "Tracker URL"
    const keyLabel = config.keyLabel || 'Tracker URL';

    let keyInputHTML;

    // Check if this schema should use category dropdown for key editing
    if (config.useCategoryDropdown && !isOther) {
        // Generate dropdown for category selection
        keyInputHTML = `
            <select class="form-input complex-object-key-dropdown" data-original-key="${entryKey}">
                <option value="${entryKey}" selected>${entryKey}</option>
            </select>
        `;
    } else {
        // Use regular text input
        keyInputHTML = `
            <input type="text" class="form-input complex-object-key" value="${entryKey}" data-original-key="${entryKey}" ${isOther ? 'readonly' : ''}>
        `;
    }

    let html = `
        <div class="complex-object-item complex-object-entry-card" data-key="${entryKey}">
            <button type="button" class="btn btn-icon btn-close-icon remove-complex-object-item complex-object-close-btn" data-key="${entryKey}">
                ${CLOSE_ICON_SVG}
            </button>
            <div class="complex-object-item-content">
                <div class="form-group complex-object-key-group">
                    <label class="form-label">${keyLabel}</label>
                    ${keyInputHTML}
                </div>
    `;

    // Render fields based on schemaProperties
    Object.entries(schemaProperties).forEach(([propName, propSchema]) => {
        // Use a custom separator for complex object fields to avoid issues with dots in keys
        const fieldName = `${entryKey}::${propName}`;
        const value = entryValue[propName] ?? propSchema.default ?? '';

        if (propSchema.type === 'array') {
            html += generateArrayFieldHTML(propSchema, value, fieldName);
        } else {
            html += generateFieldHTML(propSchema, value, fieldName);
        }
    });

    html += `
            </div>
        </div>
    `;
    return html;
}

/**
 * Build defaults for share-limit group properties directly from the schema.
 * This avoids duplicating defaults in code and uses the schema as source of truth.
 * @param {object} config - The section configuration (share-limits schema).
 * @returns {object} defaults map of property -> default value
 */
function getShareLimitSchemaDefaults(config) {
    // share_limits schema defines a single field object with name 'share_limit_groups'
    const groupField = Array.isArray(config?.fields)
        ? (config.fields.find(f => f.name === 'share_limit_groups') || config.fields[0])
        : null;
    const properties = groupField?.properties || {};

    const defaults = {};
    for (const [propName, propSchema] of Object.entries(properties)) {
        if (Object.prototype.hasOwnProperty.call(propSchema, 'default')) {
            defaults[propName] = propSchema.default;
        } else {
            // Fallbacks when schema doesn't provide a default
            switch (propSchema.type) {
                case 'array':
                    defaults[propName] = [];
                    break;
                case 'boolean':
                    defaults[propName] = false;
                    break;
                case 'number':
                    // No assumed numeric default; undefined means "no value set"
                    defaults[propName] = undefined;
                    break;
                default:
                    // text and others: default to empty string so we don't show in summary
                    defaults[propName] = '';
            }
        }
    }
    return defaults;
}

/**
 * Generates HTML for Share Limits configuration with drag-and-drop interface.
 * @param {object} config - The section configuration.
 * @param {object} data - The current data for the section.
 * @returns {string} The HTML string for the share limits configuration.
 */
export function generateShareLimitsHTML(config, data) {
    const shareLimitsData = data || {};
    const defaults = getShareLimitSchemaDefaults(config);

    // Convert data to array format sorted by priority for display
    const groupsArray = Object.entries(shareLimitsData)
        .map(([key, value]) => ({
            key,
            priority: value.priority || 999,
            ...value
        }))
        .sort((a, b) => a.priority - b.priority);

    let html = `
        <div class="share-limits-config">
            <div class="share-limits-header">
                <h3>Share Limit Groups</h3>
                <p class="share-limits-description">
                    Drag and drop to reorder priority. Click on a group to configure its settings.
                </p>
                <button type="button" class="btn btn-primary add-share-limit-group-btn">
                    Add New Group
                </button>
            </div>
            <div class="share-limits-list" id="share-limits-sortable">
    `;

    groupsArray.forEach((group, index) => {
        const summaryText = generateGroupSummary(group, defaults);
        html += `
            <div class="share-limit-group-item" data-key="${group.key}" data-priority="${group.priority}">
                <div class="share-limit-group-handle">
                    <svg class="drag-handle-icon" viewBox="0 0 24 24" width="16" height="16">
                        <path d="M9 3h2v2H9V3zm0 4h2v2H9V7zm0 4h2v2H9v-2zm0 4h2v2H9v-2zm0 4h2v2H9v-2zm4-16h2v2h-2V3zm0 4h2v2h-2V7zm0 4h2v2h-2v-2zm0 4h2v2h-2v-2zm0 4h2v2h-2v-2z"/>
                    </svg>
                </div>
                <div class="share-limit-group-content" data-key="${group.key}">
                    <div class="share-limit-group-main">
                        <div class="share-limit-group-info">
                            <div class="share-limit-group-name">${group.key}</div>
                            <div class="share-limit-group-priority">Priority: ${group.priority}</div>
                        </div>
                        <div class="share-limit-group-summary">${summaryText}</div>
                    </div>
                    <button type="button" class="btn btn-icon btn-close-icon remove-share-limit-group" data-key="${group.key}">
                        ${CLOSE_ICON_SVG}
                    </button>
                </div>
            </div>
        `;
    });

    html += `
            </div>
        </div>
    `;

    return html;
}

/**
 * Generates a summary text for a share limit group.
 * @param {object} group - The share limit group data.
 * @returns {string} Summary text describing the group's configuration.
 */
function generateGroupSummary(group, defaults) {
    // defaults are supplied from schema via getShareLimitSchemaDefaults(config)

    const summaryParts = [];

    // Helper function to check if value is not default
    const isNotDefault = (value, defaultValue) => {
        // Handle arrays
        if (Array.isArray(value) && Array.isArray(defaultValue)) {
            return value.length > 0;
        }

        // Handle null/undefined values
        if (value === undefined || value === null) {
            return false;
        }

        // Handle mixed type comparisons (number vs string)
        // This handles cases where default is number but value could be string like "1d", "2h1m"
        if (typeof value !== typeof defaultValue) {
            // If value is a string and default is a number, check if string represents the default number
            if (typeof value === 'string' && typeof defaultValue === 'number') {
                // If the string is a pure number, convert and compare
                const numValue = parseFloat(value);
                if (!isNaN(numValue) && numValue.toString() === value) {
                    return numValue !== defaultValue;
                }
                // If it's a duration string like "1d", "2h1m", it's definitely not default
                return true;
            }
            // If value is number and default is string, convert default and compare
            if (typeof value === 'number' && typeof defaultValue === 'string') {
                const numDefault = parseFloat(defaultValue);
                if (!isNaN(numDefault)) {
                    return value !== numDefault;
                }
            }
            // Different types that can't be meaningfully compared - assume not default
            return true;
        }

        // Same type comparisons
        return value !== defaultValue;
    };

    // 1) Share limits (share ratio, max/min seeding time, last active, min num seeds, limit upload speed)
    // Priority order: max_ratio, max_seeding_time, min_seeding_time, max_last_active, min_last_active, min_num_seeds, limit_upload_speed

    if (isNotDefault(group.max_ratio, defaults.max_ratio)) {
        summaryParts.push(`Max Ratio: ${group.max_ratio}`);
    }

    if (isNotDefault(group.max_seeding_time, defaults.max_seeding_time)) {
        summaryParts.push(`Max Seed Time: ${group.max_seeding_time}`);
    }

    if (isNotDefault(group.min_seeding_time, defaults.min_seeding_time)) {
        summaryParts.push(`Min Seed Time: ${group.min_seeding_time}`);
    }

    if (isNotDefault(group.max_last_active, defaults.max_last_active)) {
        summaryParts.push(`Max Last Active: ${group.max_last_active}`);
    }

    if (isNotDefault(group.min_last_active, defaults.min_last_active)) {
        summaryParts.push(`Min Last Active: ${group.min_last_active}`);
    }

    if (isNotDefault(group.min_num_seeds, defaults.min_num_seeds)) {
        summaryParts.push(`Min Seeds: ${group.min_num_seeds}`);
    }

    if (isNotDefault(group.limit_upload_speed, defaults.limit_upload_speed)) {
        summaryParts.push(`Upload Limit: ${group.limit_upload_speed} KiB/s`);
    }

    if (isNotDefault(group.upload_speed_on_limit_reached, defaults.upload_speed_on_limit_reached)) {
        summaryParts.push(`Upload Speed on Limit Reached: ${group.upload_speed_on_limit_reached} KiB/s`);
    }

    // Size filters (display values as entered)
    if (isNotDefault(group.min_torrent_size, defaults.min_torrent_size)) {
        summaryParts.push(`Min Size ${group.min_torrent_size}`);
    }
    if (isNotDefault(group.max_torrent_size, defaults.max_torrent_size)) {
        summaryParts.push(`Max Size ${group.max_torrent_size}`);
    }

    // 2) Tag/Category filters
    const tagFilters = [];

    if (isNotDefault(group.include_all_tags, defaults.include_all_tags)) {
        tagFilters.push(`Include All: ${group.include_all_tags.slice(0, 2).join(', ')}${group.include_all_tags.length > 2 ? '...' : ''}`);
    }

    if (isNotDefault(group.include_any_tags, defaults.include_any_tags)) {
        tagFilters.push(`Include Any: ${group.include_any_tags.slice(0, 2).join(', ')}${group.include_any_tags.length > 2 ? '...' : ''}`);
    }

    if (isNotDefault(group.exclude_all_tags, defaults.exclude_all_tags)) {
        tagFilters.push(`Exclude All: ${group.exclude_all_tags.slice(0, 2).join(', ')}${group.exclude_all_tags.length > 2 ? '...' : ''}`);
    }

    if (isNotDefault(group.exclude_any_tags, defaults.exclude_any_tags)) {
        tagFilters.push(`Exclude Any: ${group.exclude_any_tags.slice(0, 2).join(', ')}${group.exclude_any_tags.length > 2 ? '...' : ''}`);
    }

    if (tagFilters.length > 0) {
        summaryParts.push(`Tags: ${tagFilters.join(', ')}`);
    }

    if (isNotDefault(group.categories, defaults.categories)) {
        summaryParts.push(`Categories: ${group.categories.slice(0, 2).join(', ')}${group.categories.length > 2 ? '...' : ''}`);
    }

    // 3) Any other options (Cleanup enabled, Group Upload Speed, Custom Tag)
    if (isNotDefault(group.cleanup, defaults.cleanup)) {
        summaryParts.push('Cleanup: Enabled');
    }

    if (isNotDefault(group.enable_group_upload_speed, defaults.enable_group_upload_speed)) {
        summaryParts.push('Group Upload Speed: Enabled');
    }

    if (isNotDefault(group.custom_tag, defaults.custom_tag)) {
        summaryParts.push(`Custom Tag: ${group.custom_tag}`);
    }

    const result = summaryParts.length > 0 ? summaryParts.join(' • ') : 'No specific configuration';
    return result;
}
