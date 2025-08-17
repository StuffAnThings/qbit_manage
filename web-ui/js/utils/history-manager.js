/**
 * History Manager for Config Undo/Redo Functionality
 * Manages undo/redo state for each config file with hybrid approach:
 * - In-memory storage for recent changes (fast operations)
 * - Integration with existing backup system for persistence
 */

export class HistoryManager {
    constructor(api) {
        this.api = api;
        this.histories = new Map(); // Per config file: { configName: HistoryState }
        this.maxInMemoryStates = 50; // Maximum states to keep in memory
        this.maxBackupStates = 200; // Maximum backup files to track
    }

    /**
     * Get or create history state for a config file
     */
    _getHistoryState(configName) {
        if (!this.histories.has(configName)) {
            this.histories.set(configName, {
                states: [], // Array of state objects
                currentIndex: -1, // Current position in history
                savedIndex: -1, // Index of last saved state
                backupMapping: new Map(), // Maps state indices to backup file names
            });
        }
        return this.histories.get(configName);
    }

    /**
     * Create a checkpoint in history
     * @param {string} configName - Name of the config file
     * @param {Object} state - Current config state
     * @param {string} description - Description of the change
     * @param {boolean} isSavePoint - Whether this is a save operation
     */
    createCheckpoint(configName, state, description = 'Config change', isSavePoint = false) {
        const history = this._getHistoryState(configName);

        // Create state object
        const stateEntry = {
            data: JSON.parse(JSON.stringify(state)), // Deep clone
            timestamp: Date.now(),
            description,
            isSavePoint,
            id: this._generateStateId()
        };

        // If we're not at the end of history, remove future states (redo history)
        if (history.currentIndex < history.states.length - 1) {
            history.states.splice(history.currentIndex + 1);
            // Clean up backup mappings for removed states
            for (let i = history.currentIndex + 1; i < history.states.length; i++) {
                history.backupMapping.delete(i);
            }
        }

        // Add new state
        history.states.push(stateEntry);
        history.currentIndex = history.states.length - 1;

        // Mark save point
        if (isSavePoint) {
            history.savedIndex = history.currentIndex;
        }

        // Manage memory by removing old states if we exceed the limit
        this._manageMemoryLimit(configName);

        console.log(`History checkpoint created for ${configName}: ${description}`);
        return stateEntry.id;
    }

    /**
     * Undo the last change
     * @param {string} configName - Name of the config file
     * @returns {Object|null} - Previous state or null if can't undo
     */
    async undo(configName) {
        const history = this._getHistoryState(configName);

        if (!this.canUndo(configName)) {
            return null;
        }

        history.currentIndex--;
        const targetState = history.states[history.currentIndex];

        // If state is not in memory, try to load from backup
        if (!targetState.data && history.backupMapping.has(history.currentIndex)) {
            const backupName = history.backupMapping.get(history.currentIndex);
            try {
                targetState.data = await this._loadFromBackup(configName, backupName);
            } catch (error) {
                console.error(`Failed to load backup for undo: ${error.message}`);
                // Revert index change
                history.currentIndex++;
                return null;
            }
        }

        console.log(`Undo: ${targetState.description} (${configName})`);

        // Notify app of state change
        const event = new CustomEvent('history-state-change', {
            detail: {
                configName,
                data: targetState.data
            }
        });
        document.dispatchEvent(event);

        return {
            data: targetState.data,
            description: targetState.description,
            timestamp: targetState.timestamp
        };
    }

