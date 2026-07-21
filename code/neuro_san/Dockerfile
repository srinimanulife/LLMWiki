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
COPY neuro_san/neuro_san-0.6.79-py3-none-any.whl /wheels/
COPY neuro_san/neuro_san_studio-0.3.8-py3-none-any.whl /wheels/
COPY neuro_san/nsflow-0.6.16-py3-none-any.whl /wheels/
RUN uv pip install --system --no-deps /wheels/*.whl

# Stage 2 — install remaining deps from PyPI (all available as wheels)
COPY neuro_san/requirements.txt requirements.txt
RUN uv pip install --system \
    --allow-insecure-host pypi.org \
    --allow-insecure-host files.pythonhosted.org \
    --allow-insecure-host pypi.python.org \
    --no-build-isolation \
    -r requirements.txt

# Patch two nsflow 0.6.16 bugs in the editor backend:
# 1. OperationStore.list_all_drafts calls _read_jsonl (private) but only read_jsonl (public) exists.
# 2. SimpleStateManager.__init__ never calls _initialize_empty_state unless NSFLOW_PLUGIN_MANUAL_EDITOR=True,
#    leaving current_state={} and causing KeyError('meta') on every set_network_name call.
RUN python3 - <<'PYEOF'
import pathlib, site
base = pathlib.Path(site.getsitepackages()[0])

# Fix 1: ops_store.py — list_all_drafts calls OperationStore._read_jsonl() but the
# method is defined as read_jsonl (public, no underscore). Add a _read_jsonl static
# method that delegates. Guard on "def _read_jsonl" to avoid double-patching.
p = base / "nsflow/backend/utils/editor/ops_store.py"
src = p.read_text()
if "def _read_jsonl" not in src:
    src = src.replace(
        "    @staticmethod\n    def _write_json",
        "    @staticmethod\n    def _read_jsonl(path):\n        return OperationStore.read_jsonl(path)\n\n    @staticmethod\n    def _write_json"
    )
    p.write_text(src)
    print("ops_store.py patched (_read_jsonl added)")
else:
    print("ops_store.py already patched")

# Fix 2: simple_state_manager.py — _initialize_empty_state only called when
# NSFLOW_PLUGIN_MANUAL_EDITOR=True; always call it so current_state["meta"] exists.
p2 = base / "nsflow/backend/utils/editor/simple_state_manager.py"
src2 = p2.read_text()
if "self._initialize_empty_state()  # always" not in src2:
    src2 = src2.replace(
        "        self.max_history = 20  # Reduced for simplicity\n\n        if self.NSFLOW_PLUGIN_MANUAL_EDITOR:",
        "        self.max_history = 20  # Reduced for simplicity\n        self._initialize_empty_state()  # always\n\n        if self.NSFLOW_PLUGIN_MANUAL_EDITOR:"
    )
    p2.write_text(src2)
    print("simple_state_manager.py patched (always init state)")
else:
    print("simple_state_manager.py already patched")
PYEOF

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

# Register agent_network_designer (WAND) + its required sub-agents so the
# /editor AI design chat works. agent_network_designer calls 3 sub-agents as
# external network tools (/agent_network_editor, /agent_network_query_generator,
# /agent_network_instructions_editor) — all must be in the manifest.
RUN python3 - <<'PYEOF'
import pathlib, site

pkg = pathlib.Path(site.getsitepackages()[0])
dst_dir = pathlib.Path("/app/registries/llmwiki")

wand_agents = [
    "agent_network_designer",
    "agent_network_editor",
    "agent_network_query_generator",
    "agent_network_instructions_editor",
    "agent_network_architect",
    "agent_network_test_generator",
]

for name in wand_agents:
    src = pkg / f"registries/{name}.hocon"
    if src.exists():
        dst = dst_dir / f"{name}.hocon"
        dst.write_text(src.read_text())
        print(f"Copied {name}.hocon")
    else:
        print(f"WARNING: {name}.hocon not found in pip package")

manifest = dst_dir / "manifest.hocon"
mtext = manifest.read_text()
changed = False
for name in wand_agents:
    entry = f'"{name}.hocon"'
    if entry not in mtext:
        mtext = mtext.rstrip().rstrip("}").rstrip()
        mtext += f',\n    "{name}.hocon": true\n}}\n'
        changed = True
        print(f"manifest: added {name}")

if changed:
    manifest.write_text(mtext)
    print("manifest.hocon saved")
else:
    print("manifest.hocon already up to date")
PYEOF

# neuro-san-server HTTP/WS port + nsflow React UI port
EXPOSE 8080 4173

# PYTHONPATH: site-packages (middleware.agent_network_designer classes for WAND),
# lambda_common (llmwiki_common), app root (coded_tools.llmwiki.*).
# Copy all WAND coded_tools sub-packages into /app/coded_tools so they are found
# when Python resolves coded_tools.* (/app/coded_tools takes precedence as a package).
RUN for pkg in agent_network_editor agent_network_query_generator \
               agent_network_instructions_editor agent_network_architect \
               agent_network_test_generator; do \
      cp -r /usr/local/lib/python3.12/site-packages/coded_tools/${pkg} \
            /app/coded_tools/${pkg}; \
    done
ENV PYTHONPATH=/usr/local/lib/python3.12/site-packages:/app/lambda_common:/app

ENTRYPOINT ["/bin/bash", "start.sh"]
