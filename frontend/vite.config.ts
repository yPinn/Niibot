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
  server: {
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
}))
