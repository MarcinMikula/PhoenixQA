import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Fixed port — must match CHAOS_APP_URL in PhoenixQA .env
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
