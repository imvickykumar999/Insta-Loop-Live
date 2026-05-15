#!/usr/bin/env python3
"""Flask web app for Instagram Live streaming."""

import os

from flask import Flask, jsonify, render_template, request

from stream_service import StreamService

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB uploads

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

stream = StreamService()
stream.load_config()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify(stream.get_status())


@app.route("/api/config", methods=["GET"])
def api_get_config():
    data = stream.get_config()
    return jsonify(
        {
            "video": data.get("video", ""),
            "url": data.get("url", ""),
            "key": data.get("key", ""),
        }
    )


@app.route("/api/config", methods=["POST"])
def api_save_config():
    body = request.get_json(silent=True) or {}
    video = body.get("video", "").strip()
    url = body.get("url", "").strip()
    key = body.get("key", "").strip()
    stream.save_config(video, url, key)
    stream._video_path = video
    stream._rtmp_url = url
    stream._stream_key = key
    return jsonify({"ok": True, "message": "Settings saved."})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "video" not in request.files:
        return jsonify({"ok": False, "error": "No file provided."}), 400

    f = request.files["video"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename."}), 400

    safe_name = os.path.basename(f.filename)
    dest = os.path.join(UPLOAD_DIR, safe_name)
    f.save(dest)
    stream._append_log(f"Uploaded video: {safe_name}")
    return jsonify({"ok": True, "path": dest, "filename": safe_name})


@app.route("/api/start", methods=["POST"])
def api_start():
    body = request.get_json(silent=True) or {}
    video = body.get("video", stream._video_path).strip()
    url = body.get("url", stream._rtmp_url).strip()
    key = body.get("key", stream._stream_key).strip()

    ok, message = stream.start_stream(video, url, key)
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message}), code


@app.route("/api/stop", methods=["POST"])
def api_stop():
    ok, message = stream.stop_stream()
    return jsonify({"ok": ok, "message": message})


@app.route("/api/logs")
def api_logs():
    since = request.args.get("since", 0, type=int)
    return jsonify(stream.get_logs(since))


@app.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    stream.clear_logs()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
