import os
import uuid
from datetime import datetime

from flask import Flask, request, redirect, render_template_string, jsonify
from google.cloud import firestore, storage

app = Flask(__name__)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT"))
BUCKET_NAME = f"{PROJECT_ID}-trail-photos"
DB_NAME = "trail-reports"

db = firestore.Client(database=DB_NAME)
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# ── Montana trails (hardcoded for simplicity) ────────────────────────────
TRAILS = [
    {"name": "M Trail (Mount Sentinel)", "lat": 46.8427, "lng": -113.9750},
    {"name": "Palisade Falls", "lat": 45.4631, "lng": -111.1042},
    {"name": "Grotto Falls", "lat": 45.4803, "lng": -111.1076},
    {"name": "Pine Creek Falls", "lat": 45.5120, "lng": -110.5098},
    {"name": "Drinking Horse Trail", "lat": 45.7125, "lng": -111.0172},
    {"name": "Sacagawea Peak", "lat": 45.8703, "lng": -110.9753},
    {"name": "Bear Canyon Trail", "lat": 45.6310, "lng": -111.0625},
    {"name": "Rattlesnake Wilderness", "lat": 46.9280, "lng": -113.8900},
    {"name": "Blue Mountain Trail", "lat": 46.8100, "lng": -114.1200},
    {"name": "Lava Lake Trail", "lat": 45.0520, "lng": -111.4375},
]

STATUSES = ["Clear", "Muddy", "Snowy", "Flooded", "Overgrown", "Icy"]

