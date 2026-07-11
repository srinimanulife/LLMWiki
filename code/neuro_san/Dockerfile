# Neuro SAN + nsflow sidecar image
# Runs: neuro-san-server (port 8080) + nsflow UI (port 4173) + S3 sync loop
# Uses uv for fast installs; pre-bundled wheels for packages blocked by corporate proxy.
FROM python:3.12-slim

WORKDIR /app

# Install system deps + uv (fast Python package manager)
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    curl ca-certificates awscli \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv \
       --trusted-host pypi.org \
       --trusted-host files.pythonhosted.org

# Trust Zscaler CA so Python requests/urllib can reach AWS APIs at runtime
COPY streamlit/zscaler-ca.pem /usr/local/share/ca-certificates/zscaler-ca.crt
RUN update-ca-certificates

# Stage 1 — install pre-bundled wheels (proxy-blocked or source-only packages)
# pyhocon is source-only on PyPI (no wheel) — pre-built from source
COPY neuro_san/pyhocon-0.3.63-py3-none-any.whl /wheels/
COPY neuro_san/neuro_san-0.6.74-py3-none-any.whl /wheels/
COPY neuro_san/neuro_san_studio-0.3.8-py3-none-any.whl /wheels/
COPY neuro_san/nsflow-0.6.9-py3-none-any.whl /wheels/
RUN uv pip install --system --no-deps /wheels/*.whl

# Stage 2 — install remaining deps from PyPI (all available as wheels)
COPY neuro_san/requirements.txt requirements.txt
RUN uv pip install --system \
    --allow-insecure-host pypi.org \
    --allow-insecure-host files.pythonhosted.org \
    --allow-insecure-host pypi.python.org \
    --no-build-isolation \
    -r requirements.txt

# LLMWiki coded tools (SK-01 to SK-05)
COPY neuro_san/coded_tools/ coded_tools/

# Shared common library — same source used by Lambda Layer
COPY lambda/common/ lambda_common/

# HOCON registries + LLM config (baseline — overridden by S3 sync at runtime)
COPY registries/ registries/
COPY config/llm_config.hocon config/llm_config.hocon

# S3 hot-reload sync sidecar + startup script
COPY neuro_san/sync_registries.sh sync_registries.sh
COPY neuro_san/start.sh start.sh
RUN chmod +x sync_registries.sh start.sh

# neuro-san-server HTTP/WS port + nsflow React UI port
EXPOSE 8080 4173

# PYTHONPATH: lambda_common (for llmwiki_common) + app root (for coded_tools.llmwiki.*)
ENV PYTHONPATH=/app/lambda_common:/app

ENTRYPOINT ["/bin/bash", "start.sh"]
