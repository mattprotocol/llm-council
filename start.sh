#!/bin/bash

# LLM Council - Start script

echo "Starting LLM Council..."
echo ""

# Start backend with uvicorn
echo "Starting backend on http://localhost:8001..."
cd "$(dirname "$0")"  # Ensure we're in the project root
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8001 --log-level warning &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 3

# Start frontend
echo "Starting frontend on http://localhost:5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✓ LLM Council is running!"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for Ctrl+C
trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
