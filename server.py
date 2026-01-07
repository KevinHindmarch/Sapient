"""
Sapient Production Server
Runs the FastAPI backend with React frontend on port 5000.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True
    )
