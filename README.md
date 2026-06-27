# Insta-Loop-Live

Go Live on Instagram, Loop a Video.

Web UI to loop a local video and stream it to Instagram Live via RTMP (FFmpeg, vertical 720×1280).

![ss](https://github.com/user-attachments/assets/15bafaf6-0492-40c1-9b9e-f43ec6d9a8c6)

## Docker Hub

Published image: **[imvickykumar999/insta-loop-live](https://hub.docker.com/r/imvickykumar999/insta-loop-live)**

## Quick start (Docker)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed
- Instagram **RTMP URL** and **stream key** (from Instagram when you go live)

### Pull the image

```bash
docker pull imvickykumar999/insta-loop-live:latest
```

### Run the container

```bash
docker run -d \
  --name insta-loop-live \
  --restart unless-stopped \
  -p 3000:5000 \
  -v "$(pwd)/uploads:/app/uploads" \
  -v "$(pwd)/logs:/app/logs" \
  imvickykumar999/insta-loop-live:latest
```

Open the app: **http://localhost:3000**

| Flag | Purpose |
|------|---------|
| `-p 3000:5000` | App on port **3000** (container listens on 5000) |
| `-v .../uploads` | Persist uploaded videos |
| `-v .../logs` | Persist stream logs |
| `--restart unless-stopped` | Keep running in the background |

### Optional: persist settings

To save RTMP URL, stream key, and video path between restarts, mount a config file:

```bash
# Create config on the host first (example)
cat > ig_stream_config.json << 'EOF'
{
  "video": "/app/uploads/your-video.mp4",
  "url": "rtmps://live-upload.instagram.com:443/rtmp/",
  "key": "YOUR_STREAM_KEY"
}
EOF

docker run -d \
  --name insta-loop-live \
  --restart unless-stopped \
  -p 3000:5000 \
  -v "$(pwd)/uploads:/app/uploads" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/ig_stream_config.json:/app/ig_stream_config.json" \
  imvickykumar999/insta-loop-live:latest
```

> **Security:** Do not commit `ig_stream_config.json` to git; it contains your stream key.

## Troubleshooting: Permission Denied Error

If you see a `PermissionError: [Errno 13] Permission denied` in logs or when uploading a video/saving configuration, it is because the Docker container runs as a non-root user `appuser` (UID `1000`), but the directories and config file on the host were created by the root user.

To fix this, change the ownership of these files/folders on the host to UID/GID `1000`:

```bash
sudo chown -R 1000:1000 ig_stream_config.json uploads logs
```

Then, restart the container:

```bash
docker restart insta-loop-live
```

## Using the app

1. Open **http://localhost:3000**
2. **Upload** a video or set the path to `/app/uploads/yourfile.mp4`
3. Enter your **RTMP URL** and **stream key**
4. Click **Go Live** to start looping the video to Instagram
5. Click **Stop stream** when finished

After upload via the UI, use the container path (e.g. `/app/uploads/myvideo.mp4`) as the video source.

## Manage the container

```bash
docker logs -f insta-loop-live    # follow logs
docker stop insta-loop-live         # stop
docker start insta-loop-live        # start again
docker rm -f insta-loop-live        # remove
```

## Run from source (without Docker Hub)

```bash
git clone https://github.com/imvickykumar999/Insta-Loop-Live.git
cd Insta-Loop-Live
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Requires ffmpeg on the host
python app.py
```

Or build and run locally:

```bash
docker-compose up -d --build
```

## License

BSD-3-Clause — see [LICENSE](LICENSE).
