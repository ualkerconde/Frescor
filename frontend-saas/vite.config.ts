/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Frontend do SaaS (gestor da central). Desktop, http em localhost: sem
// câmera, então não precisa de HTTPS (ao contrário do app mobile).
// As chamadas à API passam pelo próprio Vite (/backend/... ->
// http://127.0.0.1:8000/...), como no app: sem CORS em desenvolvimento.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
  server: {
    port: 3001,
    strictPort: true,
    proxy: {
      '/backend': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (caminho) => caminho.replace(/^\/backend/, ''),
      },
    },
  },
})
