#!/usr/bin/env bash
set -e

echo "=========================================="
echo "🚀 Starting Project JOY Cloud Platform"
echo "=========================================="

export PORT="${PORT:-3000}"
export BACKEND_INTERNAL_URL="${BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}"
export PYTHONUNBUFFERED=1

# Clean up background jobs on exit
cleanup() {
  echo "🛑 Shutting down backend processes..."
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Environment Configuration Setup
if [ ! -f .env ] && [ -f .env.example ]; then
  echo "📋 Copying root .env from .env.example..."
  cp .env.example .env
fi

if [ ! -f backend/.env ] && [ -f backend/.env.example ]; then
  echo "📋 Copying backend/.env from backend/.env.example..."
  cp backend/.env.example backend/.env
fi

# 2. Python Environment Setup
if [ ! -d ".venv" ]; then
  echo "🐍 Creating Python virtual environment (.venv)..."
  python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import fastapi" 2>/dev/null; then
  echo "📦 Installing backend Python dependencies..."
  pip install --upgrade pip
  pip install -r backend/requirements.txt
fi

# 3. Frontend Node.js Dependencies Setup
if [ ! -d "frontend/node_modules" ]; then
  echo "📦 Installing frontend Node dependencies..."
  (cd frontend && npm install)
fi

# 4. Database Migrations (if DATABASE_URL is reachable)
if [ -n "$DATABASE_URL" ]; then
  echo "🗄️ Checking and running PostgreSQL migrations..."
  (
    cd backend
    alembic upgrade head 2>&1 || echo "⚠️ Alembic auto-migration warning: lifespan will auto-initialize schema on startup."
  )
fi

# 5. Launch FastAPI Backend Service
echo "⚡ Launching FastAPI backend on 127.0.0.1:8000..."
(
  cd backend
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

# Wait for backend to report healthy
echo "⏳ Waiting for backend to initialize..."
for i in {1..15}; do
  if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "✅ FastAPI Backend is live and healthy!"
    break
  fi
  sleep 1
done

# 6. Launch Next.js Frontend Service
echo "🌐 Launching Next.js frontend on 0.0.0.0:$PORT..."
cd frontend

if [ "$NODE_ENV" = "production" ] && [ -d ".next" ]; then
  exec npm run start -- -p "$PORT" -H 0.0.0.0
else
  exec npm run dev -- -p "$PORT" -H 0.0.0.0
fi
