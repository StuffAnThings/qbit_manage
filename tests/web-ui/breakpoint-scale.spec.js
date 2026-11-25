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

// Height conditions are exempt; strip only those so any width condition in the same query is still checked.
function nonCanonicalWidths(mediaQuery) {
  const withoutHeight = mediaQuery.replace(/\([^)]*height[^)]*\)/g, "");
  return [...withoutHeight.matchAll(/(\d+(?:\.\d+)?)px/g)].filter((width) => !canonicalBreakpointsPx.has(Number(width[1])));
}

test("height conditions do not exempt a non-canonical width in the same media query", () => {
  expect(nonCanonicalWidths("@media (max-width: 600px) and (max-height: 500px)")).toHaveLength(1);
  expect(nonCanonicalWidths("@media (max-width: 640px) and (max-height: 500px)")).toHaveLength(0);
  expect(nonCanonicalWidths("@media (max-height: 500px)")).toHaveLength(0);
});

test("width media queries only use the canonical 640/768/1024/1280 breakpoints", () => {
  const offenders = [];
  for (const stylesheet of stylesheets(cssRoot)) {
    const css = fs.readFileSync(stylesheet, "utf8");
    for (const mediaQuery of css.matchAll(/@media[^{]+/g)) {
      if (nonCanonicalWidths(mediaQuery[0]).length > 0) {
        offenders.push(`${path.relative(cssRoot, stylesheet)}: ${mediaQuery[0].trim()}`);
      }
    }
  }
  expect(offenders).toEqual([]);
});
