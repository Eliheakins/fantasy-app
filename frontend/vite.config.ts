/// <reference types="vitest/config" />
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, URL } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * @duckdb/duckdb-wasm worker scripts end with `//# sourceMappingURL=*.map`, but the
 * package does not always ship those `.map` files. Vite then logs ENOENT when resolving
 * source maps. Stub missing maps once so dev stays quiet (writes under `node_modules/`).
 */
function ensureDuckdbWorkerSourcemaps(): Plugin {
  const emptyMap = '{"version":3,"sources":[],"names":[],"mappings":""}';

  return {
    name: "ensure-duckdb-worker-sourcemaps",
    buildStart() {
      const dist = fileURLToPath(new URL("./node_modules/@duckdb/duckdb-wasm/dist", import.meta.url));
      if (!fs.existsSync(dist)) {
        return;
      }
      for (const name of fs.readdirSync(dist)) {
        if (!name.endsWith(".worker.js")) {
          continue;
        }
        const mapPath = path.join(dist, `${name}.map`);
        if (!fs.existsSync(mapPath)) {
          fs.writeFileSync(mapPath, emptyMap, "utf8");
        }
      }
    },
  };
}

/**
 * Vite handles `.wasm` assets out of the box via `?url` imports — you do **not**
 * need `vite-plugin-wasm` for DuckDB-WASM’s prebuilt bundles.
 *
 * Optional: if you import raw `.wasm` as a module (`import wasm from 'x.wasm'`), add:
 *   import wasm from "vite-plugin-wasm";
 *   import topLevelAwait from "vite-top-level-await";
 *
 * For the **COI / multithreaded** bundle (`coi`), enable cross-origin isolation in dev:
 *   (see `server.headers` below) — required for SharedArrayBuffer in some browsers.
 */
function resolveApacheArrowDom(): string {
  const candidates = [
    fileURLToPath(new URL("./node_modules/apache-arrow/Arrow.dom.js", import.meta.url)),
    fileURLToPath(
      new URL("./node_modules/@duckdb/duckdb-wasm/node_modules/apache-arrow/Arrow.dom.js", import.meta.url),
    ),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  throw new Error(
    '[vite] apache-arrow Arrow.dom.js not found. Run npm install in frontend (apache-arrow ships broken "exports"; we alias to Arrow.dom.js).',
  );
}

const apacheArrowDom = resolveApacheArrowDom();

export default defineConfig({
  plugins: [ensureDuckdbWorkerSourcemaps(), react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      /**
       * apache-arrow@17 `exports` reference `*.mjs` builds that are missing from the npm tarball;
       * only `Arrow.dom.js` (browser/CJS) is present. Point the bare specifier at that file so Vite
       * and @duckdb/duckdb-wasm's dependency both resolve.
       */
      "apache-arrow": apacheArrowDom,
    },
  },
  server: {
    port: 3000,
    // metrics/metrics.json lives at the repo root, outside this project folder.
    fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] },
    // Uncomment if you use initDB("coi") (COI bundle) and need pthreads / SAB:
    // headers: {
    //   "Cross-Origin-Opener-Policy": "same-origin",
    //   "Cross-Origin-Embedder-Policy": "require-corp",
    // },
  },
  optimizeDeps: {
    exclude: ["@duckdb/duckdb-wasm"],
  },
  worker: {
    format: "es",
  },
  test: {
    include: ["src/**/*.test.ts"],
    setupFiles: ["src/test/setup.ts"],
  },
});
