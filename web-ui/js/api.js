/**
 * qBit Manage Web UI - API Client
 * Handles all communication with the FastAPI backend
 */

class API {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.defaultHeaders = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
        this.supportsBackups = true; // Assume backups are supported until proven otherwise
    }

    /**
     * Make HTTP request with error handling
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}/api${endpoint}`;
        const config = {
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new APIError(
                    errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
                    response.status,
                    errorData
                );
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            if (error instanceof APIError) {
                throw error;
            }

            // Network or other errors
            throw new APIError(
                error.message || 'Network error occurred',
                0,
                { originalError: error }
            );
        }
    }

    /**
     * GET request
     */
    async get(endpoint, params = {}) {
        const url = new URL(`${this.baseUrl}/api${endpoint}`, window.location.origin);
        Object.keys(params).forEach(key => {
            if (params[key] !== undefined && params[key] !== null) {
                url.searchParams.append(key, params[key]);
            }
        });

        return this.request(endpoint + (url.search || ''), { method: 'GET' });
    }

    /**
     * POST request
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT request
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE request
     */
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }

    // Configuration Management Endpoints

    /**
     * List all configuration files
     */
    async listConfigs() {
        return this.get('/configs');
    }

    /**
     * Get configuration file content
     */
    async getConfig(filename) {
        return this.get(`/configs/${encodeURIComponent(filename)}`);
    }

    /**
     * Create new configuration file
     */
    async createConfig(filename, data) {
        return this.post(`/configs/${encodeURIComponent(filename)}`, data);
    }

    /**
     * Update configuration file
     */
    async updateConfig(filename, data) {
        return this.put(`/configs/${encodeURIComponent(filename)}`, data);
    }

    /**
     * Delete configuration file
     */
    async deleteConfig(filename) {
        return this.delete(`/configs/${encodeURIComponent(filename)}`);
    }

    /**
     * Validate configuration file
     */
    async validateConfig(filename, data = null) {
        const endpoint = `/configs/${encodeURIComponent(filename)}/validate`;
        if (data) {
            return this.post(endpoint, data);
        } else {
            return this.get(endpoint);
        }
    }

    /**
     * Backup configuration file
     */
    async backupConfig(filename) {
        return this.post(`/configs/${encodeURIComponent(filename)}/backup`);
    }

    /**
     * Restore configuration from backup
     */
    async restoreConfig(filename, backupId) {
        return this.post(`/configs/${encodeURIComponent(filename)}/restore`, {
            backup_id: backupId
        });
    }

    /**
     * List configuration backups
     */
    async listBackups(filename) {
        if (!this.supportsBackups) {
            throw new APIError('Backup feature not supported', 404);
        }

        try {
            return await this.get(`/configs/${encodeURIComponent(filename)}/backups`);
        } catch (error) {
            if (error.status === 404) {
                this.supportsBackups = false; // Disable future backup calls
            }
            throw error;
        }
    }

    // Command Execution Endpoints

    /**
     * Execute qBit Manage commands
     */
    async runCommand(data) {
        return this.post('/commands/run', data);
    }


    /**
     * Get command history
     */
    async getCommandHistory(limit = 50) {
        return this.get('/commands/history', { limit });
    }


    // qBittorrent Integration Endpoints

    /**
     * Test qBittorrent connection
     */
    async testQbittorrentConnection(config = null) {
        const endpoint = '/qbittorrent/test';
        if (config) {
            return this.post(endpoint, config);
        } else {
            return this.get(endpoint);
        }
    }

    /**
     * Get qBittorrent info
     */
    async getQbittorrentInfo() {
        return this.get('/qbittorrent/info');
    }

    /**
     * Get torrent list from qBittorrent
     */
    async getTorrents(filters = {}) {
        return this.get('/qbittorrent/torrents', filters);
    }

    /**
     * Get torrent details
     */
    async getTorrentDetails(hash) {
        return this.get(`/qbittorrent/torrents/${hash}`);
    }

    /**
     * Get categories from qBittorrent
     */
    async getCategories() {
        return this.get('/qbittorrent/categories');
    }

    /**
     * Get tags from qBittorrent
     */
    async getTags() {
        return this.get('/qbittorrent/tags');
    }

    /**
     * Get trackers from qBittorrent
     */
    async getTrackers() {
        return this.get('/qbittorrent/trackers');
    }


    // Log Management Endpoints

    /**
     * Get recent logs
     */
    async getLogs(limit = null, log_filename = null) {
        const params = {};
        if (limit !== null) params.limit = limit;
        if (log_filename) params.log_filename = log_filename;
        return this.get('/logs', params);
    }

    /**
     * Get list of available log files
     */
    async getLogFiles() {
        return this.get('/log_files');
    }

    /**
     * Get the current qBit Manage version
     */
    async getVersion() {
        try {
            const result = await this.get('/version');
            return result;
        } catch (error) {
            console.error('API.getVersion() failed:', error);
            throw error;
        }
    }


    // Utility Methods

    /**
     * Upload file
     */
    async uploadFile(file, endpoint) {
        const formData = new FormData();
        formData.append('file', file);

        return this.request(endpoint, {
            method: 'POST',
            body: formData,
            headers: {} // Let browser set Content-Type for FormData
        });
    }

    /**
     * Download file
     */
    async downloadFile(endpoint, filename = null) {
        const response = await fetch(`${this.baseUrl}/api${endpoint}`, {
            headers: this.defaultHeaders
        });

        if (!response.ok) {
            throw new APIError(`Download failed: ${response.statusText}`, response.status);
        }

        const blob = await response.blob();

        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || 'download';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }

    /**
     * Check if endpoint is available
     */
    async ping() {
        try {
            await this.get('/health');
            return true;
        } catch (error) {
            return false;
        }
    }

    /**
     * Get API documentation
     */
    async getApiDocs() {
        return this.get('/docs');
    }

    /**
     * Get OpenAPI schema
     */
    async getOpenApiSchema() {
        return this.get('/openapi.json');
    }
}

