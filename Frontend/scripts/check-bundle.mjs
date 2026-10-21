// Offline build check: bundles the whole app with esbuild (no network, nothing written
// to the repository) so missing imports, syntax errors and accidental dependencies on
// removed packages fail fast. `vite build` remains the production build.
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const ALLOWED_PACKAGES = new Set(["react", "react-dom", "react-router-dom", "react-router", "@remix-run/router", "scheduler"]);

const result = await build({
  absWorkingDir: root,
  entryPoints: ["src/main.jsx"],
  bundle: true,
  write: false,
  outdir: "out",
  metafile: true,
  minify: true,
  splitting: true,
  format: "esm",
  jsx: "automatic",
  target: "es2020",
  loader: { ".svg": "file", ".png": "file" },
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "silent",
}).catch((error) => {
  for (const message of error.errors ?? []) {
    console.error(`✗ ${message.location?.file ?? ""}:${message.location?.line ?? ""} ${message.text}`);
  }
  process.exit(1);
});

for (const warning of result.warnings) console.warn(`! ${warning.location?.file}:${warning.location?.line} ${warning.text}`);

const packages = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
  const match = /node_modules\/((?:@[^/]+\/)?[^/]+)/.exec(input);
  if (match) packages.add(match[1]);
}
const unexpected = [...packages].filter((name) => !ALLOWED_PACKAGES.has(name));
let total = 0;
for (const [file, info] of Object.entries(result.metafile.outputs)) {
  if (file.endsWith(".js") || file.endsWith(".css")) total += info.bytes;
}
console.log(`Bundled ${Object.keys(result.metafile.inputs).length} modules, ${Object.keys(result.metafile.outputs).length} output files, ${(total / 1024).toFixed(1)} KB minified.`);
console.log(`Packages: ${[...packages].sort().join(", ")}`);
if (unexpected.length) {
  console.error(`✗ Unexpected dependencies in the bundle: ${unexpected.join(", ")}`);
  process.exit(1);
}
if (result.warnings.length) process.exit(1);
console.log("✓ Bundle check passed");
