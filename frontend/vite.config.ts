import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || '/',
  envDir: '..',
  server: {
    port: parseInt(process.env.FRONTEND_PORT || '5201'),
    host: '0.0.0.0',
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
    },
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.BACKEND_PORT || '8201'}`,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
