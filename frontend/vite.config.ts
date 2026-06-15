import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react-swc'
import path from 'path'
import { defineConfig } from 'vitest/config'

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
    // Vite 8 runs on Rolldown/Oxc (esbuild is no longer the transformer), so the
    // former esbuild.drop console stripping moves to Terser — bundler-agnostic and
    // the documented path for granular drops.
    minify: 'terser' as const,
    terserOptions: {
      compress: { drop_console: true, drop_debugger: true },
    },
  },
  test: {
    environment: 'jsdom',
    coverage: {
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
      },
    },
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
      '/status': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ping': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
}))
