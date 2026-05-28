import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Proxy /api and /healthz to the Django dev server so cookies and CSRF flow
// without cross-origin gymnastics during local dev.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/healthz": { target: "http://localhost:8000", changeOrigin: true },
      "/readyz": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
