"""Instagram Live streaming backend (shared by Flask app)."""

import json
import os
import platform
import queue
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

from telegram_notify import is_configured, send_telegram

CONFIG_FILE = "ig_stream_config.json"
LOG_FILE = "logs/insta_stream.log"
MAX_LOG_LINES = 500
MAX_AUTO_RESTARTS = 5
RESTART_DELAY_SEC = 3


def build_rtmp_url(rtmp_url: str, stream_key: str) -> str:
    """Join RTMP base URL and stream key (Instagram: rtmps://host/rtmp/KEY)."""
    base = rtmp_url.strip()
    key = stream_key.strip()
    if not base or not key:
        return ""
    if key.startswith("?"):
        return f"{base.rstrip('/')}{key}"
    return f"{base.rstrip('/')}/{key.lstrip('/')}"


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
        self._restart_count = 0
        self._stop_requested = False
        self._live_notified = False

        os.makedirs("logs", exist_ok=True)
        if is_configured():
            self._append_log("Telegram notifications enabled.")
        else:
            self._append_log(
                "Telegram notifications disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)."
            )
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
        self._stop_requested = False
        self._restart_count = 0
        self._live_notified = False
        self.streaming = True
        self._set_status("Starting Instagram Live...", "ready")

        self.stream_thread = threading.Thread(target=self._run_ffmpeg, daemon=True)
        self.stream_thread.start()
        return True, "Stream starting."

    def stop_stream(self):
        self._stop_requested = True
        self.streaming = False
        self._set_status("Stopping...", "stopping")

        with self._lock:
            proc = self.ffmpeg_process

        if proc and proc.poll() is None:
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

        self._set_status("Stream stopped", "ready")
        self._append_log("Stream stopped.")
        self._notify_stopped(user_requested=True)
        return True, "Stream stopped."

    def _notify_live(self) -> None:
        if self._live_notified:
            return
        self._live_notified = True
        video = os.path.basename(self._video_path) or "unknown"
        send_telegram(
            f"🟢 Instagram Live started\nVideo: {video}",
            on_error=lambda e: self._append_log(f"Telegram notify failed: {e}"),
        )

    def _notify_stopped(self, user_requested: bool = True) -> None:
        self._live_notified = False
        reason = "stopped by user" if user_requested else "stream ended"
        send_telegram(
            f"⏹ Instagram Live {reason}",
            on_error=lambda e: self._append_log(f"Telegram notify failed: {e}"),
        )

    def _terminate_proc(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except OSError:
            pass

    def _ffmpeg_cmd(self, video: str, rtmp_target: str) -> list[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            video,
            "-vf",
            "crop=in_h*9/16:in_h,scale=720:1280",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "zerolatency",
            "-profile:v",
            "main",
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
            "-keyint_min",
            "60",
            "-sc_threshold",
            "0",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-f",
            "flv",
            rtmp_target,
        ]

    def _run_ffmpeg_once(self) -> int | None:
        video = self._video_path
        rtmp_target = build_rtmp_url(self._rtmp_url, self._stream_key)
        if not rtmp_target:
            self._append_log("Invalid RTMP URL or stream key.")
            return -1

        cmd = self._ffmpeg_cmd(video, rtmp_target)
        self._append_log("Launching FFmpeg...")
        self._append_log(f"Video: {video}")

        proc: subprocess.Popen | None = None
        return_code: int | None = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
            with self._lock:
                self.ffmpeg_process = proc

            self._set_status("LIVE on Instagram", "live")
            self._notify_live()

            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                if not self.streaming:
                    break
                if line.strip():
                    self.output_queue.put(line.strip())
        except Exception as e:
            self._append_log(f"Execution error: {e}")
            self._set_status(f"Error: {e}", "error")
            return -1
        finally:
            if proc is not None:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except OSError:
                    pass
                if self.streaming:
                    self._terminate_proc(proc)
                return_code = proc.wait()
                with self._lock:
                    if self.ffmpeg_process is proc:
                        self.ffmpeg_process = None

        return return_code

    def _run_ffmpeg(self):
        while self.streaming and not self._stop_requested:
            return_code = self._run_ffmpeg_once()

            if self._stop_requested or not self.streaming:
                break

            self._restart_count += 1
            if self._restart_count > MAX_AUTO_RESTARTS:
                self._append_log(
                    f"Stream ended (FFmpeg code {return_code}). "
                    "Max reconnect attempts reached. Refresh your Instagram stream key and try again."
                )
                self._set_status("Stream ended — check stream key", "error")
                self.streaming = False
                self._notify_stopped(user_requested=False)
                break

            self._append_log(
                f"Stream disconnected (FFmpeg code {return_code}). "
                f"Reconnecting in {RESTART_DELAY_SEC}s "
                f"({self._restart_count}/{MAX_AUTO_RESTARTS})..."
            )
            self._set_status("Reconnecting...", "ready")
            time.sleep(RESTART_DELAY_SEC)

        self.streaming = False
        with self._lock:
            self.ffmpeg_process = None
