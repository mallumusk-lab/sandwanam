// Runs every tests/*.test.js(x) with Node's built-in test runner. Each file is bundled
// with esbuild first (JSX, CSS imports, React), into the OS temp directory, so tests
// need no extra packages and nothing is written into the repository.
import { build } from "esbuild";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const testDir = join(root, "tests");
const files = readdirSync(testDir).filter((name) => /\.test\.jsx?$/.test(name)).sort();
const outDir = mkdtempSync(join(tmpdir(), "goldloan-web-tests-"));

try {
  await build({
    absWorkingDir: root,
    entryPoints: files.map((name) => join(testDir, name)),
    outdir: outDir,
    outExtension: { ".js": ".mjs" },
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node18",
    jsx: "automatic",
    loader: { ".css": "empty", ".svg": "empty", ".png": "empty" },
    define: { "process.env.NODE_ENV": '"test"', "import.meta.env.DEV": "false" },
    external: ["node:*"],
    banner: { js: "import { createRequire as __cr } from 'node:module'; const require = __cr(import.meta.url);" },
    logLevel: "warning",
  });
  const outputs = readdirSync(outDir).filter((name) => name.endsWith(".mjs")).map((name) => join(outDir, name));
  const result = spawnSync(process.execPath, ["--test", ...outputs], { stdio: "inherit", cwd: root });
  process.exitCode = result.status ?? 1;
} finally {
  rmSync(outDir, { recursive: true, force: true });
}