    /**
     * Redo the next change
     * @param {string} configName - Name of the config file
     * @returns {Object|null} - Next state or null if can't redo
     */
    async redo(configName) {
        const history = this._getHistoryState(configName);

        if (!this.canRedo(configName)) {
            return null;
        }

        history.currentIndex++;
        const targetState = history.states[history.currentIndex];

        // If state is not in memory, try to load from backup
        if (!targetState.data && history.backupMapping.has(history.currentIndex)) {
            const backupName = history.backupMapping.get(history.currentIndex);
            try {
                targetState.data = await this._loadFromBackup(configName, backupName);
            } catch (error) {
                console.error(`Failed to load backup for redo: ${error.message}`);
                // Revert index change
                history.currentIndex--;
                return null;
            }
        }

        console.log(`Redo: ${targetState.description} (${configName})`);

        // Notify app of state change
        const event = new CustomEvent('history-state-change', {
            detail: {
                configName,
                data: targetState.data
            }
        });
        document.dispatchEvent(event);

        return {
            data: targetState.data,
            description: targetState.description,
            timestamp: targetState.timestamp
        };
    }

    /**
     * Check if undo is possible
     * @param {string} configName - Name of the config file
     * @returns {boolean}
     */
    canUndo(configName) {
        const history = this._getHistoryState(configName);
        return history.currentIndex > 0;
    }

    /**
     * Check if redo is possible
     * @param {string} configName - Name of the config file
     * @returns {boolean}
     */
    canRedo(configName) {
        const history = this._getHistoryState(configName);
        const canRedo = history.currentIndex < history.states.length - 1;
        return canRedo;
    }

    /**
     * Check if there are unsaved changes
     * @param {string} configName - Name of the config file
     * @returns {boolean}
     */
    hasUnsavedChanges(configName) {
        const history = this._getHistoryState(configName);
        return history.currentIndex !== history.savedIndex;
    }

    /**
     * Get current state description
     * @param {string} configName - Name of the config file
     * @returns {string}
     */
    getCurrentStateDescription(configName) {
        const history = this._getHistoryState(configName);
        if (history.currentIndex >= 0 && history.currentIndex < history.states.length) {
            return history.states[history.currentIndex].description;
        }
        return 'Initial state';
    }

    /**
     * Get undo description (what would be undone)
     * @param {string} configName - Name of the config file
     * @returns {string|null}
     */
    getUndoDescription(configName) {
        const history = this._getHistoryState(configName);
        if (this.canUndo(configName)) {
            return history.states[history.currentIndex - 1].description;
        }
        return null;
    }

    /**
     * Get redo description (what would be redone)
     * @param {string} configName - Name of the config file
     * @returns {string|null}
     */
    getRedoDescription(configName) {
        const history = this._getHistoryState(configName);
        if (this.canRedo(configName)) {
            return history.states[history.currentIndex + 1].description;
        }
        return null;
    }

    /**
     * Clear history for a config file
     * @param {string} configName - Name of the config file
     */
    clearHistory(configName) {
        this.histories.delete(configName);
        console.log(`History cleared for ${configName}`);
    }

    /**
     * Initialize history from existing backups
     * @param {string} configName - Name of the config file
     */
    async initializeFromBackups(configName, initialData) {
        const history = this._getHistoryState(configName);

        // Skip backup initialization if API doesn't support backups
        if (!this.api.supportsBackups) {
            console.info(`Backup feature not available. Skipping initialization for ${configName}.`);
            // Create initial state if history is empty
            if (history.states.length === 0) {
                this._createInitialState(history, initialData);
            }
            return;
        }

        try {
            const backups = await this.api.listBackups(configName);

            // Sort backups by timestamp (oldest first)
            const sortedBackups = backups.backups.sort((a, b) =>
                new Date(a.timestamp) - new Date(b.timestamp)
            );

            // Create history entries for existing backups
            sortedBackups.forEach((backup, index) => {
                const stateEntry = {
                    data: null, // Will be loaded on demand
                    timestamp: new Date(backup.timestamp).getTime(),
                    description: `Backup: ${backup.filename}`,
                    isSavePoint: true,
                    id: this._generateStateId()
                };

                history.states.push(stateEntry);
                history.backupMapping.set(index, backup.filename);
            });

            if (history.states.length > 0) {
                // Create an additional state for the current config (beyond backups)
                const currentStateEntry = {
                    data: initialData, // Current config data
                    timestamp: Date.now(),
                    description: `Latest config (${configName})`,
                    isSavePoint: true,
                    id: this._generateStateId()
                };

                history.states.push(currentStateEntry);
                history.currentIndex = history.states.length - 1; // Point to current state
                history.savedIndex = history.currentIndex;

            } else {
                // Create initial state if no backups found
                this._createInitialState(history, initialData);
            }

            console.log(`Initialized history for ${configName} with ${history.states.length} backup states`);
        } catch (error) {
            if (error.message.includes('Not Found')) {
                console.info(`Backup feature not implemented for ${configName}. Proceeding without backup history.`);
                // Mark API as not supporting backups for future calls
                this.api.supportsBackups = false;

                // Create initial state if history is empty
                if (history.states.length === 0) {
                    this._createInitialState(history, initialData);
                }
            } else {
                console.warn(`Failed to initialize history from backups for ${configName}:`, error);
            }
        }
    }

