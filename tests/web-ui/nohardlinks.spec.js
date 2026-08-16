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

test("nohardlinks schema and form use false category-ignore default", async ({ page }) => {
  await loadApplication(page);

  const result = await page.evaluate(async () => {
    const { nohardlinksSchema } = await import("/static/js/config-schemas/nohardlinks.js");
    const { ConfigForm } = await import("/static/js/components/config-form.js");
    const form = new ConfigForm();

    return {
      patternDefault: nohardlinksSchema.patternProperties[".*"].properties.ignore_category_dir.default,
      dynamicDefault: nohardlinksSchema.additionalProperties.properties.ignore_category_dir.default,
      legacy: form._preprocessComplexObjectData("nohardlinks", ["Movies"]),
      missing: form._preprocessComplexObjectData("nohardlinks", { Movies: {} }),
      explicit: form._preprocessComplexObjectData("nohardlinks", {
        Movies: { ignore_category_dir: true },
      }),
    };
  });

  expect(result.patternDefault).toBe(false);
  expect(result.dynamicDefault).toBe(false);
  expect(result.legacy.Movies.ignore_category_dir).toBe(false);
  expect(result.missing.Movies.ignore_category_dir).toBe(false);
  expect(result.explicit.Movies.ignore_category_dir).toBe(true);
});

test("saving an empty nohardlinks category keeps false category-ignore default", async ({ page }) => {
  await loadApplication(page);

  const savedCategory = await page.evaluate(async () => {
    const app = window.app;
    app.currentConfig = "config.yml";
    app.currentSection = "nohardlinks";
    app.configData = { nohardlinks: { Movies: null } };
    app.configForm.currentData = { Movies: null };
    app.historyManager.createCheckpoint = async () => {};
    app.configForm.loadSection = async () => {};
    app.updateSaveButton = () => {};
    app.clearAllDirtyIndicators = () => {};

    let savedData;
    app.api.updateConfig = async (_filename, payload) => {
      savedData = payload.data;
    };
    app.api.getConfig = async () => ({ data: savedData });

    await app.saveConfig();
    return savedData.nohardlinks.Movies;
  });

  expect(savedCategory).toEqual({
    ignore_root_dir: true,
    ignore_category_dir: false,
  });
});
