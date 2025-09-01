import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// Optional overrides via env when needed:
//   VITE_API_PROXY_TARGET=http://localhost:8000
//   VITE_HMR_CLIENT_PORT=5173
const API_PROXY_TARGET =
  process.env.VITE_API_PROXY_TARGET || "http://localhost:8000";
const HMR_CLIENT_PORT = process.env.VITE_HMR_CLIENT_PORT
  ? Number(process.env.VITE_HMR_CLIENT_PORT)
  : undefined;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    ...(HMR_CLIENT_PORT ? { hmr: { clientPort: HMR_CLIENT_PORT } } : {}),
    proxy: {
      // Frontend calls `/api/*` in dev; this proxies to FastAPI to avoid CORS.
      "/api": {
        target: API_PROXY_TARGET,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
