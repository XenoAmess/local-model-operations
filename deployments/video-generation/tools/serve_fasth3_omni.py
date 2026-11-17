#!/usr/bin/env python3
"""Validate resource containment before importing the video runtime."""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
from resource_guard import require_isolation

require_isolation()
from fastvideo.entrypoints.cli.main import main

config = os.environ.get("FASTVIDEO_SERVE_CONFIG", str(ROOT / "fasth3-omni.yaml"))
sys.argv = ["fastvideo", "serve", "--config", config]
main()
