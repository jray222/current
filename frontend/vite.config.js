import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI backend so the browser sees a
// single origin: the httpOnly refresh cookie just works and no CORS is needed.
const backend = process.env.DOSE_API_URL || 'http://localhost:5733'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
  preview: {
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
})
