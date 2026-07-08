# daveLinK — Dockerfile production
# Un solo contenedor con FastAPI (API + frontend) y Django (admin + migraciones)

FROM python:3.12-slim

WORKDIR /app

# ── Dependencias del sistema ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencias de Python ──────────────────────────────────────────────────
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Código de la aplicación ────────────────────────────────────────────────
COPY . .

# ── Puerto ──────────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Arranque ────────────────────────────────────────────────────────────────
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
