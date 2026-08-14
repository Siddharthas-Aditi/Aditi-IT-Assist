/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Vitest owns unit tests under src/. Playwright owns e2e/ (its *.spec.ts
    // files use @playwright/test and must not be collected by Vitest).
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
  },
  server: {
    port: 5173,
    // Docker on Windows/macOS bind-mounts do not forward inotify events into
    // the container, so Vite's watcher never fires and it keeps serving the
    // cached transform of an edited file — the page looks unchanged until the
    // container is restarted. Polling costs a little CPU and makes HMR work.
    watch: {
      usePolling: process.env.VITE_USE_POLLING !== 'false',
      interval: 300,
    },
    // Proxy /api requests to backend
    // In Docker: http://aditi-backend:8000
    // In local dev (npm run dev): http://localhost:8000
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
