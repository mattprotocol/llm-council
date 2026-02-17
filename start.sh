#!/bin/bash
# LLM Council - Production Startup
set -e

cd /Users/macmini/llm-council

echo "Starting LLM Council..."

# Start backend
echo "Starting backend on port 8001..."
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on port 5173..."
cd frontend
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
cd ..

echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo ""
echo "LLM Council running:"
echo "  Frontend: http://0.0.0.0:5173"
echo "  Backend:  http://0.0.0.0:8001"
echo ""

# Wait for both
wait $BACKEND_PID $FRONTEND_PID
