import { existsSync, rmSync, mkdirSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(here, '..')
const repoRoot = path.resolve(frontendDir, '..')
const backendDir = path.join(repoRoot, 'backend')
const dataDir = path.join(here, '.e2e-data')

// Fresh empty DB every run.
if (existsSync(dataDir)) rmSync(dataDir, { recursive: true, force: true })
mkdirSync(dataDir, { recursive: true })

// Resolve a Python that has the backend deps (uvicorn, fastapi, ...).
const candidates = [
  path.join(backendDir, '.venv', 'Scripts', 'python.exe'), // Windows venv
  path.join(backendDir, '.venv', 'bin', 'python'),         // POSIX venv
]
const python = candidates.find(existsSync) || 'python' // CI: uv pip install --system

const proc = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--port', '8000'], {
  cwd: backendDir,
  env: {
    ...process.env,
    PYTHONPATH: '.',
    DATA_DIR: dataDir,
    SECRET_KEY: 'e2e-secret-key-do-not-use-in-prod',
    TZ: 'America/Chicago',
  },
  stdio: 'inherit',
})
proc.on('exit', (code) => process.exit(code ?? 0))
process.on('SIGTERM', () => proc.kill('SIGTERM'))
process.on('SIGINT', () => proc.kill('SIGINT'))
