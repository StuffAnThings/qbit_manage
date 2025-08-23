/**
 * Documentation Viewer Component
 * Fetches and renders markdown documentation with collapsible sections
 */

class DocumentationViewer {
    constructor() {
        this.markedLoaded = false;
        this.cache = new Map();
        this.loadMarkedLibrary();
    }

    /**
     * Load the marked.js library from CDN
     */
    async loadMarkedLibrary() {
        if (this.markedLoaded) return;

        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
            script.onload = () => {
                this.markedLoaded = true;
                // Configure marked options
                if (window.marked) {
                    window.marked.setOptions({
                        breaks: true,
                        gfm: true,
                        tables: true,
                        sanitize: false,
                        smartLists: true,
                        smartypants: false
                    });
                }
                resolve();
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    /**
     * Fetch markdown content from a file
     * @param {string} filePath - Path to the markdown file relative to the web root
     * @returns {Promise<string>} The markdown content
     */
    async fetchMarkdown(filePath) {
        // Check cache first
        if (this.cache.has(filePath)) {
            return this.cache.get(filePath);
        }

        try {
            const response = await fetch(`/api/docs?file=${encodeURIComponent(filePath)}`);
            if (!response.ok) {
                throw new Error(`Failed to fetch documentation: ${response.statusText}`);
            }
            const content = await response.text();
            this.cache.set(filePath, content);
            return content;
        } catch (error) {
            console.error('Error fetching markdown:', error);
            return `*Unable to load documentation from ${filePath}*`;
        }
    }

    /**
     * Extract a specific section from markdown content
     * @param {string} content - The full markdown content
     * @param {string} sectionTitle - The section title to extract
     * @param {number} headingLevel - The heading level (1-6)
     * @returns {string} The extracted section content
     */
    extractSection(content, sectionTitle, headingLevel = 2) {
        const lines = content.split('\n');
        const headingPrefix = '#'.repeat(headingLevel);

        // Create a more flexible regex that handles markdown formatting like **text:** or *text*
        // Escape special regex characters in the section title
        const escapedTitle = sectionTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

        // Look for the section title with optional markdown formatting (**, *, :, etc.)
        // Handle format like: ## **settings:** where asterisks surround "settings:"
        const sectionRegex = new RegExp(`^${headingPrefix}\\s+(?:\\*{1,2})?${escapedTitle}:?(?:\\*{1,2})?\\s*$`, 'i');
        const nextSectionRegex = new RegExp(`^#{1,${headingLevel}}\\s+`);

        let sectionStart = -1;
        let sectionEnd = lines.length;

        // Find the start of the section
        for (let i = 0; i < lines.length; i++) {
            if (sectionRegex.test(lines[i])) {
                sectionStart = i;
                break;
            }
        }

        if (sectionStart === -1) {
            return '';
        }

        // Find the end of the section (next heading of same or higher level)
        for (let i = sectionStart + 1; i < lines.length; i++) {
            if (nextSectionRegex.test(lines[i])) {
                const currentLevel = lines[i].match(/^#+/)[0].length;
                if (currentLevel <= headingLevel) {
                    sectionEnd = i;
                    break;
                }
            }
        }

        return lines.slice(sectionStart, sectionEnd).join('\n');
    }

    /**
     * Process GitHub-style alerts in markdown content
     * @param {string} markdown - The markdown content
     * @returns {string} The processed markdown with GitHub alerts converted to placeholders
     */
    processGitHubAlerts(markdown) {
        // Store alert data for post-processing
        this.alertData = [];

        // Split markdown into lines for processing
        const lines = markdown.split('\n');
        const processedLines = [];
        let i = 0;

        while (i < lines.length) {
            const line = lines[i];
            const alertMatch = line.match(/^>\s*\[!(WARNING|TIP|NOTE|CAUTION|IMPORTANT)\]\s*$/);

            if (alertMatch) {
                const alertType = alertMatch[1].toLowerCase();
                const alertContent = [];

                // Skip the alert header line
                i++;

                // Collect all subsequent blockquote lines that belong to this alert
                while (i < lines.length && lines[i].startsWith('>')) {
                    // Remove the '> ' prefix and add to content
                    alertContent.push(lines[i].substring(2));
                    i++;
                }

                // Store alert data for post-processing
                const alertId = this.alertData.length;
                this.alertData.push({
                    type: alertType,
                    content: alertContent.join('\n').trim()
                });

                // Create placeholder that will be replaced after markdown processing
                processedLines.push(`GITHUB_ALERT_PLACEHOLDER_${alertId}`);

                // Don't increment i here as it's already been incremented in the while loop
                continue;
            } else {
                processedLines.push(line);
                i++;
            }
        }

        return processedLines.join('\n');
    }

    /**
     * Post-process HTML to replace alert placeholders with rendered alerts
     * @param {string} html - The rendered HTML
     * @returns {string} The HTML with alert placeholders replaced
     */
    async processAlertPlaceholders(html) {
        if (!this.alertData || this.alertData.length === 0) {
            return html;
        }

        let processedHtml = html;

        for (let i = 0; i < this.alertData.length; i++) {
            const alert = this.alertData[i];

            // Try multiple placeholder formats since markdown processing might wrap them differently
            const placeholderPatterns = [
                `<p>GITHUB_ALERT_PLACEHOLDER_${i}</p>`,
                `GITHUB_ALERT_PLACEHOLDER_${i}`,
                new RegExp(`<p[^>]*>\\s*GITHUB_ALERT_PLACEHOLDER_${i}\\s*</p>`, 'g'),
                new RegExp(`GITHUB_ALERT_PLACEHOLDER_${i}`, 'g')
            ];

            // Render the alert content as markdown
            const renderedContent = await window.marked.parse(alert.content);

            // Create the alert HTML
            const alertHtml = `<div class="github-alert github-alert-${alert.type}">
                <div class="github-alert-header">
                    <span class="github-alert-icon">${this.getAlertIcon(alert.type)}</span>
                    <span class="github-alert-title">${alert.type.toUpperCase()}</span>
                </div>
                <div class="github-alert-content">${renderedContent}</div>
            </div>`;

            // Try each placeholder pattern until one matches
            for (const pattern of placeholderPatterns) {
                if (typeof pattern === 'string') {
                    if (processedHtml.includes(pattern)) {
                        processedHtml = processedHtml.replace(pattern, alertHtml);
                        break;
                    }
                } else {
                    // RegExp pattern
                    if (pattern.test(processedHtml)) {
                        processedHtml = processedHtml.replace(pattern, alertHtml);
                        break;
                    }
                }
            }
        }

        // Clean up
        this.alertData = [];

        return processedHtml;
    }

    /**
     * Get the appropriate icon for each alert type
     * @param {string} type - The alert type (warning, tip, note, caution, important)
     * @returns {string} The SVG icon HTML
     */
    getAlertIcon(type) {
        const icons = {
            warning: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>`,
            tip: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 16v-4"></path>
                <path d="M12 8h.01"></path>
            </svg>`,
            note: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
            </svg>`,
            caution: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>`,
            important: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>`
        };

        return icons[type] || icons.note;
    }

    /**
     * Render markdown content to HTML
     * @param {string} markdown - The markdown content
     * @returns {string} The rendered HTML
     */
    async renderMarkdown(markdown) {
        await this.loadMarkedLibrary();

        if (!window.marked) {
            return '<p>Markdown renderer not available</p>';
        }

        // Process GitHub-style alerts before rendering markdown
        const processedMarkdown = this.processGitHubAlerts(markdown);

        // Render markdown to HTML
        let html = window.marked.parse(processedMarkdown);

        // Post-process to replace alert placeholders with rendered alerts
        html = await this.processAlertPlaceholders(html);

        return html;
    }

    /**
     * Create a collapsible documentation section
     * @param {Object} options - Configuration options
     * @param {string} options.title - The title of the documentation section
     * @param {string} options.filePath - Path to the markdown file
     * @param {string} [options.section] - Specific section to extract
     * @param {number} [options.headingLevel] - Heading level for section extraction
     * @param {boolean} [options.defaultExpanded] - Whether to expand by default
     * @param {string} [options.className] - Additional CSS class
     * @returns {HTMLElement} The documentation section element
     */
    async createDocumentationSection(options) {
        const {
            title,
            filePath,
            section = null,
            headingLevel = 2,
            defaultExpanded = false,
            className = ''
        } = options;

        // Create container
        const container = document.createElement('div');
        container.className = `documentation-section ${className}`;

        // Create header
        const header = document.createElement('div');
        header.className = 'documentation-header';
        header.innerHTML = `
            <button class="documentation-toggle" aria-expanded="${defaultExpanded}">
                <span class="documentation-toggle-icon">${defaultExpanded ? '▼' : '▶'}</span>
                <span class="documentation-title">
                    <svg class="documentation-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                    ${title}
                </span>
            </button>
        `;

        // Create content area
        const content = document.createElement('div');
        content.className = 'documentation-content';
        content.style.display = defaultExpanded ? 'block' : 'none';

        // Add loading indicator
        content.innerHTML = '<div class="documentation-loading">Loading documentation...</div>';

        // Add event listener for toggle
        const toggleButton = header.querySelector('.documentation-toggle');
        const toggleIcon = header.querySelector('.documentation-toggle-icon');

        toggleButton.addEventListener('click', async () => {
            const isExpanded = toggleButton.getAttribute('aria-expanded') === 'true';

            if (!isExpanded) {
                // Expand
                toggleButton.setAttribute('aria-expanded', 'true');
                toggleIcon.textContent = '▼';
                content.style.display = 'block';

                // Load content if not already loaded
                if (content.querySelector('.documentation-loading')) {
                    try {
                        let markdown = await this.fetchMarkdown(filePath);

                        // Extract specific section if requested
                        if (section) {
                            markdown = this.extractSection(markdown, section, headingLevel);
                        }

                        const html = await this.renderMarkdown(markdown);
                        content.innerHTML = `<div class="documentation-body">${html}</div>`;

                        // Process tables to make them responsive
                        this.makeTablesResponsive(content);

                        // Add copy buttons to code blocks
                        this.addCodeCopyButtons(content);
                    } catch (error) {
                        content.innerHTML = `<div class="documentation-error">Failed to load documentation: ${error.message}</div>`;
                    }
                }
            } else {
                // Collapse
                toggleButton.setAttribute('aria-expanded', 'false');
                toggleIcon.textContent = '▶';
                content.style.display = 'none';
            }
        });

        container.appendChild(header);
        container.appendChild(content);

        return container;
    }

    /**
     * Make tables responsive by wrapping them in a scrollable container
     * @param {HTMLElement} container - The container element
     */
    makeTablesResponsive(container) {
        const tables = container.querySelectorAll('table');
        tables.forEach(table => {
            const wrapper = document.createElement('div');
            wrapper.className = 'documentation-table-wrapper';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });
    }

    /**
     * Add copy buttons to code blocks
     * @param {HTMLElement} container - The container element
     */
    addCodeCopyButtons(container) {
        const codeBlocks = container.querySelectorAll('pre code');
        codeBlocks.forEach(block => {
            const pre = block.parentElement;
            const wrapper = document.createElement('div');
            wrapper.className = 'documentation-code-wrapper';

            const copyButton = document.createElement('button');
            copyButton.className = 'documentation-code-copy';
            copyButton.textContent = 'Copy';
            copyButton.title = 'Copy code to clipboard';

            copyButton.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(block.textContent);
                    copyButton.textContent = 'Copied!';
                    setTimeout(() => {
                        copyButton.textContent = 'Copy';
                    }, 2000);
                } catch (error) {
                    console.error('Failed to copy:', error);
                    copyButton.textContent = 'Failed';
                    setTimeout(() => {
                        copyButton.textContent = 'Copy';
                    }, 2000);
                }
            });

            pre.parentNode.insertBefore(wrapper, pre);
            wrapper.appendChild(copyButton);
            wrapper.appendChild(pre);
        });
    }

    /**
     * Create inline documentation tooltip
     * @param {string} text - The tooltip text
     * @param {string} markdown - The markdown content for the tooltip
     * @returns {HTMLElement} The tooltip element
     */
    async createTooltip(text, markdown) {
        const container = document.createElement('span');
        container.className = 'documentation-tooltip-container';

        const trigger = document.createElement('span');
        trigger.className = 'documentation-tooltip-trigger';
        trigger.innerHTML = `
            ${text}
            <svg class="documentation-help-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
        `;

        const tooltip = document.createElement('div');
        tooltip.className = 'documentation-tooltip';
        const html = await this.renderMarkdown(markdown);
        tooltip.innerHTML = html;

        container.appendChild(trigger);
        container.appendChild(tooltip);

        return container;
    }
}

// Export as singleton
const documentationViewer = new DocumentationViewer();
window.DocumentationViewer = documentationViewer;
