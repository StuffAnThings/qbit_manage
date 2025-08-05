/**
 * General Utility Module
 * Provides common utility functions.
 */

/**
 * Gets a nested value from an object using a dot-separated path.
 * @param {object} obj - The object to query.
 * @param {string} path - The dot-separated path (e.g., 'parent.child.property').
 * @returns {*} The value at the specified path, or undefined if not found.
 */
export function getNestedValue(obj, path) {
    return path.split('.').reduce((current, key) => {
        return current && current[key] !== undefined ? current[key] : undefined;
    }, obj);
}

 /**
  * Escape a string for safe insertion into HTML/attribute context.
  * Encodes &, <, >, ", ' to their HTML entities.
  * This should be used whenever inserting user-controlled content via innerHTML
  * or into attribute values.
  * @param {any} str - Input value to escape
  * @returns {string} Escaped HTML-safe string
  */
export function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/\//g, '&#x2F;');
}

/**
 * Sets a nested value in an object using a dot-separated path.
 * Creates intermediate objects if they don't exist.
 * If the value is null, undefined, or an empty string, the property is deleted.
 * @param {object} obj - The object to modify.
 * @param {string} path - The dot-separated path (e.g., 'parent.child.property').
 * @param {*} value - The value to set.
 */
export function setNestedValue(obj, path, value) {
    const keys = path.split('.');
    const lastKey = keys.pop();
    const target = keys.reduce((current, key) => {
        if (!current[key] || typeof current[key] !== 'object') {
            current[key] = {};
        }
        return current[key];
    }, obj);

    if (value === null || value === undefined || value === '') {
        delete target[lastKey];
    } else {
        target[lastKey] = value;
    }
}

/**
 * Basic host validation - IP address or hostname
 * @param {string} host - The host string to validate.
 * @returns {boolean} True if the host is valid, false otherwise.
 */
export function isValidHost(host) {
    const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    const hostnameRegex = /^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/;

    return ipRegex.test(host) || hostnameRegex.test(host) || host === 'localhost';
}
/**
 * Debounces a function, so it only runs after a specified delay.
 * @param {function} func - The function to debounce.
 * @param {number} delay - The delay in milliseconds.
 * @returns {function} The debounced function.
 */
export function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}
