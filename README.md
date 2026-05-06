# Montana Trail Conditions Tracker

A community-driven web application that lets hikers report and browse real-time trail conditions across Montana. Built on Google Cloud Platform for the Cloud Computing final project (Spring 2026).

## What It Does

Users visit the site, pick a trail from a list of popular Montana hikes, choose a condition status (Clear, Muddy, Snowy, Flooded, etc.), optionally attach a photo and a note, and submit. The report is saved to Firestore and shows up immediately on the main feed. If a photo was attached, a background function automatically generates a compressed thumbnail so the feed loads quickly.

## Architecture Overview

The application uses four distinct GCP services, each with a single responsibility:

| Layer | Service | Role |
|---|---|---|
| Compute | Cloud Run | Serves the Flask web app and REST API |
| Data/State | Firestore (Native mode) | Stores all trail report documents |
| Storage | Cloud Storage | Holds uploaded trail photos and generated thumbnails |
| Event/Background | Cloud Run Functions (2nd gen) | Triggered on photo upload to generate a 400px thumbnail |

### Data Flow

1. A user visits the Cloud Run web app and fills out the trail report form.
2. The Flask app uploads the photo (if any) to a Cloud Storage bucket under the `photos/` prefix, then writes the report metadata to Firestore.
3. The photo upload fires a `google.cloud.storage.object.v1.finalized` event, which triggers the Cloud Run Function.
4. The function downloads the original image, resizes it to 400px wide using Pillow, saves the thumbnail back to Cloud Storage under `thumbnails/`, and updates the Firestore document with the thumbnail URL.
5. Other users loading the trail feed read from Firestore. Photos and thumbnails are served directly from Cloud Storage's public URLs.

### Architecture Diagram

```
                    +-------------------+
  User  ------>     |   Cloud Run       |
  (browser)         |   (Flask app)     |
                    +--------+----------+
                             |
                 +-----------+-----------+
                 |                       |
          +------v------+       +-------v--------+
          |  Firestore  |       | Cloud Storage  |
          | (trail-     |       | (trail-photos  |
          |  reports)   |       |  bucket)       |
          +-------------+       +-------+--------+
                                        |
                                        | finalize event
                                        v
                                +-------+--------+
                                | Cloud Run      |
                                | Function       |
                                | (thumbnail     |
                                |  generator)    |
                                +----------------+
                                   |         |
                          writes   |         | updates
                          thumb    v         v
                        Cloud Storage    Firestore
```

## Project Structure

```
montana-trail-tracker/
  app/
    main.py              # Flask web application
    requirements.txt     # Python dependencies for the web app
    Dockerfile           # Container image definition for Cloud Run
  thumbnail-function/
    main.py              # Cloud Run Function entry point
    requirements.txt     # Python dependencies for the function
  cleanup.sh             # Teardown script (gcloud commands to delete everything)
  README.md              # This file
```

## Deployment Steps

All commands below assume you are working in Google Cloud Shell with your project already selected (`gcloud config set project YOUR_PROJECT_ID`). The deployment region is `us-central1`.

### 1. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  eventarc.googleapis.com \
  artifactregistry.googleapis.com
```

### 2. Create the Firestore database

```bash
gcloud firestore databases create \
  --database=trail-reports \
  --location=nam5 \
  --type=firestore-native
```

### 3. Create the Cloud Storage bucket

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud storage buckets create gs://${PROJECT_ID}-trail-photos \
  --location=us-central1 \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-trail-photos \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

### 4. Deploy the Cloud Run service

```bash
cd app/

gcloud run deploy trail-tracker \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
```

### 5. Deploy the Cloud Run Function

```bash
cd ../thumbnail-function/

gcloud functions deploy generate-thumbnail \
  --gen2 \
  --runtime python311 \
  --region us-central1 \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=${PROJECT_ID}-trail-photos" \
  --source . \
  --entry-point generate_thumbnail \
  --set-env-vars GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
```

### 6. Verify

Open the Cloud Run service URL printed by step 4 in a browser. Submit a test report with a photo and confirm the thumbnail appears after a few seconds.

## Cost Estimate

At the expected usage level for a class project (roughly 500 requests/day, 50 photos/week, under 1 GB stored), every service stays within GCP's free tier. Estimated monthly cost: **$0.00**. See the Part 1 design document for the full breakdown.

## Teardown

Run the cleanup script to delete all resources and avoid any charges:

```bash
chmod +x cleanup.sh
./cleanup.sh
```

## Screenshots

*(Screenshots of the running application and GCP Console are included below.)*

### Application Screenshots

- **Trail feed with reports and thumbnails**

  `[INSERT SCREENSHOT: main page showing submitted reports with status badges and thumbnail images]`

- **Report submission form**

  `[INSERT SCREENSHOT: the form at the top of the page with trail dropdown, status dropdown, note field, and photo upload]`

### GCP Console Screenshots

- **Cloud Run service active and healthy**

  `[INSERT SCREENSHOT: Cloud Run console showing the trail-tracker service with a green checkmark, the service URL, and recent request metrics]`

- **Firestore database populated with reports**

  `[INSERT SCREENSHOT: Firestore console showing the trail-reports database, the reports collection, and several documents with fields like trail_name, condition, timestamp, etc.]`

- **Cloud Storage bucket with photos and thumbnails**

  `[INSERT SCREENSHOT: Cloud Storage browser showing the trail-photos bucket with both photos/ and thumbnails/ prefixes containing uploaded files]`

- **Cloud Run Function deployed and invoked**

  `[INSERT SCREENSHOT: Cloud Functions console showing generate-thumbnail with a 2nd gen badge, invocation count, and recent execution logs]`

## Post-Mortem

*(Describe the technical difficulties you ran into and how you solved them. Swap in your real experiences here.)*

**Problem 1: Eventarc permissions for the Cloud Run Function.**
When I first tried to deploy the function with the Cloud Storage trigger, the deployment failed with a permissions error related to Eventarc. The issue was that the default Compute Engine service account did not have the `eventarc.eventReceiver` role. I fixed it by running:

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/eventarc.eventReceiver"
```

After granting that role and redeploying the function, the trigger connected successfully.

**Problem 2: Cloud Storage public access.**
Initially the uploaded photos were not rendering in the browser because the bucket had uniform bucket-level access enabled but no public read policy. I had to add an IAM binding granting `roles/storage.objectViewer` to `allUsers` on the bucket, and then also call `blob.make_public()` in the application code to ensure each individual object was accessible.

**Infrastructure setup method:** I used the `gcloud` CLI for all deployments. I ran commands in Google Cloud Shell, which already had the SDK and Docker build tools available. No Terraform was used for this project (though I am familiar with it from Labs 10 and 11).
