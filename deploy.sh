#!/usr/bin/env bash
# Deploy PathFinder to Google Cloud Run.
# Usage:  ./deploy.sh [PROJECT_ID]   (default: promptwar-501405)
#   REGION=asia-south1 ./deploy.sh
set -euo pipefail

export CLOUDSDK_CORE_DISABLE_PROMPTS=1   # never block on interactive prompts

PROJECT="${1:-promptwar-501405}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-pathfinder}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Strong session secret (override by exporting JWT_SECRET before running).
if [ -z "${JWT_SECRET:-}" ]; then
  JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
fi

echo "▶ Project : $PROJECT"
echo "▶ Region  : $REGION"
echo "▶ Service : $SERVICE"

gcloud config set project "$PROJECT" >/dev/null

echo "▶ Enabling required APIs (run, cloudbuild, artifactregistry)…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Build env vars. Gemini is wired only if GEMINI_API_KEY is exported at run time
# (never hard-coded here). Local providers are used otherwise.
ENV_VARS="APP_ENV=production,JWT_SECRET=${JWT_SECRET}"
if [ -n "${GEMINI_API_KEY:-}" ]; then
  ENV_VARS="${ENV_VARS},GEMINI_API_KEY=${GEMINI_API_KEY},GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash}"
  echo "▶ Gemini: ENABLED (model ${GEMINI_MODEL:-gemini-2.5-flash})"
else
  echo "▶ Gemini: not set — using local extractor"
fi
if [ -n "${RAPIDAPI_KEY:-}" ]; then
  ENV_VARS="${ENV_VARS},RAPIDAPI_KEY=${RAPIDAPI_KEY}"
  echo "▶ JSearch (RapidAPI): key set"
fi
if [ -n "${ADZUNA_APP_ID:-}" ] && [ -n "${ADZUNA_APP_KEY:-}" ]; then
  ENV_VARS="${ENV_VARS},ADZUNA_APP_ID=${ADZUNA_APP_ID},ADZUNA_APP_KEY=${ADZUNA_APP_KEY}"
  echo "▶ Adzuna: keys set"
fi
if [ -n "${DATABASE_URL:-}" ]; then
  ENV_VARS="${ENV_VARS},DATABASE_URL=${DATABASE_URL}"
  echo "▶ Database: Cloud SQL / Postgres (DATABASE_URL set)"
else
  echo "▶ Database: on-container SQLite (ephemeral — resets on redeploy)"
fi
CLOUDSQL_FLAG=""
if [ -n "${CLOUDSQL_CONN:-}" ]; then
  CLOUDSQL_FLAG="--add-cloudsql-instances=${CLOUDSQL_CONN}"
  echo "▶ Cloud SQL instance: ${CLOUDSQL_CONN}"
fi

echo "▶ Building & deploying from source (uses ./Dockerfile)…"
gcloud run deploy "$SERVICE" \
  --source "$HERE" \
  --region "$REGION" \
  --platform managed \
  --quiet \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi --cpu 1 \
  --min-instances 1 --max-instances 1 \
  ${CLOUDSQL_FLAG} \
  --set-env-vars "${ENV_VARS}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
echo ""
echo "✅ Deployed: $URL"
echo "   Health : $URL/api/health"
echo ""
echo "NOTE: This deploy uses on-container SQLite pinned to a single instance —"
echo "      accounts/history persist while the instance is warm but reset on redeploy."
echo "      For durable persistence, set DATABASE_URL to a Cloud SQL Postgres DSN"
echo "      and add --add-cloudsql-instances (see README 'Durable persistence')."
