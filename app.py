#!/usr/bin/env python3
"""
Sapient - Australian Stock Portfolio Optimizer

FastAPI + React Application Entry Point

To run this application correctly, use:
    python server.py

The current workflow configuration uses Streamlit which conflicts with FastAPI.
To fix this, change the workflow command in the Workflows pane to: python server.py
"""

import os
import sys

if __name__ == "__main__":
    os.execvp(sys.executable, [sys.executable, "server.py"])
else:
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=5000, reload=True)
