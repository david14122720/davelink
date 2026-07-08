#!/bin/bash
# LinkSnap / Acortador — Run both Django and FastAPI

set -e

echo "🚀 Starting LinkSnap..."

# Check if PostgreSQL is running
if ! docker compose ps | grep -q "postgres.*healthy"; then
    echo "⚠️  PostgreSQL not running. Starting Docker Compose..."
    docker compose up -d
    sleep 5
fi

# Activate virtual environment
cd backend
source .venv/bin/activate

# Start Django in background (for admin)
echo "📊 Starting Django admin on port 8001..."
python django_app/manage.py runserver 0.0.0.0:8001 &
DJANGO_PID=$!

# Start FastAPI
echo "⚡ Starting FastAPI on port 8000..."
uvicorn fastapi_app.main:app --host 0.0.0.0 --port 8000 --reload &
FASTAPI_PID=$!

echo ""
echo "✅ LinkSnap is running!"
echo "   - Frontend: http://localhost:8000"
echo "   - API:      http://localhost:8000/docs"
echo "   - Django:   http://localhost:8001/admin"
echo ""
echo "Press Ctrl+C to stop all services"

# Cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $DJANGO_PID 2>/dev/null || true
    kill $FASTAPI_PID 2>/dev/null || true
    echo "✅ All services stopped"
}

trap cleanup EXIT INT TERM

# Wait for processes
wait
