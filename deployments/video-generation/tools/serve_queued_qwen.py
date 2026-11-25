#!/usr/bin/env python3
"""Start the approved engine profile on the scheduler-owned loopback transport."""
import argparse
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "llm-lab/scripts"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int, default=8005)
    args = parser.parse_args()
    if not 8005 <= args.port <= 8099:
        parser.error("Choose a dedicated loopback port between 8005 and 8099")
    sys.path.insert(0, str(SCRIPTS))
    from resource_guard import require_isolation
    require_isolation()
    import inference_transport
    legacy = inference_transport.binding

    def queued_binding(settings):
        legacy(settings)
        return "127.0.0.1", args.port

    # The existing launcher and inference profile are hashed by the quality
    # proofs. Change the binding only inside this scheduler-owned process.
    inference_transport.binding = queued_binding
    launcher = SCRIPTS / "serve_coder_lan.py"
    sys.argv = [str(launcher), "--config", args.config]
    runpy.run_path(str(launcher), run_name="__main__")


if __name__ == "__main__":
    main()
