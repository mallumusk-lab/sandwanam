// WCAG 2.2 AA contrast for every colour pair the UI uses, in both themes.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";

// Tests run with the Frontend directory as the working directory (scripts/run-tests.mjs).
const css = readFileSync(join(process.cwd(), "src/ui/tokens.css"), "utf8");

function block(selector) {
  const start = css.indexOf(selector);
  assert.ok(start >= 0, `missing ${selector}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const tokens = {};
  for (const match of css.slice(open + 1, close).matchAll(/--(color-[\w-]+):\s*(#[0-9a-f]{6})/gi)) {
    tokens[match[1]] = match[2];
  }
  return tokens;
}

function luminance(hex) {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

const TEXT_PAIRS = [
  ["text", "bg"], ["text", "surface"], ["text", "surface-2"],
  ["text-muted", "bg"], ["text-muted", "surface"], ["text-muted", "surface-2"],
  ["on-primary", "primary"], ["on-primary", "primary-hover"],
  ["primary-text", "surface"], ["primary-text", "bg"], ["primary-text", "primary-soft"],
  ["success", "success-soft"], ["success", "surface"],
  ["warning", "warning-soft"], ["warning", "surface"],
  ["danger", "danger-soft"], ["danger", "surface"],
  ["info", "info-soft"], ["info", "surface"],
];
const UI_PAIRS = [
  ["focus", "surface"], ["focus", "bg"], ["border-strong", "surface"], ["primary", "surface"],
  ["chart-1", "surface"], ["chart-2", "surface"],
];

for (const [name, selector] of [["light", ":root {"], ["dark", ':root[data-theme="dark"]']]) {
  const tokens = block(selector);
  test(`${name} theme text contrast is at least 4.5:1`, () => {
    for (const [fg, bg] of TEXT_PAIRS) {
      const ratio = contrast(tokens[`color-${fg}`], tokens[`color-${bg}`]);
      assert.ok(ratio >= 4.5, `${fg} on ${bg}: ${ratio.toFixed(2)}`);
    }
  });
  test(`${name} theme component contrast is at least 3:1`, () => {
    for (const [fg, bg] of UI_PAIRS) {
      const ratio = contrast(tokens[`color-${fg}`], tokens[`color-${bg}`]);
      assert.ok(ratio >= 3, `${fg} on ${bg}: ${ratio.toFixed(2)}`);
    }
  });
}

test("the system dark theme matches the explicit dark theme", () => {
  assert.deepEqual(block(':root:not([data-theme="light"])'), block(':root[data-theme="dark"]'));
});
