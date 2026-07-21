"""
Step 0 — Start Phoenix and verify it is healthy.

Runs Phoenix via docker.exe (WSL), waits for :6006 to respond, then prints
the URL. If Phoenix is already running this script is a no-op.

Usage:
    python eval/step0_start_phoenix.py
    python eval/step0_start_phoenix.py --reset   # stops + removes old container first
"""

import argparse
import subprocess
import sys
import time
import urllib.request
import urllib.error

from phoenix_config import PHOENIX_ENDPOINT, PHOENIX_GRPC_PORT

CONTAINER_NAME = "phoenix-llmwiki"
VOLUME_NAME    = "phoenix-llmwiki-data"
IMAGE          = "arizephoenix/phoenix:latest"  # DockerHub mirror (ghcr.io blocked by Zscaler)


def _run(cmd: str) -> tuple[int, str]:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def _phoenix_healthy() -> bool:
    try:
        with urllib.request.urlopen(f"{PHOENIX_ENDPOINT}/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _container_running() -> bool:
    rc, out = _run(f"docker.exe inspect -f '{{{{.State.Running}}}}' {CONTAINER_NAME} 2>/dev/null")
    return "true" in out.lower()


def start(reset: bool = False) -> None:
    if reset:
        print("Stopping existing Phoenix container...")
        _run(f"docker.exe stop {CONTAINER_NAME}")
        _run(f"docker.exe rm {CONTAINER_NAME}")

    if _phoenix_healthy():
        print(f"Phoenix already healthy at {PHOENIX_ENDPOINT}")
        print(f"UI:  {PHOENIX_ENDPOINT}")
        return

    if _container_running():
        print("Container running but not healthy yet — waiting...")
    else:
        print(f"Starting Phoenix container ({IMAGE})...")
        cmd = (
            f"docker.exe run -d"
            f" --name {CONTAINER_NAME}"
            f" -p 6006:6006"
            f" -p {PHOENIX_GRPC_PORT}:{PHOENIX_GRPC_PORT}"
            f" -v {VOLUME_NAME}:/mnt/data"
            f" -e PHOENIX_WORKING_DIR=/mnt/data"
            f" {IMAGE}"
        )
        # Note: port 9000 (HTTP OTLP) is skipped — conflicts with other services on this host.
        # Traces are seeded via REST POST /v1/traces on :6006 instead.
        rc, out = _run(cmd)
        if rc != 0 and "already in use" not in out and "already exists" not in out:
            print(f"ERROR: docker run failed:\n{out}")
            sys.exit(1)
        print(f"Container started: {out[:64]}")

    # Wait up to 60 seconds — Phoenix takes ~15s to start its ASGI server
    print("Waiting for Phoenix to become healthy", end="", flush=True)
    for _ in range(60):
        if _phoenix_healthy():
            print(" OK")
            break
        print(".", end="", flush=True)
        time.sleep(1)
    else:
        print("\nERROR: Phoenix did not become healthy within 60 seconds")
        sys.exit(1)

    print(f"\nPhoenix is ready.")
    print(f"  UI:      {PHOENIX_ENDPOINT}")
    print(f"  gRPC:    http://localhost:{PHOENIX_GRPC_PORT}")
    print(f"  HTTP:    http://localhost:9000")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start Phoenix locally via docker.exe")
    parser.add_argument("--reset", action="store_true",
                        help="Stop and remove existing container before starting")
    args = parser.parse_args()
    start(reset=args.reset)
