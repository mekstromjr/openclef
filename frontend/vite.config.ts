import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    port: 5173,
    // Dev-mode end-to-end: the Vite dev server proxies API calls to the
    // FastAPI backend so the landing page can fetch /api/v1/version
    // without a CORS dance. In prod the Python app serves both the
    // static build and the API on the same origin.
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000'
    }
  }
});
