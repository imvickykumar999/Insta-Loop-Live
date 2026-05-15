"""Instagram Live streaming backend (shared by Flask app)."""

import json
import os
import platform
import queue
import subprocess
import threading
from collections import deque
from datetime import datetime

CONFIG_FILE = "ig_stream_config.json"
LOG_FILE = "logs/insta_stream.log"
MAX_LOG_LINES = 500


class StreamService:
    def __init__(self):
        self.streaming = False
        self.ffmpeg_process = None
        self.stream_thread = None
        self.output_queue = queue.Queue()
        self.log_buffer = deque(maxlen=MAX_LOG_LINES)
        self._lock = threading.Lock()
        self._video_path = ""
        self._rtmp_url = ""
        self._stream_key = ""
        self._status = "Ready to stream"
        self._status_kind = "ready"  # ready | live | error | stopping

        os.makedirs("logs", exist_ok=True)
        self._start_output_reader()

    def _start_output_reader(self):
        def reader():
            while True:
                try:
                    msg = self.output_queue.get(timeout=0.1)
                    if msg:
                        self._append_log(msg)
                except queue.Empty:
                    continue

        threading.Thread(target=reader, daemon=True).start()

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with self._lock:
            self.log_buffer.append(line)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def get_logs(self, since: int = 0):
        with self._lock:
            lines = list(self.log_buffer)
        if since < 0:
            since = 0
        if since >= len(lines):
            return {"lines": [], "next": len(lines)}
        chunk = lines[since:]
        return {"lines": chunk, "next": len(lines)}

    def clear_logs(self):
        with self._lock:
            self.log_buffer.clear()

    def get_status(self):
        with self._lock:
            return {
                "streaming": self.streaming,
                "status": self._status,
                "status_kind": self._status_kind,
                "video": self._video_path,
                "rtmp_url": self._rtmp_url,
                "has_stream_key": bool(self._stream_key),
            }

    def get_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"video": "", "url": "", "key": ""}

    def save_config(self, video: str, url: str, key: str):
        data = {"video": video, "url": url, "key": key}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self._append_log("Settings saved.")
        return data

    def load_config(self):
        data = self.get_config()
        self._video_path = data.get("video", "")
        self._rtmp_url = data.get("url", "")
        self._stream_key = data.get("key", "")
        if any(data.values()):
            self._append_log("Settings loaded.")
        return data

    def _set_status(self, msg: str, kind: str = "ready"):
        with self._lock:
            self._status = msg
            self._status_kind = kind

    def start_stream(self, video: str, rtmp_url: str, stream_key: str):
        with self._lock:
            if self.streaming:
                return False, "Stream is already running."

        if not video or not stream_key:
            return False, "Video source and stream key are required."

        if not os.path.isfile(video):
            return False, f"Video file not found: {video}"

        self._video_path = video
        self._rtmp_url = rtmp_url
        self._stream_key = stream_key
        self.streaming = True
        self._set_status("Starting Instagram Live...", "ready")

        self.stream_thread = threading.Thread(target=self._run_ffmpeg, daemon=True)
        self.stream_thread.start()
        return True, "Stream starting."

    def stop_stream(self):
        self.streaming = False
        self._set_status("Stopping...", "stopping")

        proc = self.ffmpeg_process
        if proc:
            try:
                if platform.system() == "Windows":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        check=False,
                    )
                else:
                    proc.terminate()
            except OSError:
                pass

        self.ffmpeg_process = None
        self._set_status("Stream stopped", "ready")
        self._append_log("Stream stopped.")
        return True, "Stream stopped."

    def _run_ffmpeg(self):
        video = self._video_path
        url = self._rtmp_url
        key = self._stream_key

        cmd = [
            "ffmpeg",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            video,
            "-vf",
            "crop=in_h*9/16:in_h,scale=720:1280",
            "-c:v",
            "libx264",
            "-preset",
            "superfast",
            "-b:v",
            "2500k",
            "-maxrate",
            "2500k",
            "-bufsize",
            "5000k",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "60",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-f",
            "flv",
            f"{url}{key}",
        ]

        self._append_log("Launching FFmpeg...")

        try:
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
            self._set_status("LIVE on Instagram", "live")

            for line in iter(self.ffmpeg_process.stdout.readline, ""):
                if not self.streaming:
                    break
                if line.strip():
                    self.output_queue.put(line.strip())

            self.ffmpeg_process.wait()
        except Exception as e:
            self._append_log(f"Execution error: {e}")
            self._set_status(f"Error: {e}", "error")

        if self.streaming:
            self.stop_stream()
