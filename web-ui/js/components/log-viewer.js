/**
 * qBit Manage Web UI - Log Viewer Component
 * Real-time log viewing and management
 */

import { API } from '../api.js';
import { showToast } from '../utils/toast.js';
import { show, hide } from '../utils/dom.js';

class LogViewer {
    constructor(options = {}) {
        this.container = options.container;
        this.autoRefreshInterval = parseInt(localStorage.getItem('qbm-log-refresh-interval') || '0'); // Default to 0 (no auto-refresh)
        this.autoRefreshTimer = null;
        this.currentLogFile = localStorage.getItem('qbm-selected-log-file') || 'qbit_manage.log'; // Default log file
        this.currentLogLimit = parseInt(localStorage.getItem('qbm-log-limit') || '50'); // Default to 50 lines

        this.api = new API();
        this.logs = [];
        this.filteredLogs = [];
    }

    async init() {
        this.render();
        this.bindEvents();
        await this.loadLogFiles(); // Load log files first
        this.loadRecentLogs();
        this.startAutoRefresh(); // Start auto-refresh on init
        // Initial call to handle scroll to set button visibility
        setTimeout(() => this.handleScroll(), 100);
    }

    async loadLogFiles() {
        try {
            const response = await this.api.getLogFiles();
            const logFileSelect = this.container.querySelector('#log-file-select');
            logFileSelect.innerHTML = ''; // Clear existing options

            if (response.log_files && response.log_files.length > 0) {
                response.log_files.forEach(file => {
                    const option = document.createElement('option');
                    option.value = file;
                    option.textContent = file;
                    logFileSelect.appendChild(option);
                });
                // Set the selected value based on localStorage or default
                logFileSelect.value = this.currentLogFile;
                if (!logFileSelect.value) { // If the stored value isn't in the list, default to the first
                    this.currentLogFile = response.log_files[0];
                    logFileSelect.value = this.currentLogFile;
                    localStorage.setItem('qbm-selected-log-file', this.currentLogFile);
                }
            } else {
                logFileSelect.innerHTML = '<option value="">No log files found</option>';
                this.currentLogFile = null;
            }
        } catch (error) {
            this.showToast('Failed to load log files', 'error');
            this.currentLogFile = null;
        }
    }

    render() {
        if (!this.container) return;

        const generatedHtml = `
            <div class="log-viewer-header">
                <div class="log-viewer-title">
                    <h4>System Logs</h4>
                    <select id="log-file-select" class="form-select form-select-sm">
                        <!-- Options will be populated dynamically -->
                    </select>
                    <div class="refresh-interval-control">
                        <label for="log-refresh-interval" class="form-label">Refresh every:</label>
                        <select id="log-refresh-interval" class="form-select form-select-sm">
                            <option value="0">Off</option>
                            <option value="1">1s</option>
                            <option value="5">5s</option>
                            <option value="10">10s</option>
                            <option value="30">30s</option>
                            <option value="60">1m</option>
                            <option value="300">5m</option>
                        </select>
                        <label for="log-limit-select" class="form-label">Show lines:</label>
                        <select id="log-limit-select" class="form-select form-select-sm">
                            <option value="0">All</option>
                            <option value="50">50</option>
                            <option value="100">100</option>
                            <option value="200">200</option>
                            <option value="500">500</option>
                            <option value="1000">1000</option>
                        </select>
                    </div>
                </div>

                <div class="log-viewer-controls">
                    <div class="log-filters">
                        <input type="text" id="log-search" class="form-input form-input-sm"
                                placeholder="Search logs...">
                        <button type="button" class="btn btn-secondary" id="refresh-logs-btn">
                            🔄 Refresh
                        </button>
                    </div>
                    </div>
                </div>
            </div>

            <div class="log-viewer-content">
                <div class="log-floating-scroll-top-btn">
                    <button type="button" class="btn btn-secondary" id="scroll-to-top-btn">
                        ⬆️ Top
                    </button>
                </div>

                <div class="log-floating-scroll-bottom-btn">
                    <button type="button" class="btn btn-secondary" id="scroll-to-bottom-btn">
                        ⬇️ Bottom
                    </button>
                </div>

                <div class="log-container" id="log-container">
                    <div class="log-placeholder">
                        <div class="placeholder-icon">📋</div>
                        <div class="placeholder-text">No logs to display</div>
                        <div class="placeholder-subtext">Logs will appear here when available</div>
                    </div>
                </div>
            </div>

            <div class="log-viewer-footer">
                <div class="log-status">
                    <span class="last-updated-status" id="log-last-updated-status">
                        Last updated: Never
                    </span>
                </div>
                <div class="log-settings">
                    <!-- Word wrap checkbox removed as per user request -->
                </div>
            </div>
        `;
        this.container.innerHTML = generatedHtml;
    }

