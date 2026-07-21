#!/bin/sh
# Kill any stale nginx from a previous container restart on the same ENI
pkill -x nginx 2>/dev/null || true
sleep 0.5

# Start nginx reverse proxy (listens on 8501, proxies / → 8502, /phoenix → 6006, /agents → 4173)
nginx -c /app/nginx-proxy.conf &

# Start Streamlit on its internal port
exec streamlit run app.py \
  --server.port=8502 \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
