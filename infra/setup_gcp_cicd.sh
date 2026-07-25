#!/usr/bin/env bash
# Setup Google Cloud resources for GitHub Actions CI/CD using Workload Identity Federation.
set -euo pipefail

PROJECT_ID="${1:-pathfinderai-503505}"
REGION="asia-south1"
REPO_NAME="pathfinderai-repo"
GITHUB_REPO="ojha-436/PathfinderAI"

echo "=========================================================="
echo "▶ Configuring CI/CD Resources in Google Cloud"
echo "▶ Project  : $PROJECT_ID"
echo "▶ Region   : $REGION"
echo "▶ Registry : $REPO_NAME"
echo "▶ GitHub   : $GITHUB_REPO"
echo "=========================================================="

# 1. Set active project
echo "▶ Setting active project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID"

# 2. Enable required APIs
echo "▶ Enabling required APIs (this may take a minute)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  sts.googleapis.com \
  iamcredentials.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com

# 3. Create Artifact Registry repository if it doesn't exist
echo "▶ Checking Artifact Registry repository..."
if ! gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" &>/dev/null; then
  echo "▶ Creating Artifact Registry repository $REPO_NAME..."
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="PathFinderAI Docker Repository" \
    --quiet
else
  echo "✔ Artifact Registry repository $REPO_NAME already exists."
fi

# 4. Create Service Accounts
echo "▶ Setting up Service Accounts..."

# Runtime Service Account for Cloud Run
RUNNER_SA="pathfinderai-runner"
RUNNER_SA_EMAIL="$RUNNER_SA@$PROJECT_ID.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$RUNNER_SA_EMAIL" &>/dev/null; then
  echo "▶ Creating runtime service account: $RUNNER_SA..."
  gcloud iam service-accounts create "$RUNNER_SA" \
    --description="Runtime service account for PathFinderAI Cloud Run" \
    --display-name="PathFinderAI Runner"
else
  echo "✔ Runtime service account $RUNNER_SA already exists."
fi

# GitHub Actions Deployer Service Account
DEPLOYER_SA="github-actions-deployer"
DEPLOYER_SA_EMAIL="$DEPLOYER_SA@$PROJECT_ID.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$DEPLOYER_SA_EMAIL" &>/dev/null; then
  echo "▶ Creating deployer service account: $DEPLOYER_SA..."
  gcloud iam service-accounts create "$DEPLOYER_SA" \
    --description="CI/CD deployer service account for GitHub Actions" \
    --display-name="GitHub Actions Deployer"
else
  echo "✔ Deployer service account $DEPLOYER_SA already exists."
fi

# 5. Set up Workload Identity Federation
echo "▶ Setting up Workload Identity Federation..."
POOL_NAME="github-actions-pool"
PROVIDER_NAME="github-actions-provider"

# Create Workload Identity Pool
if ! gcloud iam workload-identity-pools describe "$POOL_NAME" --location="global" &>/dev/null; then
  echo "▶ Creating Workload Identity Pool $POOL_NAME..."
  gcloud iam workload-identity-pools create "$POOL_NAME" \
    --location="global" \
    --display-name="GitHub Actions Pool"
else
  echo "✔ Workload Identity Pool $POOL_NAME already exists."
fi

# Create Workload Identity Provider
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" \
    --workload-identity-pool="$POOL_NAME" \
    --location="global" &>/dev/null; then
  echo "▶ Creating Workload Identity Provider $PROVIDER_NAME..."
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
    --location="global" \
    --workload-identity-pool="$POOL_NAME" \
    --display-name="GitHub Actions Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '$GITHUB_REPO'" \
    --issuer-uri="https://token.actions.githubusercontent.com"
else
  echo "✔ Workload Identity Provider $PROVIDER_NAME already exists."
fi

# Get Project Number
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# Bind GitHub Actions repository to the deployer service account
echo "▶ Binding GitHub Actions OIDC to deployer service account..."
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_NAME/attribute.repository/$GITHUB_REPO" \
  --quiet

# 6. Configure IAM Permissions
echo "▶ Granting IAM permissions (least-privilege)..."

# Deployer SA permissions
# Pushing to Artifact Registry
gcloud artifacts repositories add-iam-policy-binding "$REPO_NAME" \
  --location="$REGION" \
  --member="serviceAccount:$DEPLOYER_SA_EMAIL" \
  --role="roles/artifactregistry.writer" \
  --quiet

# Deploying to Cloud Run
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$DEPLOYER_SA_EMAIL" \
  --role="roles/run.developer" \
  --quiet

# Service Account User on runner SA (deployer SA must act as runner SA when deploying)
gcloud iam service-accounts add-iam-policy-binding "$RUNNER_SA_EMAIL" \
  --member="serviceAccount:$DEPLOYER_SA_EMAIL" \
  --role="roles/iam.serviceAccountUser" \
  --quiet

# Runner SA permissions
# Pulling from Artifact Registry (for Cloud Run to fetch container)
gcloud artifacts repositories add-iam-policy-binding "$REPO_NAME" \
  --location="$REGION" \
  --member="serviceAccount:$RUNNER_SA_EMAIL" \
  --role="roles/artifactregistry.reader" \
  --quiet

# Secret Manager Access
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNNER_SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet

# 7. Provision Secrets in Secret Manager
echo "▶ Initializing secrets in Secret Manager (if they do not exist)..."
SECRETS=(
  "JWT_SECRET"
  "GEMINI_API_KEY"
  "RAPIDAPI_KEY"
  "ADZUNA_APP_ID"
  "ADZUNA_APP_KEY"
  "SMTP_USER"
  "SMTP_PASSWORD"
  "DIGEST_TOKEN"
  "DATABASE_URL"
)

for SECRET in "${SECRETS[@]}"; do
  if ! gcloud secrets describe "$SECRET" &>/dev/null; then
    echo "▶ Creating secret: $SECRET..."
    gcloud secrets create "$SECRET" \
      --replication-policy="automatic" \
      --quiet
    
    # Add a safe placeholder value
    if [ "$SECRET" = "JWT_SECRET" ]; then
      VAL=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    elif [ "$SECRET" = "DIGEST_TOKEN" ]; then
      VAL=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    elif [ "$SECRET" = "DATABASE_URL" ]; then
      VAL="sqlite:///./pathfinderai.db"
    else
      VAL="placeholder"
    fi
    
    echo -n "$VAL" | gcloud secrets versions add "$SECRET" --data-file=-
    echo "✔ Initialized secret $SECRET with default value."
  else
    echo "✔ Secret $SECRET already exists."
  fi
done

# Output results
WIF_PROVIDER="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_NAME/providers/$PROVIDER_NAME"
echo "=========================================================="
echo "✅ CI/CD GCP Resources Configured Successfully!"
echo "----------------------------------------------------------"
echo "Add these secrets to your GitHub repository (ojha-436/PathfinderAI):"
echo "  GCP_WORKLOAD_IDENTITY_PROVIDER : $WIF_PROVIDER"
echo "  GCP_SERVICE_ACCOUNT            : $DEPLOYER_SA_EMAIL"
echo "=========================================================="
