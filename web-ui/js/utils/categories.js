/**
 * Categories Utility Module
 * Provides functions for working with category dropdowns in forms
 */

/**
 * Get available categories from the global app configuration
 * @returns {Array<string>} Array of available category names
 */
export function getAvailableCategories() {
    try {
        // Access categories from the app's global config data
        // The app instance should be available through window.app
        if (window.app && window.app.configData && window.app.configData.cat) {
            const categories = Object.keys(window.app.configData.cat);
            return categories;
        }

        return [];
    } catch (error) {
        console.error('Error fetching categories:', error);
        return [];
    }
}

/**
 * Generate HTML for a category dropdown select element
 * @param {string} name - The name attribute for the select element
 * @param {string} value - The current selected value
 * @param {Array<string>} categories - Array of available categories
 * @param {string} className - CSS class names for the select element
 * @param {string} fieldName - The field name for data attributes
 * @param {number} index - The index for array items
 * @returns {string} HTML string for the category dropdown
 */
export function generateCategoryDropdownHTML(name, value, categories, className = '', fieldName = '', index = null) {
    const dataAttributes = [];
    if (fieldName) {
        dataAttributes.push(`data-field="${fieldName}"`);
    }
    if (index !== null) {
        dataAttributes.push(`data-index="${index}"`);
    }

    let html = `<select name="${name}" class="category-dropdown ${className}" ${dataAttributes.join(' ')}>`;

    // Add empty option
    html += `<option value="">Select Category</option>`;

    // Add all available categories
    categories.forEach(category => {
        const selected = category === value ? 'selected' : '';
        html += `<option value="${category}" ${selected}>${category}</option>`;
    });

    html += `</select>`;

    return html;
}

/**
 * Populate existing category dropdowns with available categories
 * @param {HTMLElement} container - The container element to search for dropdowns
 */
export async function populateCategoryDropdowns(container) {
    // Find all category dropdowns in the container
    const fieldDropdowns = container.querySelectorAll('.category-dropdown');

    if (fieldDropdowns.length === 0) return;

    try {
        // Get available categories
        const categories = getAvailableCategories();

        // Handle individual field category dropdowns
        fieldDropdowns.forEach(dropdown => {
            const currentValue = dropdown.value;

            // Clear existing options
            dropdown.innerHTML = '';

            // Add empty option
            const emptyOption = document.createElement('option');
            emptyOption.value = '';
            emptyOption.textContent = 'Select Category';
            dropdown.appendChild(emptyOption);

            // Add all available categories
            categories.forEach(category => {
                const option = document.createElement('option');
                option.value = category;
                option.textContent = category;
                if (category === currentValue) {
                    option.selected = true;
                }
                dropdown.appendChild(option);
            });
        });
    } catch (error) {
        console.error('Error populating category dropdowns:', error);
    }
}
