"""
Sapient Production Server
Runs the FastAPI backend with React frontend.
"""

import uvicorn
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=port,
        reload=False
    )
