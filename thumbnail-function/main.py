import os
import tempfile

import functions_framework
from google.cloud import firestore, storage
from PIL import Image

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT"))
BUCKET_NAME = f"{PROJECT_ID}-trail-photos"
DB_NAME = "trail-reports"
THUMB_WIDTH = 400

storage_client = storage.Client()
db = firestore.Client(database=DB_NAME)


@functions_framework.cloud_event
def generate_thumbnail(cloud_event):
    """Triggered by a finalize event on the trail-photos bucket.

    Downloads the original image, creates a 400px-wide thumbnail,
    uploads it back to the bucket under thumbnails/, and updates the
    matching Firestore document with the thumbnail URL.
    """
    data = cloud_event.data
    file_name = data["name"]        # e.g. photos/abc123.jpg
    bucket_name = data["bucket"]

    # only process files that land in the photos/ prefix
    if not file_name.startswith("photos/"):
        print(f"Skipping {file_name} -- not in photos/ prefix")
        return

    # avoid infinite loops, do not process thumbnails
    if file_name.startswith("thumbnails/"):
        print(f"Skipping {file_name} already a thumbnail")
        return

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)

    # download to a temp file
    _, tmp_path = tempfile.mkstemp()
    blob.download_to_filename(tmp_path)
    print(f"Downloaded {file_name} to {tmp_path}")

    # generate the thumbnail
    img = Image.open(tmp_path)
    ratio = THUMB_WIDTH / img.width
    new_height = int(img.height * ratio)
    img = img.resize((THUMB_WIDTH, new_height), Image.LANCZOS)

    thumb_tmp = tmp_path + "_thumb.jpg"
    img.save(thumb_tmp, "JPEG", quality=80)
    print(f"Created thumbnail at {thumb_tmp} ({THUMB_WIDTH}x{new_height})")

    # upload thumbnail
    base = file_name.split("/")[-1]           # abc123.jpg
    thumb_blob_name = f"thumbnails/{base}"
    thumb_blob = bucket.blob(thumb_blob_name)
    thumb_blob.upload_from_filename(thumb_tmp, content_type="image/jpeg")
    thumb_blob.make_public()
    thumb_url = thumb_blob.public_url
    print(f"Uploaded thumbnail to {thumb_blob_name}")

    # update the firestore document that references this photo
    # stored photo_gcs_path = "photos/abc123.jpg" in the document
    docs = (
        db.collection("reports")
        .where("photo_gcs_path", "==", file_name)
        .limit(1)
        .stream()
    )
    for doc in docs:
        doc.reference.update({"thumbnail_url": thumb_url})
        print(f"Updated Firestore doc {doc.id} with thumbnail URL")

    # clean up temp files
    os.remove(tmp_path)
    os.remove(thumb_tmp)

    return "OK"
