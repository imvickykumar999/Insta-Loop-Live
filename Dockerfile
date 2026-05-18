FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py stream_service.py telegram_notify.py env_loader.py ./
COPY templates/ templates/

RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -m appuser \
    && mkdir -p uploads logs \
    && chown -R appuser:appuser /app

ENV FLASK_APP=app.py
EXPOSE 5000
USER appuser

# Single worker: stream state is in-process memory
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
