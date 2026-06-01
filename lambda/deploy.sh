#!/usr/bin/env bash
# deploy.sh — build and deploy the Lambda container to AWS.
#
# Prerequisites
# -------------
# - AWS CLI configured (aws configure) with a user that has:
#     ecr:GetAuthorizationToken, ecr:BatchCheckLayerAvailability,
#     ecr:InitiateLayerUpload, ecr:UploadLayerPart, ecr:CompleteLayerUpload,
#     ecr:PutImage, lambda:UpdateFunctionCode
# - Docker running locally
# - Environment variables set (or pass as arguments — see usage below)
#
# Usage
# -----
#   ./deploy.sh                         # uses env vars below
#   AWS_REGION=us-east-1 ./deploy.sh   # override inline
#
# Required env vars (set in your shell or .env.deploy — never commit secrets)
# ---------------------------------------------------------------------------
#   AWS_REGION          e.g. us-east-1
#   AWS_ACCOUNT_ID      12-digit AWS account number
#   LAMBDA_FUNCTION     function name, e.g. callback-submit-application
#
# The ECR repo name is derived from LAMBDA_FUNCTION automatically.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — override via environment or edit here.
# ---------------------------------------------------------------------------

AWS_REGION="${AWS_REGION:-ca-central-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}"
LAMBDA_FUNCTION="${LAMBDA_FUNCTION:-callback-submit-application}"

ECR_REPO="${LAMBDA_FUNCTION}"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
IMAGE_TAG="latest"


# ---------------------------------------------------------------------------
# Step 1: Authenticate Docker with ECR.
# ---------------------------------------------------------------------------

echo "→ Authenticating Docker with ECR (${AWS_REGION})..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ---------------------------------------------------------------------------
# Step 2: Create ECR repo if it doesn't exist yet.
# ---------------------------------------------------------------------------

echo "→ Ensuring ECR repo '${ECR_REPO}' exists..."
aws ecr describe-repositories \
  --repository-names "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  > /dev/null 2>&1 \
|| aws ecr create-repository \
  --repository-name "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  --image-scanning-configuration scanOnPush=true \
  > /dev/null

# ---------------------------------------------------------------------------
# Step 3: Build the Docker image.
# The image is ~2GB (Playwright + Chromium). First build takes a few minutes;
# subsequent builds are fast thanks to Docker layer caching.
# ---------------------------------------------------------------------------

echo "→ Building Docker image..."
docker build \
  --platform linux/amd64 \
  -t "${ECR_REPO}:${IMAGE_TAG}" \
  .

# ---------------------------------------------------------------------------
# Step 4: Tag and push to ECR.
# ---------------------------------------------------------------------------

echo "→ Tagging image..."
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"

echo "→ Pushing to ECR (${ECR_URI})..."
docker push "${ECR_URI}:${IMAGE_TAG}"

# ---------------------------------------------------------------------------
# Step 5: Update Lambda to use the new image.
# ---------------------------------------------------------------------------

echo "→ Updating Lambda function '${LAMBDA_FUNCTION}'..."
aws lambda update-function-code \
  --function-name "${LAMBDA_FUNCTION}" \
  --image-uri "${ECR_URI}:${IMAGE_TAG}" \
  --region "${AWS_REGION}" \
  > /dev/null

# Wait for the update to finish before returning.
echo "→ Waiting for Lambda update to complete..."
aws lambda wait function-updated \
  --function-name "${LAMBDA_FUNCTION}" \
  --region "${AWS_REGION}"

echo ""
echo "✓ Deploy complete: ${LAMBDA_FUNCTION} → ${ECR_URI}:${IMAGE_TAG}"
echo ""
echo "If this is the first deploy, make sure the Lambda function is configured with:"
echo "  - Memory:  2048 MB (minimum; 3008 MB recommended)"
echo "  - Timeout: 900 seconds (15 minutes)"
echo "  - Env vars: ANTHROPIC_API_KEY, DJANGO_CALLBACK_URL, CALLBACK_SECRET"