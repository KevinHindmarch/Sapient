// Freezes the Python engine with PyInstaller into packaging/dist/sapient-api.
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const result = spawnSync('uv', ['run', '--with', 'pyinstaller', 'pyinstaller', 'packaging/sapient-api.spec',
  '--noconfirm', '--distpath', 'packaging/dist', '--workpath', 'packaging/build'],
  { cwd: repo, stdio: 'inherit', shell: process.platform === 'win32' })
process.exit(result.status ?? 1)
