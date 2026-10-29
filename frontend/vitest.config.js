// Configuração só dos testes (D83). Separada do vite.config.js para não
// carregar o PWA nem o HTTPS de desenvolvimento; o build de produção não muda.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
  },
})
