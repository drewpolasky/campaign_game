import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The client calls the Flask API directly (CORS is open on the server), so no
// proxy is needed. Override the API base with VITE_API_BASE if the server runs
// somewhere other than http://localhost:8080.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,   // bind 0.0.0.0 so WSL port-forwarding exposes it to Windows
    port: 5173,
  },
})
