import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // maplibre-gl spins up its own module Worker for tile parsing. Vite's
  // dependency optimizer pre-bundles maplibre-gl but does not correctly
  // rewrite that worker's internal import, so the worker script 404s at
  // runtime, its Worker permanently fails to respond, and no tile ever
  // finishes decoding -- the map renders as a blank/black canvas with no
  // console error (DOM overlay controls still work since they're not
  // WebGL/worker-dependent). Excluding it from optimizeDeps makes Vite
  // serve maplibre-gl unbundled, so its worker import resolves correctly.
  optimizeDeps: {
    exclude: ["maplibre-gl"],
  },
  server: {
    port: 5173,
    // The API runs in the docker stack; proxying keeps the browser on one
    // origin so no CORS handling is needed in development.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/tiles": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