    bindEvents() {
        if (!this.container) return;

        // Filter controls
        const logFileSelect = this.container.querySelector('#log-file-select');
        const searchInput = this.container.querySelector('#log-search');
        const logLimitSelect = this.container.querySelector('#log-limit-select');

        logFileSelect.addEventListener('change', (e) => {
            this.currentLogFile = e.target.value;
            localStorage.setItem('qbm-selected-log-file', this.currentLogFile);
            this.loadRecentLogs(); // Reload logs for the newly selected file
        });

        searchInput.addEventListener('input', (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.applyFilters();
        });

        if (logLimitSelect) {
            // Always set the dropdown value to match currentLogLimit
            logLimitSelect.value = this.currentLogLimit;
            logLimitSelect.addEventListener('change', (e) => {
                this.currentLogLimit = parseInt(e.target.value);
                localStorage.setItem('qbm-log-limit', this.currentLogLimit);
                this.loadRecentLogs(); // Reload logs with new limit
            });
        }

        // Manual refresh button
        const refreshButton = this.container.querySelector('#refresh-logs-btn');
        if (refreshButton) {
            refreshButton.addEventListener('click', () => {
                this.loadRecentLogs();
                this.showToast('Logs refreshed', 'info');
            });
        }

        // Auto-refresh interval control
        const refreshIntervalSelect = this.container.querySelector('#log-refresh-interval');
        if (refreshIntervalSelect) {
            refreshIntervalSelect.value = this.autoRefreshInterval; // Set initial value
            refreshIntervalSelect.addEventListener('change', (e) => {
                this.autoRefreshInterval = parseInt(e.target.value);
                localStorage.setItem('qbm-log-refresh-interval', this.autoRefreshInterval);
                this.startAutoRefresh(); // Restart timer with new interval
                if (this.autoRefreshInterval > 0) {
                    this.showToast(`Logs will refresh every ${this.autoRefreshInterval} seconds`, 'info');
                } else {
                    this.showToast('Log auto-refresh is off', 'info');
                }
            });
        }

        // Scroll buttons
        const scrollToTopBtn = this.container.querySelector('#scroll-to-top-btn');
        if (scrollToTopBtn) {
            scrollToTopBtn.addEventListener('click', () => this.scrollToTop());
        }

        const scrollToBottomBtn = this.container.querySelector('#scroll-to-bottom-btn');
        if (scrollToBottomBtn) {
            scrollToBottomBtn.addEventListener('click', () => this.scrollToBottom());
        }

        // Scroll event listener for button visibility
        const logViewerContent = this.container.querySelector('.log-viewer-content');
        if (logViewerContent) {
            logViewerContent.addEventListener('scroll', () => this.handleScroll());
        }

        // Window resize event listener to reposition buttons
        window.addEventListener('resize', () => this.handleScroll());
    }

    async loadRecentLogs() {
        try {
            const limit = this.currentLogLimit === 0 ? null : this.currentLogLimit;
            const response = await this.api.getLogs(limit, this.currentLogFile);
            this.logs = response.logs || [];
            this.applyFilters();
            this.updateLastUpdatedStatus();
        } catch (error) {
            this.updateLastUpdatedStatus(true); // Indicate error
        }
    }

    addLog(logData) {
        // Logs are now raw strings from the backend
        this.logs.unshift(logData);
        this.applyFilters();
    }

    // New methods to be added
    show() {
        if (this.container) {
            show(this.container);
            this.scrollToBottom(); // Scroll to bottom when shown
        }
    }

    hide() {
        if (this.container) {
            hide(this.container);
        }
    }

    clearLogs() {
        this.logs = [];
        this.filteredLogs = [];
        this.renderLogs();
    }

    log(level, message) {
        const timestamp = new Date().toISOString();
        this.addLog(`${timestamp} [${level.toUpperCase()}] ${message}`);
    }

    applyFilters() {
        let filtered = [...this.logs];

        // Search filter
        if (this.searchTerm) {
            filtered = filtered.filter(log =>
                log.toLowerCase().includes(this.searchTerm)
            );
        }

        this.filteredLogs = filtered;
        this.renderLogs();
    }

