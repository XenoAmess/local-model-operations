"""Model adapters and scheduling preferences for the shared GPU."""
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "deployment/video-queue/model-registry.json"
ADAPTERS = {"omni", "ic", "openai_llm", "blender_review"}


def load_registry(path=None):
    source = Path(path or os.environ.get("UNIFIED_MODEL_REGISTRY", DEFAULT_REGISTRY))
    with source.open() as stream:
        config = json.load(stream)
    models = {}
    for entry in config["models"]:
        name = entry["id"]
        if name in models or entry["adapter"] not in ADAPTERS:
            raise ValueError(f"Invalid or duplicate model: {name}")
        if type(entry["max_inflight"]) is not int or not 1 <= entry["max_inflight"] <= 32:
            raise ValueError(f"Invalid model concurrency: {name}")
        models[name] = entry
    return config, models


def task_sort_key(job):
    return (-job.get("priority", 0), -job.get("front_order", 0), job["created"], job["id"])


def effective_duration(config, preferences, model):
    overrides = preferences.get("models", {})
    return overrides.get(model, preferences.get("default_seconds", config["default_residency_seconds"]))


def select_job(jobs, active_model, ready_at, duration, now=None):
    """Safety boundaries are enforced by the caller, after in-flight GPU work drains."""
    ordered = sorted(jobs, key=task_sort_key)
    if not ordered:
        return None
    same = [job for job in ordered if job["model"] == active_model]
    other = [job for job in ordered if job["model"] != active_model]
    now = time.time() if now is None else now
    if same and other:
        if ready_at is None or now < ready_at + duration:
            return same[0]
        return other[0]
    return ordered[0]
