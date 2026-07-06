# PathFinder v2 — single-container image (API + static SPA) for Cloud Run.
# Build context = pathfinder/  (so both backend/ and frontend/ are copied).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    PORT=8080

WORKDIR /app

# Install deps first (better layer caching)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# App code + static frontend (main.py resolves ../../frontend => /app/frontend)
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

WORKDIR /app/backend
EXPOSE 8080

# Create tables + materialise the demand series, then serve.
# Cloud Run injects $PORT (default 8080).
CMD ["sh", "-c", "python -m seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
