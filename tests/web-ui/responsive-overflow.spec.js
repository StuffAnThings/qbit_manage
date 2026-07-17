import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(currentDirectory, "../..");
const webUiRoot = path.join(repositoryRoot, "web-ui");
const cssRoot = path.join(repositoryRoot, "web-ui/css");
const viewportWidths = [320, 375, 390, 430, 768, 1024, 1280, 1920];
const longTorrentPath = `/downloads/${"nested-directory/".repeat(20)}torrent-file-with-an-intentionally-long-name.mkv`;

async function loadRealApplication(page) {
  await page.route("http://qbm.test/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const relativePath = pathname === "/" ? "index.html" : pathname.replace(/^\/static\//, "").replace(/^\//, "");
    const filePath = path.resolve(webUiRoot, relativePath);

    if (!filePath.startsWith(`${webUiRoot}${path.sep}`) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      await route.fulfill({ status: 404, body: "Not found" });
      return;
    }
    await route.fulfill({ path: filePath });
  });
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.goto("http://qbm.test/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.headerComponent !== undefined);
}

function componentStylesheets() {
  const manifest = fs.readFileSync(path.join(cssRoot, "components.css"), "utf8");
  return [...manifest.matchAll(/@import ['"](.+?)['"];?/g)].map((match) => path.resolve(cssRoot, match[1]));
}

async function loadApplicationStyles(page) {
  const stylesheets = [
    path.join(cssRoot, "themes.css"),
    path.join(cssRoot, "main.css"),
    ...componentStylesheets(),
    path.join(cssRoot, "responsive.css"),
  ];

  for (const stylesheet of stylesheets) {
    await page.addStyleTag({ path: stylesheet });
  }

  await page.addStyleTag({ content: "*, *::before, *::after { animation: none !important; transition: none !important; }" });
}

function representativeApplicationMarkup(width) {
  const compactActionClass = width < 640 ? " btn-icon-only" : "";
  const actionLabel = width < 640 ? "" : "Action";
  return `<!doctype html>
    <html lang="en">
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body>
    <div id="app" class="app">
      <header class="header">
        <div class="header-left"><span class="app-title">qBit Manage</span></div>
        <div class="header-right">
          <div class="header-actions">
            <button class="btn btn-icon">Undo</button>
            <button class="btn btn-primary${compactActionClass}">${actionLabel}</button>
            <button class="btn btn-secondary${compactActionClass}">${actionLabel}</button>
            <button class="btn btn-secondary${compactActionClass}">${actionLabel}</button>
          </div>
        </div>
      </header>
      <div class="main-content">
        <nav class="sidebar"><div class="sidebar-header"><h3>Configuration Sections</h3></div></nav>
        <main class="content">
          <div class="content-header"><h2>qBittorrent Connection</h2></div>
          <section class="section-content">
            <div class="card">
              <div class="card-header">Configuration editor</div>
              <div class="card-body">
                <div class="form-group"><label class="form-label">Root directory</label>
                  <input class="form-input" value="${longTorrentPath}">
                </div>
              </div>
            </div>
            <div class="log-viewer">
              <div class="log-viewer-header"><span class="log-viewer-title">Run log</span></div>
              <div class="log-viewer-content"><div class="log-entry">
                <span class="log-timestamp">2026-07-16 12:00:00</span>
                <span class="log-level">INFO</span><span class="log-message">${longTorrentPath}</span>
              </div></div>
            </div>
          </section>
        </main>
      </div>
      <footer class="footer"><span>qBit Manage</span></footer>
    </div>
    <aside class="command-panel-drawer active">
      <div class="command-panel-header"><h3>Command output</h3></div>
      <div class="command-panel-content">
        <div class="log-viewer-content"><div class="log-entry"><span class="log-message">${longTorrentPath}</span></div></div>
      </div>
    </aside>
    </body>
    </html>`;
}

for (const width of viewportWidths) {
  test(`contains representative content at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.setContent(representativeApplicationMarkup(width));
    await loadApplicationStyles(page);

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      overflowingElements: [...document.querySelectorAll("body *")]
        .filter((element) => {
          const bounds = element.getBoundingClientRect();
          const closedSidebar = element.closest(".sidebar:not(.mobile-open)");
          if (closedSidebar) {
            const sidebarBounds = closedSidebar.getBoundingClientRect();
            return bounds.left < sidebarBounds.left || bounds.right > sidebarBounds.right;
          }
          return bounds.left < 0 || bounds.right > document.documentElement.clientWidth;
        })
        .slice(0, 10)
        .map((element) => ({
          classes: element.className,
          tag: element.tagName,
          width: element.getBoundingClientRect().width,
        })),
    }));

    expect(dimensions.scrollWidth, JSON.stringify(dimensions)).toBe(dimensions.clientWidth);
    expect(dimensions.overflowingElements, JSON.stringify(dimensions)).toEqual([]);
  });
}

for (const width of viewportWidths) {
  test(`real application shell does not overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await loadRealApplication(page);
    await page.evaluate((longPath) => {
      const section = document.getElementById("section-content");
      section.innerHTML = `<div class="card"><div class="card-body"><input class="form-input" value="${longPath}"></div></div>`;

      const drawer = document.getElementById("command-panel-drawer");
      drawer.classList.remove("hidden");
      drawer.classList.add("active");
      drawer.innerHTML = `<div class="command-panel-content"><div class="log-viewer-content"><div class="log-entry"><span class="log-message">${longPath}</span></div></div></div>`;
    }, longTorrentPath);

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      overflowingElements: [...document.querySelectorAll("body *")]
        .filter((element) => {
          const bounds = element.getBoundingClientRect();
          for (
            let ancestor = element.parentElement;
            ancestor && ancestor !== document.body && ancestor !== document.documentElement;
            ancestor = ancestor.parentElement
          ) {
            if (["auto", "scroll", "hidden", "clip"].includes(getComputedStyle(ancestor).overflowX)) return false;
          }
          const closedSidebar = element.closest(".sidebar:not(.mobile-open)");
          if (closedSidebar) {
            const sidebarBounds = closedSidebar.getBoundingClientRect();
            return bounds.left < sidebarBounds.left || bounds.right > sidebarBounds.right;
          }
          return bounds.left < 0 || bounds.right > document.documentElement.clientWidth;
        })
        .slice(0, 10)
        .map((element) => ({
          classes: element.className,
          tag: element.tagName,
          right: element.getBoundingClientRect().right,
          width: element.getBoundingClientRect().width,
        })),
    }));
    expect(dimensions.scrollWidth, JSON.stringify(dimensions)).toBe(dimensions.clientWidth);
    expect(dimensions.overflowingElements, JSON.stringify(dimensions)).toEqual([]);
  });
}

test("real header restores actions at the canonical 640px breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 639, height: 900 });
  await loadRealApplication(page);
  const saveButton = page.locator("#save-config-btn");
  await expect(saveButton).toHaveClass(/btn-icon-only/);
  await expect(saveButton).toHaveCSS("width", "32px");
  const compactLabels = await saveButton.evaluate((button) =>
    [...button.childNodes].filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => node.textContent.trim())
  );
  expect(compactLabels).not.toHaveLength(0);
  expect(compactLabels.every((label) => label === "")).toBe(true);

  await page.setViewportSize({ width: 640, height: 900 });
  await expect(saveButton).not.toHaveClass(/btn-icon-only/);
  await expect(saveButton).not.toHaveCSS("width", "32px");
  await expect(saveButton).toContainText("Save");
});