/**
 * Custom API Error class
 */
class APIError extends Error {
    constructor(message, status = 0, data = {}) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }

    /**
     * Check if error is a specific HTTP status
     */
    isStatus(status) {
        return this.status === status;
    }

    /**
     * Check if error is a client error (4xx)
     */
    isClientError() {
        return this.status >= 400 && this.status < 500;
    }

    /**
     * Check if error is a server error (5xx)
     */
    isServerError() {
        return this.status >= 500 && this.status < 600;
    }

    /**
     * Check if error is a network error
     */
    isNetworkError() {
        return this.status === 0;
    }

    /**
     * Get user-friendly error message
     */
    getUserMessage() {
        if (this.isNetworkError()) {
            return 'Unable to connect to the server. Please check your connection.';
        }

        if (this.isStatus(401)) {
            return 'Authentication required. Please log in.';
        }

        if (this.isStatus(403)) {
            return 'Access denied. You do not have permission to perform this action.';
        }

        if (this.isStatus(404)) {
            return 'The requested resource was not found.';
        }

        if (this.isStatus(422)) {
            return 'Invalid data provided. Please check your input.';
        }

        if (this.isStatus(429)) {
            return 'Too many requests. Please wait a moment and try again.';
        }

        if (this.isServerError()) {
            return 'A server error occurred. Please try again later.';
        }

        return this.message || 'An unexpected error occurred.';
    }

    /**
     * Get validation errors if available
     */
    getValidationErrors() {
        if (this.isStatus(422) && this.data.detail && Array.isArray(this.data.detail)) {
            return this.data.detail.map(error => ({
                field: error.loc ? error.loc.join('.') : 'unknown',
                message: error.msg,
                type: error.type
            }));
        }
        return [];
    }
}

/**
 * API Response wrapper for consistent handling
 */
class APIResponse {
    constructor(data, status = 200, headers = {}) {
        this.data = data;
        this.status = status;
        this.headers = headers;
        this.success = status >= 200 && status < 300;
    }

    /**
     * Check if response is successful
     */
    isSuccess() {
        return this.success;
    }

    /**
     * Get response data
     */
    getData() {
        return this.data;
    }

    /**
     * Get specific field from response data
     */
    getField(field, defaultValue = null) {
        return this.data && typeof this.data === 'object'
            ? this.data[field] || defaultValue
            : defaultValue;
    }

    /**
     * Check if response has specific field
     */
    hasField(field) {
        return this.data && typeof this.data === 'object' && field in this.data;
    }
}

/**
 * API Client with retry logic and caching
 */
class EnhancedAPI extends API {
    constructor(baseUrl = '', options = {}) {
        super(baseUrl);

        this.retryAttempts = options.retryAttempts || 3;
        this.retryDelay = options.retryDelay || 1000;
        this.cache = new Map();
        this.cacheTimeout = options.cacheTimeout || 60000; // 1 minute
    }

    /**
     * Request with retry logic
     */
    async requestWithRetry(endpoint, options = {}, attempt = 1) {
        try {
            return await this.request(endpoint, options);
        } catch (error) {
            if (attempt < this.retryAttempts && this.shouldRetry(error)) {
                await this.delay(this.retryDelay * attempt);
                return this.requestWithRetry(endpoint, options, attempt + 1);
            }
            throw error;
        }
    }

    /**
     * Check if error should trigger a retry
     */
    shouldRetry(error) {
        return error.isNetworkError() ||
               error.isStatus(500) ||
               error.isStatus(502) ||
               error.isStatus(503) ||
               error.isStatus(504);
    }

    /**
     * Delay utility for retries
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Cached GET request
     */
    async getCached(endpoint, params = {}, cacheKey = null) {
        const key = cacheKey || `${endpoint}?${new URLSearchParams(params).toString()}`;
        const cached = this.cache.get(key);

        if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
            return cached.data;
        }

        const data = await this.get(endpoint, params);
        this.cache.set(key, { data, timestamp: Date.now() });

        return data;
    }

    /**
     * Clear cache
     */
    clearCache(pattern = null) {
        if (pattern) {
            for (const key of this.cache.keys()) {
                if (key.includes(pattern)) {
                    this.cache.delete(key);
                }
            }
        } else {
            this.cache.clear();
        }
    }

    /**
     * Batch requests
     */
    async batch(requests) {
        const promises = requests.map(({ method, endpoint, data }) => {
            switch (method.toLowerCase()) {
                case 'get':
                    return this.get(endpoint, data);
                case 'post':
                    return this.post(endpoint, data);
                case 'put':
                    return this.put(endpoint, data);
                case 'delete':
                    return this.delete(endpoint);
                default:
                    throw new Error(`Unsupported method: ${method}`);
            }
        });

        return Promise.allSettled(promises);
    }
}

// Export classes
export { API, APIError, APIResponse, EnhancedAPI };

// Create default instance
export default new API();
