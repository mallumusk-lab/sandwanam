import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000 and is reached through this proxy, so the
// browser sees a single origin (same as production, where Vercel serves both).
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5174,
    strictPort: false,
    proxy: {
      "/api": { target: process.env.API_TARGET || "http://127.0.0.1:8001", changeOrigin: false },
    },
  },
  build: {
    target: "es2020",
    sourcemap: false,
    chunkSizeWarningLimit: 250,
  },
});
