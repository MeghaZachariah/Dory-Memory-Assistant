import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, "/api/..." is forwarded to the backend on port 8000,
// so there are no CORS problems. For the hosted demo, set VITE_API_BASE.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
