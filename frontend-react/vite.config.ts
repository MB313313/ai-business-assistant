import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import type { Plugin } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
/** Repo-root `samples/` — served at `/samples/*` in dev and copied to `dist/samples` on build */
const workspaceSamplesDir = path.resolve(__dirname, '../samples')

function workspaceSamplesPlugin(): Plugin {
  return {
    name: 'workspace-samples',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split('?')[0] ?? ''
        if (!url.startsWith('/samples/')) {
          next()
          return
        }
        const name = path.basename(url)
        if (!name || name === '/' || name.includes('..')) {
          res.statusCode = 400
          res.end()
          return
        }
        const filePath = path.join(workspaceSamplesDir, name)
        if (!filePath.startsWith(workspaceSamplesDir)) {
          res.statusCode = 403
          res.end()
          return
        }
        fs.readFile(filePath, (err, data) => {
          if (err) {
            res.statusCode = 404
            res.end()
            return
          }
          const lower = name.toLowerCase()
          const ct = lower.endsWith('.pdf')
            ? 'application/pdf'
            : lower.endsWith('.txt')
              ? 'text/plain; charset=utf-8'
              : 'application/octet-stream'
          res.setHeader('Content-Type', ct)
          res.end(data)
        })
      })
    },
    closeBundle() {
      if (!fs.existsSync(workspaceSamplesDir)) return
      const outDir = path.resolve(__dirname, 'dist/samples')
      fs.mkdirSync(outDir, { recursive: true })
      for (const entry of fs.readdirSync(workspaceSamplesDir)) {
        const src = path.join(workspaceSamplesDir, entry)
        if (fs.statSync(src).isFile()) {
          fs.copyFileSync(src, path.join(outDir, entry))
        }
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  plugins: [
    workspaceSamplesPlugin(),
    react(),
    babel({ presets: [reactCompilerPreset()] }),
  ],
})