# ── HTML template (kept inline per professor's note about polish being secondary) ──
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Montana Trail Conditions</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Georgia, serif; background: #f5f1eb; color: #2c2c2c; padding: 20px; }
    h1 { text-align: center; margin-bottom: 4px; font-size: 1.6em; }
    .subtitle { text-align: center; color: #666; margin-bottom: 20px; font-size: 0.9em; }
    .container { max-width: 700px; margin: 0 auto; }
    .card { background: #fff; border: 1px solid #ccc; border-radius: 6px; padding: 16px; margin-bottom: 14px; }
    .card h3 { margin-bottom: 8px; }
    .status-badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.8em;
      font-weight: bold; color: #fff; }
    .status-Clear { background: #4a9e4a; }
    .status-Muddy { background: #8b6914; }
    .status-Snowy { background: #5b8fbf; }
    .status-Flooded { background: #b03a3a; }
    .status-Overgrown { background: #6b8e23; }
    .status-Icy { background: #708090; }
    .note { color: #555; font-style: italic; margin-top: 6px; }
    .meta { color: #888; font-size: 0.8em; margin-top: 4px; }
    .photo { max-width: 100%; border-radius: 4px; margin-top: 8px; }
    .thumb { max-width: 200px; border-radius: 4px; margin-top: 8px; }
    form { background: #fff; border: 1px solid #ccc; border-radius: 6px; padding: 18px; margin-bottom: 20px; }
    label { display: block; font-weight: bold; margin-top: 10px; margin-bottom: 4px; }
    select, input[type="text"], textarea, input[type="file"] {
      width: 100%; padding: 8px; border: 1px solid #aaa; border-radius: 4px; font-size: 1em; }
    textarea { height: 60px; resize: vertical; }
    button { margin-top: 14px; padding: 10px 24px; background: #3a6b3a; color: #fff; border: none;
      border-radius: 4px; font-size: 1em; cursor: pointer; }
    button:hover { background: #2e562e; }
    a { color: #3a6b3a; }
    .section-title { margin: 20px 0 10px; font-size: 1.2em; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
  </style>
</head>
<body>
<div class="container">
  <h1>Montana Trail Conditions</h1>
  <p class="subtitle">Community-reported trail conditions across Big Sky Country</p>

  <h2 class="section-title">Submit a Report</h2>
  <form action="/report" method="POST" enctype="multipart/form-data">
    <label for="trail">Trail</label>
    <select name="trail" id="trail" required>
      <option value="">-- pick a trail --</option>
      {% for t in trails %}
        <option value="{{ t.name }}">{{ t.name }}</option>
      {% endfor %}
    </select>

    <label for="status">Condition</label>
    <select name="status" id="status" required>
      {% for s in statuses %}
        <option value="{{ s }}">{{ s }}</option>
      {% endfor %}
    </select>

    <label for="note">Note (optional)</label>
    <textarea name="note" id="note" placeholder="e.g. Ice on the switchbacks above the second bridge"></textarea>

    <label for="photo">Photo (optional)</label>
    <input type="file" name="photo" id="photo" accept="image/*" />

    <button type="submit">Submit Report</button>
  </form>

  <h2 class="section-title">Recent Reports</h2>
  {% if reports %}
    {% for r in reports %}
    <div class="card">
      <h3>{{ r.trail_name }}</h3>
      <span class="status-badge status-{{ r.condition }}">{{ r.condition }}</span>
      {% if r.note %}
        <p class="note">"{{ r.note }}"</p>
      {% endif %}
      {% if r.thumbnail_url %}
        <img class="thumb" src="{{ r.thumbnail_url }}" alt="trail photo thumbnail" />
      {% elif r.photo_url %}
        <img class="photo" src="{{ r.photo_url }}" alt="trail photo"
             style="max-width:300px;" />
      {% endif %}
      <p class="meta">{{ r.timestamp_str }} &middot; ({{ r.lat }}, {{ r.lng }})</p>
    </div>
    {% endfor %}
  {% else %}
    <p style="color:#888;">No reports yet. Be the first to submit one.</p>
  {% endif %}
</div>
</body>
</html>
"""


@app.route("/")
def index():
    """Render the main page with the submission form and recent reports."""
    docs = (
        db.collection("reports")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(30)
        .stream()
    )
    reports = []
    for doc in docs:
        d = doc.to_dict()
        ts = d.get("timestamp")
        ts_str = ts.strftime("%B %d, %Y at %I:%M %p") if ts else "unknown"
        reports.append({
            "trail_name": d.get("trail_name", ""),
            "condition": d.get("condition", ""),
            "note": d.get("note", ""),
            "photo_url": d.get("photo_url", ""),
            "thumbnail_url": d.get("thumbnail_url", ""),
            "lat": d.get("lat", 0),
            "lng": d.get("lng", 0),
            "timestamp_str": ts_str,
        })
    return render_template_string(PAGE_TEMPLATE, trails=TRAILS, statuses=STATUSES, reports=reports)


@app.route("/report", methods=["POST"])
def submit_report():
    """Handle a new trail condition report submission."""
    trail_name = request.form.get("trail")
    condition = request.form.get("status")
    note = request.form.get("note", "").strip()
    photo_file = request.files.get("photo")

    # look up coordinates for the selected trail
    trail_info = next((t for t in TRAILS if t["name"] == trail_name), None)
    lat = trail_info["lat"] if trail_info else 0.0
    lng = trail_info["lng"] if trail_info else 0.0

    photo_url = ""
    photo_gcs_path = ""

    if photo_file and photo_file.filename:
        ext = photo_file.filename.rsplit(".", 1)[-1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        blob = bucket.blob(f"photos/{filename}")
        blob.upload_from_file(photo_file, content_type=photo_file.content_type)
        blob.make_public()
        photo_url = blob.public_url
        photo_gcs_path = f"photos/{filename}"

    doc_ref = db.collection("reports").document()
    doc_ref.set({
        "trail_name": trail_name,
        "condition": condition,
        "note": note,
        "photo_url": photo_url,
        "photo_gcs_path": photo_gcs_path,
        "thumbnail_url": "",
        "lat": lat,
        "lng": lng,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "doc_id": doc_ref.id,
    })

    return redirect("/")


@app.route("/api/reports", methods=["GET"])
def api_reports():
    """JSON endpoint so the feed can be consumed programmatically if desired."""
    docs = (
        db.collection("reports")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(50)
        .stream()
    )
    results = []
    for doc in docs:
        d = doc.to_dict()
        ts = d.get("timestamp")
        results.append({
            "id": doc.id,
            "trail_name": d.get("trail_name"),
            "condition": d.get("condition"),
            "note": d.get("note"),
            "photo_url": d.get("photo_url"),
            "thumbnail_url": d.get("thumbnail_url"),
            "lat": d.get("lat"),
            "lng": d.get("lng"),
            "timestamp": ts.isoformat() if ts else None,
        })
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
