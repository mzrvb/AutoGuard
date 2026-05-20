#!/usr/bin/env bash
# AutoGuard GCP setup — run once from the project root.
# Prerequisites: gcloud CLI authenticated, ANTHROPIC_API_KEY set in your shell.
#
# Usage:
#   export GCP_PROJECT_ID=your-project-id
#   export ANTHROPIC_API_KEY=sk-ant-...
#   bash deploy/setup_gcp.sh

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID before running}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY before running}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="autoguard"
TOPIC="autoguard-gmail"
SA_NAME="autoguard-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "==> Enabling APIs"
gcloud services enable \
  pubsub.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  --project="$PROJECT_ID"

# ── Service account ──────────────────────────────────────────────────
echo "==> Creating service account"
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="AutoGuard Cloud Run SA" \
  --project="$PROJECT_ID" 2>/dev/null || echo "    (already exists)"

# ── Pub/Sub topic ────────────────────────────────────────────────────
echo "==> Creating Pub/Sub topic: $TOPIC"
gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID" 2>/dev/null || echo "    (already exists)"

# Allow Gmail's push service to publish to the topic
gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project="$PROJECT_ID"

# ── Secrets ──────────────────────────────────────────────────────────
echo "==> Uploading secrets to Secret Manager"

_upsert_secret() {
  local name=$1 file=$2
  if gcloud secrets describe "$name" --project="$PROJECT_ID" &>/dev/null; then
    gcloud secrets versions add "$name" --data-file="$file" --project="$PROJECT_ID"
  else
    gcloud secrets create "$name" --data-file="$file" --project="$PROJECT_ID"
  fi
}

_upsert_secret "autoguard-token"       "config/token.json"
_upsert_secret "autoguard-preferences" "staff/preferences.json"
_upsert_secret "autoguard-whitelist"   "staff/emails.json"

# Anthropic API key (from env, not a file)
if gcloud secrets describe "autoguard-anthropic-key" --project="$PROJECT_ID" &>/dev/null; then
  echo -n "$ANTHROPIC_API_KEY" | gcloud secrets versions add "autoguard-anthropic-key" \
    --data-file=- --project="$PROJECT_ID"
else
  echo -n "$ANTHROPIC_API_KEY" | gcloud secrets create "autoguard-anthropic-key" \
    --data-file=- --project="$PROJECT_ID"
fi

# Grant service account access to all four secrets
for secret in autoguard-token autoguard-preferences autoguard-whitelist autoguard-anthropic-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID"
done

# ── Build & deploy ───────────────────────────────────────────────────
echo "==> Building container image"
gcloud builds submit --tag "$IMAGE" --project="$PROJECT_ID"

echo "==> Deploying to Cloud Run"
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --no-allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},PUBSUB_TOPIC=${TOPIC}" \
  --update-secrets="GOOGLE_TOKEN_JSON=autoguard-token:latest" \
  --update-secrets="ANTHROPIC_API_KEY=autoguard-anthropic-key:latest" \
  --update-secrets="/app/staff/preferences.json=autoguard-preferences:latest" \
  --update-secrets="/app/staff/emails.json=autoguard-whitelist:latest" \
  --project="$PROJECT_ID"

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --format="value(status.url)" \
  --project="$PROJECT_ID")
echo "    Service URL: $SERVICE_URL"

# ── Pub/Sub push subscription ────────────────────────────────────────
echo "==> Creating Pub/Sub push subscription"
gcloud pubsub subscriptions create autoguard-push \
  --topic="$TOPIC" \
  --push-endpoint="${SERVICE_URL}/" \
  --push-auth-service-account="$SA_EMAIL" \
  --ack-deadline=300 \
  --project="$PROJECT_ID" 2>/dev/null || echo "    (already exists)"

# Allow the SA to invoke Cloud Run (needed for authenticated push)
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region="$REGION" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker" \
  --project="$PROJECT_ID"

# ── Weekly watch renewal via Cloud Scheduler ─────────────────────────
echo "==> Creating Cloud Scheduler job (weekly watch renewal)"
gcloud scheduler jobs create http autoguard-watch-renew \
  --location="$REGION" \
  --schedule="0 6 * * 1" \
  --uri="${SERVICE_URL}/renew" \
  --http-method=POST \
  --oidc-service-account-email="$SA_EMAIL" \
  --project="$PROJECT_ID" 2>/dev/null || echo "    (already exists)"

# ── Initial Gmail watch ───────────────────────────────────────────────
echo "==> Registering Gmail push watch"
GCP_PROJECT_ID="$PROJECT_ID" PUBSUB_TOPIC="$TOPIC" python deploy/setup_watch.py

echo ""
echo "Done! AutoGuard is live."
echo "  Cloud Run: $SERVICE_URL"
echo "  Pub/Sub topic: projects/$PROJECT_ID/topics/$TOPIC"
echo "  Gmail notifications → Pub/Sub → Cloud Run"
echo ""
echo "To redeploy after code changes:"
echo "  gcloud builds submit --tag $IMAGE --project=$PROJECT_ID"
echo "  gcloud run deploy $SERVICE_NAME --image $IMAGE --region $REGION --project $PROJECT_ID"
