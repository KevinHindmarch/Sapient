"""
Development server that runs both FastAPI backend and React frontend.
Run this with: python run_dev.py
"""

import subprocess
import sys
import time
import signal
import os

def run_servers():
    """Start both backend and frontend servers."""
    
    processes = []
    
    try:
        # Start FastAPI backend on port 8000
        print("Starting FastAPI backend on port 8000...")
        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", 
             "--host", "0.0.0.0", "--port", "8000", "--reload"],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        processes.append(backend)
        
        # Wait for backend to start
        time.sleep(3)
        
        # Start React frontend on port 5000
        print("Starting React frontend on port 5000...")
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
        )
        processes.append(frontend)
        
        print("\n" + "="*60)
        print("Sapient Development Servers Running:")
        print("  Backend API: http://localhost:8000")
        print("  Frontend:    http://localhost:5000")
        print("  API Docs:    http://localhost:8000/docs")
        print("="*60 + "\n")
        
        # Wait for either process to exit
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
