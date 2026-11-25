import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const webUiRoot = path.resolve(currentDirectory, "../../web-ui");

async function loadApplication(page) {
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
  await page.waitForFunction(() => window.app !== undefined);
}

test("undo and redo send the backup that holds the target state's secrets", async ({ page }) => {
  await loadApplication(page);

  const puts = await page.evaluate(async () => {
    const app = window.app;
    app.currentConfig = "config.yml";
    app.currentSection = "nohardlinks";
    app.configData = { nohardlinks: { Movies: null } };
    app.configForm.currentData = { Movies: null };
    app.configForm.loadSection = async () => {};
    app.updateSaveButton = () => {};
    app.clearAllDirtyIndicators = () => {};
    app.api.supportsBackups = false;
    await app.historyManager.initializeFromBackups("config.yml", app.configData);

    const puts = [];
    let n = 0;
    app.api.put = async (_endpoint, body) => {
      puts.push(body.restored_from ?? null);
      return { status: "success", backup_file: `config_${++n}.yml` };
    };
    app.api.getConfig = async () => ({ data: app.configData });

    await app.saveConfig();
    await app.undoConfig();
    await app.redoConfig();
    return puts;
  });

  // save (no restore), undo (the backup the save made), redo (the backup the undo made)
  expect(puts).toEqual([null, "config_1.yml", "config_2.yml"]);
});

test("a new edit after undo drops the backups of the discarded redo states", async ({ page }) => {
  await loadApplication(page);

  const mapped = await page.evaluate(async () => {
    const hm = window.app.historyManager;
    await hm.initializeFromBackups("x.yml", { a: 0 });
    hm.createCheckpoint("x.yml", { a: 1 }, "one");
    hm.createCheckpoint("x.yml", { a: 2 }, "two");
    const history = hm.histories.get("x.yml");
    history.backupMapping.set(2, "x_stale.yml");
    history.currentIndex = 1;
    hm.createCheckpoint("x.yml", { a: 3 }, "branch");
    return [...history.backupMapping.values()];
  });

  expect(mapped).not.toContain("x_stale.yml");
});

test("loading a config forgets a restored backup, and validate sends it", async ({ page }) => {
  await loadApplication(page);

  const sent = await page.evaluate(async () => {
    const api = window.app.api;
    const bodies = [];
    api.post = async (_endpoint, body) => (bodies.push(body.restored_from ?? null), {});
    api.get = async () => ({ data: {} });
    api.restoredFrom = "config_20260101_000000.yml";
    await api.validateConfig("config.yml", { data: {} });
    await api.getConfig("other.yml");
    await api.validateConfig("other.yml", { data: {} });
    return bodies;
  });

  expect(sent).toEqual(["config_20260101_000000.yml", null]);
});
