import os
import re
import logging
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template
from azure.storage.blob import BlobServiceClient, ContentSettings, PublicAccess

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
STORAGE_ACCOUNT_URL = "//jwj3bjstoragecase07.blob.core.windows.net"
IMAGES_CONTAINER = "lanternfly-images-obzocjkq"
CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

# ------------------------------------------------------------
# Flask setup + logging
# ------------------------------------------------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Create BlobServiceClient (use connection string locally, else URL + DefaultAzureCredential)
if CONNECTION_STRING:
    blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
else:
    blob_service_client = BlobServiceClient(account_url=STORAGE_ACCOUNT_URL)

# Ensure container exists
try:
    container_client = blob_service_client.get_container_client(IMAGES_CONTAINER)
    container_client.create_container(public_access=PublicAccess.Container)
except Exception:
    container_client = blob_service_client.get_container_client(IMAGES_CONTAINER)

# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

def sanitize_filename(filename: str) -> str:
    """Remove unsafe chars and ensure only alphanumerics, dashes, underscores, and dots."""
    filename = os.path.basename(filename)
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return filename

def allowed_file(content_type: str) -> bool:
    """Accept only image MIME types."""
    return content_type.startswith("image/")

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route("/api/v1/upload", methods=["POST"])
def upload():
    try:
        if "file" not in request.files:
            return jsonify(ok=False, error="Missing file field"), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify(ok=False, error="Empty filename"), 400

        # Validate content type
        if not allowed_file(file.content_type):
            return jsonify(ok=False, error="Unsupported file type"), 400

        # Enforce max size (10 MB)
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > 10 * 1024 * 1024:
            return jsonify(ok=False, error="File too large (max 10 MB)"), 400

        sanitized_name = sanitize_filename(file.filename)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        blob_name = f"{timestamp}-{sanitized_name}"

        # Upload to Azure Blob Storage
        container_client.upload_blob(
            name=blob_name,
            data=file,
            overwrite=True,
            content_settings=ContentSettings(content_type=file.content_type),
        )

        blob_url = f"{container_client.url}/{blob_name}"
        logging.info(f"Uploaded image: {blob_url}")
        return jsonify(ok=True, url=blob_url)

    except Exception as e:
        logging.exception("Upload failed")
        return jsonify(ok=False, error=str(e)), 500


@app.route("/api/v1/gallery", methods=["GET"])
def gallery():
    try:
        blobs = container_client.list_blobs()
        gallery_urls = [f"{container_client.url}/{b.name}" for b in blobs]
        return jsonify(ok=True, gallery=gallery_urls)
    except Exception as e:
        logging.exception("Gallery fetch failed")
        return jsonify(ok=False, error=str(e)), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.get("/")
def index():
    return render_template("index.html")



# ------------------------------------------------------------
# Run app
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
