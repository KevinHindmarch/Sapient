"""
Development runner: FastAPI backend (port 8000) + Vite frontend (port 5000).

    uv run python run_dev.py

Generates a per-run API token and gives it to both processes, mirroring what
the desktop shell does. Data goes to SAPIENT_DATA_DIR (default: the normal
per-user data folder).
"""

import os
import secrets
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def run_servers():
    token = secrets.token_urlsafe(32)
    env = dict(os.environ, SAPIENT_API_TOKEN=token, VITE_SAPIENT_API_TOKEN=token)
    processes = []
    try:
        print("Starting FastAPI backend on 127.0.0.1:8000...")
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app",
             "--host", "127.0.0.1", "--port", "8000", "--reload"],
            cwd=ROOT, env=env))
        time.sleep(3)
        print("Starting React frontend on 127.0.0.1:5000...")
        npm = "npm.cmd" if os.name == "nt" else "npm"
        processes.append(subprocess.Popen([npm, "run", "dev"], cwd=os.path.join(ROOT, "frontend"), env=env))

        print("\n" + "=" * 60)
        print("Sapient development servers running:")
        print("  Frontend:  http://127.0.0.1:5000")
        print("  Backend:   http://127.0.0.1:8000 (requires the API token)")
        print("=" * 60 + "\n")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down servers...")
    finally:
        for p in processes:
            p.terminate()
            p.wait()
        print("Servers stopped.")


if __name__ == "__main__":
    run_servers()