    renderLogs() {
        const logViewerContent = this.container.querySelector('.log-viewer-content');
        const logContainer = this.container.querySelector('#log-container');

        if (this.filteredLogs.length === 0) {
            logContainer.innerHTML = `
                <div class="log-placeholder">
                    <div class="placeholder-icon">📋</div>
                    <div class="placeholder-text">No logs match current filters</div>
                    <div class="placeholder-subtext">Try adjusting your filter settings</div>
                </div>
            `;
            // If no logs, ensure the scrollable area is reset
            if (logViewerContent) {
                logViewerContent.scrollTop = 0;
            }
            return;
        }

        let html = '';
        this.filteredLogs.forEach((log, index) => {
            // Logs are now raw strings, display them directly with clickable links
            html += `
                <div class="log-entry">
                    <span class="log-message">${this.makeLinksClickable(log)}</span>
                </div>
            `;
        });

        logContainer.innerHTML = html;

    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Converts URLs in text to clickable links while escaping the rest
     * @param {string} text - The text to process
     * @returns {string} - HTML with clickable links
     */
    makeLinksClickable(text) {
        // URL regex patterns for both HTTP and HTTPS - handled identically
        const httpRegex = /(http:\/\/[^\s]+)/g;
        const httpsRegex = /(https:\/\/[^\s]+)/g;

        // Escape the entire text first for security
        const escapedText = this.escapeHtml(text);

        // Replace both HTTP and HTTPS URLs with identical clickable links
        let result = escapedText.replace(httpRegex, (url) => {
            return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="log-link">${url}</a>`;
        });

        result = result.replace(httpsRegex, (url) => {
            return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="log-link">${url}</a>`;
        });

        return result;
    }

    scrollToTop() {
        const logViewerContent = this.container.querySelector('.log-viewer-content');
        if (logViewerContent) {
            logViewerContent.scrollTop = 0;
        }
    }

    scrollToBottom() {
        const logViewerContent = this.container.querySelector('.log-viewer-content');
        if (logViewerContent) {
            logViewerContent.scrollTop = logViewerContent.scrollHeight;
        }
    }

    handleScroll() {
        const logViewerContent = this.container.querySelector('.log-viewer-content');
        const scrollToTopBtn = this.container.querySelector('#scroll-to-top-btn');
        const scrollToBottomBtn = this.container.querySelector('#scroll-to-bottom-btn');
        const topButtonContainer = this.container.querySelector('.log-floating-scroll-top-btn');
        const bottomButtonContainer = this.container.querySelector('.log-floating-scroll-bottom-btn');

        if (!logViewerContent || !scrollToTopBtn || !scrollToBottomBtn || !topButtonContainer || !bottomButtonContainer) {
            return;
        }

        // Get the position of the log viewer content relative to the viewport
        const contentRect = logViewerContent.getBoundingClientRect();
        const rightOffset = 40; // Space from right edge, accounting for scrollbar
        const verticalOffset = 8; // Small offset from top/bottom edges

        // Position the buttons relative to the log viewer content
        topButtonContainer.style.top = `${contentRect.top + verticalOffset}px`;
        topButtonContainer.style.right = `${rightOffset}px`;

        bottomButtonContainer.style.bottom = `${window.innerHeight - contentRect.bottom + verticalOffset}px`;
        bottomButtonContainer.style.right = `${rightOffset}px`;

        const { scrollTop, scrollHeight, clientHeight } = logViewerContent;
        const atTop = scrollTop === 0;
        // Add a small tolerance (1px) for bottom detection to handle rounding issues
        const atBottom = Math.abs(scrollTop + clientHeight - scrollHeight) <= 1;
        const isScrollable = scrollHeight > clientHeight;

        // Show/hide top button - visible when scrollable and not at top
        if (isScrollable && !atTop) {
            topButtonContainer.classList.add('visible');
        } else {
            topButtonContainer.classList.remove('visible');
        }

        // Show/hide bottom button - visible when scrollable and not at bottom
        if (isScrollable && !atBottom) {
            bottomButtonContainer.classList.add('visible');
        } else {
            bottomButtonContainer.classList.remove('visible');
        }
    }

    startAutoRefresh() {
        this.stopAutoRefresh(); // Clear any existing timer
        if (this.autoRefreshInterval > 0) {
            this.autoRefreshTimer = setInterval(() => {
                this.loadRecentLogs();
            }, this.autoRefreshInterval * 1000);
        }
    }

    stopAutoRefresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }
    }

    updateLastUpdatedStatus(isError = false) {
        const statusElement = this.container.querySelector('#log-last-updated-status');
        if (isError) {
            statusElement.textContent = 'Last updated: Error loading logs';
            statusElement.classList.add('error');
        } else {
            statusElement.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
            statusElement.classList.remove('error');
        }
    }

    showToast(message, type = 'info') {
        // If there's a global toast function available, use it
        if (window.qbitManageApp && window.qbitManageApp.showToast) {
            window.qbitManageApp.showToast(message, type);
        }
    }
}

export { LogViewer };
