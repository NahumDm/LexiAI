import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// Must match Docker host mapping `WEB_HOST_PORT` (default 18000 in docker-compose).
// For `manage.py runserver` on 8000, set VITE_DJANGO_PROXY_PORT=8000 in frontend/.env
const djangoProxyPort = process.env.VITE_DJANGO_PROXY_PORT || "18000";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    // Dev: browser calls same-origin /api → Vite forwards to Django (avoids CORS + localhost vs 127.0.0.1 issues)
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${djangoProxyPort}`,
        changeOrigin: true,
      },
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
