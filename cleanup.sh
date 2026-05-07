#!/bin/bash

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
BUCKET_NAME="${PROJECT_ID}-trail-photos"
DB_NAME="trail-reports"
SERVICE_NAME="trail-tracker"
FUNCTION_NAME="generate-thumbnail"

echo "Tearing down Trail Tracker"
echo "Project: ${PROJECT_ID}"

# Delete the Cloud Run service
echo "[1/4] Deleting Cloud Run service: ${SERVICE_NAME}..."
gcloud run services delete ${SERVICE_NAME} \
  --region=${REGION} \
  --quiet 2>/dev/null || echo "  (service not found or already deleted)"

# Delete the Cloud Run Function
echo "[2/4] Deleting Cloud Run Function: ${FUNCTION_NAME}..."
gcloud functions delete ${FUNCTION_NAME} \
  --region=${REGION} \
  --gen2 \
  --quiet 2>/dev/null || echo "  (function not found or already deleted)"

# Delete the Cloud Storage bucket and all objects inside it
echo "[3/4] Deleting Cloud Storage bucket: gs://${BUCKET_NAME}..."
gcloud storage rm -r gs://${BUCKET_NAME} \
  2>/dev/null || echo "  (bucket not found or already deleted)"

# Delete the Firestore database
echo "[4/4] Deleting Firestore database: ${DB_NAME}..."
gcloud firestore databases delete \
  --database=${DB_NAME} \
  --quiet 2>/dev/null || echo "  (database not found or already deleted)"

echo ""
echo "Teardown complete."
echo "All Trail Tracker resources have been removed from project ${PROJECT_ID}."