    _createInitialState(history, initialData) {
        // Create an initial backup-like state
        const initialStateEntry = {
            data: null, // Will be loaded on demand like backups
            timestamp: Date.now() - 1000, // Slightly in the past
            description: 'Initial backup state',
            isSavePoint: true,
            id: this._generateStateId()
        };

        // Create current state entry
        const currentStateEntry = {
            data: initialData,
            timestamp: Date.now(),
            description: `Current state`,
            isSavePoint: true,
            id: this._generateStateId()
        };

        history.states.push(initialStateEntry);
        history.states.push(currentStateEntry);
        history.currentIndex = 1; // Point to current state
        history.savedIndex = 1;

        console.log('Created initial history state with current state beyond initial backup');
    }

    /**
     * Associate a backup file with the current state
     * @param {string} configName - Name of the config file
     * @param {string} backupFilename - Name of the backup file
     */
    associateBackup(configName, backupFilename) {
        const history = this._getHistoryState(configName);
        if (history.currentIndex >= 0) {
            history.backupMapping.set(history.currentIndex, backupFilename);
            console.log(`Associated backup ${backupFilename} with state ${history.currentIndex} for ${configName}`);
        }
    }

    /**
     * Manage memory by removing old states
     * @private
     */
    _manageMemoryLimit(configName) {
        const history = this._getHistoryState(configName);

        if (history.states.length > this.maxInMemoryStates) {
            const removeCount = history.states.length - this.maxInMemoryStates;

            // Remove old states but keep their metadata for backup references
            for (let i = 0; i < removeCount; i++) {
                const state = history.states[i];
                if (state.data) {
                    // Clear data but keep metadata
                    state.data = null;
                }
            }

            console.log(`Cleared data for ${removeCount} old states in ${configName} to manage memory`);
        }
    }

    /**
     * Load state from backup file
     * @private
     */
    async _loadFromBackup(configName, backupFilename) {
        try {
            const response = await this.api.restoreConfig(backupFilename);
            return response.data;
        } catch (error) {
            throw new Error(`Failed to load backup ${backupFilename}: ${error.message}`);
        }
    }

    /**
     * Generate unique state ID
     * @private
     */
    _generateStateId() {
        return `state_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Get history statistics for debugging
     * @param {string} configName - Name of the config file
     * @returns {Object}
     */
    getHistoryStats(configName) {
        const history = this._getHistoryState(configName);
        return {
            totalStates: history.states.length,
            currentIndex: history.currentIndex,
            savedIndex: history.savedIndex,
            canUndo: this.canUndo(configName),
            canRedo: this.canRedo(configName),
            hasUnsavedChanges: this.hasUnsavedChanges(configName),
            memoryStates: history.states.filter(s => s.data !== null).length,
            backupStates: history.backupMapping.size
        };
    }
}
