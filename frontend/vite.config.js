import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
    plugins: [
        vue(),
        vuetify({ autoImport: true })
    ],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
            '@core': fileURLToPath(new URL('./src/@core', import.meta.url))
        }
    },
    server: {
        port: 3009,
        host: '0.0.0.0',
        allowedHosts: true,
        proxy: {
            '/api': {
                target: process.env.VITE_API_URL || 'http://localhost:8009',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ''),
                configure: (proxy) => {
                    proxy.on('proxyRes', (proxyRes) => {
                        if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
                            proxyRes.headers['cache-control'] = 'no-cache'
                            proxyRes.headers['connection'] = 'keep-alive'
                            delete proxyRes.headers['content-length']
                        }
                    })
                }
            }
        }
    },
    build: {
        outDir: 'dist',
        sourcemap: false
    }
})
