// Copies the built React UI (frontend/dist) into desktop/renderer for packaging.
import { cpSync, existsSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const desktop = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(desktop, '..', 'frontend', 'dist')
const target = join(desktop, 'renderer')
if (!existsSync(join(source, 'index.html'))) {
  console.error('frontend/dist is missing: run `npm run build` in frontend/ first')
  process.exit(1)
}
rmSync(target, { recursive: true, force: true })
cpSync(source, target, { recursive: true })
console.log(`Copied ${source} -> ${target}`)
