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
