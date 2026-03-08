import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

import path from 'path'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(() => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // Disable the modulePreload polyfill inline script — all target browsers support
    // <link rel="modulepreload"> natively, and the inline script violates our CSP.
    modulePreload: { polyfill: false },
  },
  esbuild: {
    // Strip console.* calls and debugger statements from production builds
    drop: ['console', 'debugger'] as ('console' | 'debugger')[],
  },
  server: {
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
}))
