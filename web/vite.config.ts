import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
