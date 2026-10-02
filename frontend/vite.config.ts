/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Proxy /api to the backend so the browser stays same-origin. The backend's HOST/PORT come from
// the project-root .env (the same values `uv run itinerary-planner` uses). These are read only
// here, in the Node config — nothing without a VITE_ prefix is exposed to the browser bundle.
const PROJECT_ROOT = '..'

export default defineConfig(({ mode }) => {
  const { HOST = '127.0.0.1', PORT = '8001' } = loadEnv(mode, PROJECT_ROOT, '')
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': `http://${HOST}:${PORT}`,
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      restoreMocks: true,
      unstubGlobals: true,
    },
  }
})
