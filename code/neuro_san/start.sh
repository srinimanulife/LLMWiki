#!/bin/bash
set -e

echo "[start.sh] Starting Neuro SAN sidecar..."

# S3 sync loop — hot-reload HOCON files every 3 seconds
if [ -n "$WIKI_BUCKET" ]; then
  echo "[start.sh] Starting S3 sync from s3://${WIKI_BUCKET}/neuro-san/registries/"
  /bin/bash /app/sync_registries.sh &
else
  echo "[start.sh] WIKI_BUCKET not set — using bundled registries (no hot-reload)"
fi

# Start neuro-san server (HTTP + WebSocket on port 8080)
echo "[start.sh] Starting neuro-san-server on port 8080..."
python -m neuro_san_studio.runner.neuro_san_server_wrapper \
  --http_port 8080 &
SERVER_PID=$!

# Wait for server to be ready (health check loop, max 30s)
echo "[start.sh] Waiting for neuro-san-server health..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/livez > /dev/null 2>&1; then
    echo "[start.sh] neuro-san-server ready after ${i}s"
    break
  fi
  sleep 1
done

# Start nsflow UI (FastAPI + React SPA on port 4173)
echo "[start.sh] Starting nsflow on port 4173..."
exec python -m uvicorn nsflow.backend.main:app \
  --host 0.0.0.0 \
  --port 4173 \
  --log-level info
