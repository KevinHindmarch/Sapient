"""
Sapient Production Server
Runs the FastAPI backend with React frontend.
"""

import uvicorn
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
