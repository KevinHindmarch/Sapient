#!/bin/bash

# Start FastAPI backend in the background (from project root)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start React frontend (install dependencies first)
cd frontend && npm install 2>/dev/null && npm run dev &
FRONTEND_PID=$!

echo "Backend running on port 8000"
echo "Frontend running on port 5000"

# Wait for any process to exit
wait -n

# If one exits, kill the other
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
