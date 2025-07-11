/**
 * Theme Manager - Handles dark/light theme switching
 */

class ThemeManager {
  constructor() {
    this.currentTheme = this.getStoredTheme() || 'light';
    this.init();
  }

  init() {
    // Apply the current theme
    this.applyTheme(this.currentTheme);

    // Set up theme toggle button
    this.setupThemeToggle();

    // Listen for system theme changes
    this.setupSystemThemeListener();
  }

  getSystemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  getStoredTheme() {
    return localStorage.getItem('qbit-manage-theme');
  }

  storeTheme(theme) {
    localStorage.setItem('qbit-manage-theme', theme);
  }

  applyTheme(theme) {
    const root = document.documentElement;

    // Remove existing theme attributes
    root.removeAttribute('data-theme');

    if (theme === 'dark') {
      root.setAttribute('data-theme', 'dark');
    } else if (theme === 'light') {
      root.setAttribute('data-theme', 'light');
    }
    // If theme is 'auto' or not set, let CSS handle it via prefers-color-scheme

    this.currentTheme = theme;
    this.updateThemeToggleIcon();
  }

  toggleTheme() {
    const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
    this.applyTheme(newTheme);
    this.storeTheme(newTheme);
  }

  setupThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
      themeToggle.addEventListener('click', () => {
        this.toggleTheme();
      });
    }
  }

  updateThemeToggleIcon() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    const sunIcon = themeToggle.querySelector('.icon-sun');
    const moonIcon = themeToggle.querySelector('.icon-moon');

    if (!sunIcon || !moonIcon) return;

    // Update title based on current theme
    const title = this.currentTheme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode';
    themeToggle.setAttribute('title', title);

    // The CSS handles showing/hiding icons based on data-theme attribute
    // No need to manually toggle visibility here
  }

  setupSystemThemeListener() {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', () => {
      // Only react to system changes if we're in auto mode
      if (!this.getStoredTheme()) {
        this.updateThemeToggleIcon();
      }
    });
  }

  // Public API
  setTheme(theme) {
    if (['light', 'dark'].includes(theme)) {
      this.applyTheme(theme);
      this.storeTheme(theme);
    }
  }

  getCurrentTheme() {
    return this.currentTheme;
  }

  getEffectiveTheme() {
    return this.currentTheme;
  }
}

// Create and export theme manager instance
export const themeManager = new ThemeManager();

// Also export the class for potential custom usage
export { ThemeManager };
