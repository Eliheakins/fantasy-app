/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: {
    rolldownOptions: {
      output: {
        // Rolldown's code splitting (Vite 8): the framework sits in its own chunk, so an app-only deploy leaves its hash
        // and browser cache alone. scheduler, query-core and react-router's helpers come along with their packages.
        codeSplitting: {
          groups: [
            {
              name: "vendor",
              test: /[\\/]node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom|cookie|set-cookie-parser|@tanstack[\\/](react-query|query-core))[\\/]/,
            },
          ],
        },
      },
    },
  },
  server: {
    proxy: { "/api": API_TARGET },
    // metrics/metrics.json sits at the repo root. Never allow the root itself: data/ holds private nfl_ecr.
    fs: { allow: [import.meta.dirname, path.resolve(import.meta.dirname, "../metrics")] },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    // before each test: vi.unstubAllGlobals() and restore every vi.spyOn (vi.fn call history is cleared by the default clearMocks)
    unstubGlobals: true,
    restoreMocks: true,
  },
});
