import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, /api is proxied to the FastAPI server so the browser sees ONE origin
// (same as production, where Vercel / nginx rewrite /api to the API).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.API_PROXY ?? "http://127.0.0.1:8001", changeOrigin: false },
    },
  },
});
