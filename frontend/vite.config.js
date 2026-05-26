import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/message': 'http://localhost:8000',
      '/tasks': 'http://localhost:8000',
    },
  },
})
