import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const cssRoot = path.resolve(currentDirectory, "../../web-ui/css");
const canonicalBreakpointsPx = new Set([640, 768, 1024, 1280]);

function stylesheets(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return stylesheets(entryPath);
    return entry.name.endsWith(".css") ? [entryPath] : [];
  });
}

test("width media queries only use the canonical 640/768/1024/1280 breakpoints", () => {
  const offenders = [];
  for (const stylesheet of stylesheets(cssRoot)) {
    const css = fs.readFileSync(stylesheet, "utf8");
    for (const mediaQuery of css.matchAll(/@media[^{]+/g)) {
      for (const width of mediaQuery[0].matchAll(/(\d+(?:\.\d+)?)px/g)) {
        const isHeightQuery = /height/.test(mediaQuery[0]);
        if (!isHeightQuery && !canonicalBreakpointsPx.has(Number(width[1]))) {
          offenders.push(`${path.relative(cssRoot, stylesheet)}: ${mediaQuery[0].trim()}`);
        }
      }
    }
  }
  expect(offenders).toEqual([]);
});
