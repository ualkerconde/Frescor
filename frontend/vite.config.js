import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import basicSsl from '@vitejs/plugin-basic-ssl'

export default defineConfig({
  plugins: [
    react(),
    // HTTPS em desenvolvimento: celulares só liberam a câmera em contexto
    // seguro (HTTPS ou localhost). O certificado é autoassinado.
    basicSsl(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'Inventário',
        short_name: 'Inventário',
        description: 'App de contagem de estoque',
        theme_color: '#2563EB',
        background_color: '#FAFAFA',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ]
      },
      workbox: {
        // Cacheia os assets do app
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        // Estratégia network-first para chamadas à API
        runtimeCaching: [
          {
            urlPattern: /^http:\/\/127\.0\.0\.1:8000\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60 * 24 // 24 horas
              }
            }
          }
        ]
      }
    })
  ],
  server: {
    port: 3000,
    host: true,
    // As chamadas à API passam pelo próprio Vite (/backend/... ->
    // http://127.0.0.1:8000/...). Assim a página em HTTPS não chama uma
    // API em HTTP (o navegador bloquearia) e não há CORS em desenvolvimento.
    proxy: {
      '/backend': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/backend/, ''),
      },
    },
  }
})
