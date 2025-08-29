/**
 * DOM Utility Module
 * Provides centralized functions for DOM element selection and manipulation.
 */

/**
 * Get an element by its ID.
 * @param {string} id - The ID of the element.
 * @returns {HTMLElement|null} The element, or null if not found.
 */
export function get(id) {
    return document.getElementById(id);
}

/**
 * Get the first element matching a CSS selector.
 * @param {string} selector - The CSS selector.
 * @param {HTMLElement} [parent=document] - The parent element to search within.
 * @returns {HTMLElement|null} The element, or null if not found.
 */
export function query(selector, parent = document) {
    return parent.querySelector(selector);
}

/**
 * Get all elements matching a CSS selector.
 * @param {string} selector - The CSS selector.
 * @param {HTMLElement} [parent=document] - The parent element to search within.
 * @returns {NodeListOf<HTMLElement>} A NodeList of matching elements.
 */
export function queryAll(selector, parent = document) {
    return parent.querySelectorAll(selector);
}

/**
 * Show an HTML element by removing the 'hidden' class.
 * @param {HTMLElement} element - The element to show.
 */
export function show(element) {
    if (element) {
        element.classList.remove('hidden');
    }
}

/**
 * Hide an HTML element by adding the 'hidden' class.
 * @param {HTMLElement} element - The element to hide.
 */
export function hide(element) {
    if (element) {
        element.classList.add('hidden');
    }
}

/**
 * Displays a loading spinner in the specified container.
 * @param {HTMLElement} container - The container element where the spinner should be displayed.
 * @param {string} [message='Loading...'] - The message to display below the spinner.
 */
export function showLoading(container, message = 'Loading...') {
    if (container) {
        // Create a loading overlay element
        const loadingOverlay = document.createElement('div');
        loadingOverlay.id = 'loading-overlay'; // Give it a unique ID
        loadingOverlay.className = 'loading-overlay'; // Add a class for styling
        loadingOverlay.innerHTML = `
            <div class="loading-spinner">
                <div class="spinner spinner-lg"></div>
                <p>${message}</p>
            </div>
        `;
        container.appendChild(loadingOverlay); // Append it to the container
    }
}

/**
 * Hides the loading spinner.
 */
export function hideLoading() {
    const loadingOverlay = get('loading-overlay'); // Get the overlay by its ID
    if (loadingOverlay) {
        loadingOverlay.remove(); // Remove it from the DOM
    }
}
