import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backendUrl = process.env.VITE_BACKEND_URL || 'http://localhost:3001';
const envPort = Number(process.env.VITE_PORT);
const devPort = Number.isInteger(envPort) && envPort > 0 ? envPort : 3000;

export default defineConfig({
  plugins: [react()],
  server: {
    port: devPort,
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true
      }
    }
  }
});
