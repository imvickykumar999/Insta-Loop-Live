#!/usr/bin/env python3
"""Flask web app for Instagram Live streaming."""

import os
import secrets
import tempfile
import time
from functools import wraps

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from stream_service import StreamService
from telegram_notify import is_configured, send_telegram_sync

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB uploads
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD_HASH = generate_password_hash(
    os.environ.get("APP_PASSWORD", "password")
)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

stream = StreamService()
stream.load_config()


def is_authenticated() -> bool:
    return bool(session.get("authenticated"))


def login_required_api(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"ok": False, "error": "Login required."}), 401
        return f(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    return render_template("index.html", authenticated=is_authenticated())


@app.route("/api/auth/session", methods=["GET"])
def api_auth_session():
    return jsonify(
        {
            "authenticated": is_authenticated(),
            "username": session.get("username") if is_authenticated() else None,
        }
    )


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or request.form.get("username", "")).strip()
    password = body.get("password") or request.form.get("password", "")

    if not secrets.compare_digest(username, APP_USERNAME) or not check_password_hash(
        APP_PASSWORD_HASH, password
    ):
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401

    session.clear()
    session["authenticated"] = True
    session["username"] = username
    session.permanent = True
    return jsonify({"ok": True, "message": "Logged in.", "username": username})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True, "message": "Logged out."})


@app.route("/api/status")
@login_required_api
def api_status():
    return jsonify(stream.get_status())


@app.route("/api/config", methods=["GET"])
@login_required_api
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
@login_required_api
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
@login_required_api
def api_upload():
    if "video" not in request.files:
        return jsonify({"ok": False, "error": "No file provided."}), 400

    f = request.files["video"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename."}), 400

    safe_name = os.path.basename(f.filename)
    dest = os.path.join(UPLOAD_DIR, safe_name)

    if os.path.exists(dest) and not os.access(dest, os.W_OK):
        stem, ext = os.path.splitext(safe_name)
        safe_name = f"{stem}_{int(time.time())}{ext}"
        dest = os.path.join(UPLOAD_DIR, safe_name)

    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_DIR, suffix=".upload")
    os.close(fd)
    try:
        f.save(tmp_path)
        os.replace(tmp_path, dest)
    except PermissionError:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify(
            {
                "ok": False,
                "error": (
                    "Permission denied writing to uploads/. "
                    "Files created by Docker may be owned by root — run: "
                    "sudo chown -R $USER:$USER uploads/"
                ),
            }
        ), 500
    except OSError as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify({"ok": False, "error": str(e)}), 500

    stream._append_log(f"Uploaded video: {safe_name}")
    return jsonify({"ok": True, "path": dest, "filename": safe_name})


@app.route("/api/start", methods=["POST"])
@login_required_api
def api_start():
    body = request.get_json(silent=True) or {}
    video = body.get("video", stream._video_path).strip()
    url = body.get("url", stream._rtmp_url).strip()
    key = body.get("key", stream._stream_key).strip()

    ok, message = stream.start_stream(video, url, key)
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message}), code


@app.route("/api/stop", methods=["POST"])
@login_required_api
def api_stop():
    ok, message = stream.stop_stream()
    return jsonify({"ok": ok, "message": message})


@app.route("/api/logs")
def api_logs():
    since = request.args.get("since", 0, type=int)
    return jsonify(stream.get_logs(since))


@app.route("/api/logs/clear", methods=["POST"])
@login_required_api
def api_clear_logs():
    stream.clear_logs()
    return jsonify({"ok": True})


@app.route("/api/telegram/test", methods=["POST"])
@login_required_api
def api_telegram_test():
    if not is_configured():
        return jsonify(
            {
                "ok": False,
                "error": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env",
            }
        ), 400
    ok, detail = send_telegram_sync("Insta-Loop-Live: test notification")
    if ok:
        return jsonify({"ok": True, "message": "Telegram test sent."})
    return jsonify({"ok": False, "error": detail}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
