#!/bin/bash
# daveLinK — Entrypoint para Docker
# Ejecuta migraciones Django y levanta el servidor

set -e

echo "=== daveLinK — Migraciones Django ==="
cd backend/django_app
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear
cd /app

echo "=== daveLinK — Iniciando servidor ==="
exec gunicorn fastapi_app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile -
