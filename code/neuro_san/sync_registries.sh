#!/bin/bash
# Syncs HOCON registries from S3 to /app/registries/ every 3 seconds.
# Enables hot-reload: AGENT_MANIFEST_UPDATE_PERIOD_SECONDS=5 picks up changes
# within ~8 seconds of an editor saving to S3.
while true; do
  aws s3 sync "s3://${WIKI_BUCKET}/wiki/neuro-san/registries/" /app/registries/ --quiet 2>/dev/null || true
  sleep 3
done
