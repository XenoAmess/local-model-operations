#!/usr/bin/env python3
"""Execute the pinned PBZ review recipe under the shared GPU lease."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from blender_review import (
    BLENDER_ROOT, IMPORTER_ROOT, MAX_UNPACKED, SOURCE, SOURCE_ROOT, SUITE,
    ReviewParams, inspect_archive, ready, render_metering, resolve_manifest, validate_samples,
)
from model_registry import ROOT
from queued_llm import atomic_json


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_gpu():
    result = subprocess.run(["nvidia-smi", "--id=0", "--query-gpu=name,memory.used,memory.total",
                             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
    name, used, total = (value.strip() for value in result.stdout.strip().split(","))
    return name, int(used), int(total)


def extract(archive_path, target, entries):
    expanded = 0
    with zipfile.ZipFile(archive_path) as archive:
        for name, item in entries.items():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, destination.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    expanded += len(chunk)
                    if expanded > MAX_UNPACKED:
                        raise ValueError("Extracted bytes exceed the limit")
                    output.write(chunk)


def sandbox(input_dir, result_dir, pinned_animations):
    cmd = ["/usr/bin/bwrap", "--die-with-parent", "--new-session", "--unshare-net", "--unshare-pid",
           "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
           "--ro-bind", "/bin", "/bin", "--ro-bind", "/etc", "/etc", "--ro-bind", "/sys", "/sys",
           "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
           "--ro-bind", str(BLENDER_ROOT), "/blender",
           "--ro-bind", str(SOURCE_ROOT / "scripts"), "/recipe/scripts",
           "--ro-bind", str(SUITE.parent), "/recipe/qa/suites",
           "--ro-bind", str(IMPORTER_ROOT), "/recipe/vendor/UEFormat/plugins/blender",
           "--ro-bind", str(input_dir), "/input", "--bind", str(result_dir), "/output",
           "--ro-bind", str(pinned_animations), "/recipe/repro/game_reference/animations",
           "--clearenv", "--setenv", "HOME", "/tmp", "--setenv", "PATH", "/usr/bin:/bin",
           "--setenv", "XDG_RUNTIME_DIR", "/tmp", "--chdir", "/recipe"]
    for node in sorted(Path("/dev").glob("nvidia*")):
        if not node.is_dir():
            cmd.extend(["--dev-bind", str(node), str(node)])
    for directory in ("/dev/dri", "/dev/nvidia-caps", "/proc/driver/nvidia"):
        if Path(directory).is_dir():
            cmd.extend(["--dev-bind" if directory.startswith("/dev/") else "--ro-bind", directory, directory])
    libs = ROOT / "tools/vendor/pbz-blender-libs"
    if libs.is_dir():
        cmd.extend(["--ro-bind", str(libs), "/recipe/tools/blender_libs"])
    return cmd


def render(folder):
    request = json.loads((folder / "request.json").read_text())
    params = ReviewParams.model_validate(request["params"])
    if not ready():
        raise RuntimeError("Pinned Blender, PBZ script or UEFormat importer is missing")
    validate_samples(params)
    archive_path = Path(request["archive_path"])
    if sha(archive_path) != request["input_sha256"]:
        raise ValueError("The input archive no longer matches its submitted SHA-256")
    raw, entries = inspect_archive(archive_path)
    assets = resolve_manifest(raw, entries, params)
    workspace = folder / "blender"
    inputs, outputs, animations = (workspace / name for name in ("input", "output", "animations"))
    for path in (inputs, outputs, animations):
        path.mkdir(parents=True)
    extract(archive_path, inputs, entries)
    for name, value in assets["animations"].items():
        shutil.copyfile(inputs / value, animations / (name + ".ueanim"))
    suite_sha = sha(SUITE)
    donor_report = json.loads((inputs / assets["donor"]).with_name("sampling_report.json").read_text())
    if donor_report["input_hashes"]["suite"] != suite_sha:
        raise ValueError("The motion donor report does not match the pinned suite")
    gpu_name, peak, gpu_total = read_gpu()
    runner = "run_baiqi_cc0_motion_review.py"
    started = time.monotonic()
    deadline = started + params.timeout_seconds
    planned = params.image_count()
    reports = {}
    command = sandbox(inputs, outputs, animations)
    (folder / "render-ready").touch()
    for name in params.forms:
        (outputs / name).mkdir()
        command_args = [*command, "/blender/blender", "--background", "--factory-startup", "--disable-autoexec",
                        "--python-exit-code", "12", "--python", "/recipe/scripts/" + runner, "--",
                        "--candidate", "/input/" + assets["forms"][name], "--donor", "/input/" + assets["donor"],
                        "--cc0-control", "/input/" + assets["cc0_control"], "--out", "/output/" + name,
                        "--render", "triage", "--neck-head-share", ".35", "--game-hair-shadows",
                        "--resolution", *map(str, params.resolution), "--samples", str(params.samples)]
        for key, values in (("--case", params.cases), ("--view", params.views), ("--sample-index", params.sample_indices)):
            for value in values:
                command_args.extend([key, str(value)])
        with (outputs / "worker.log").open("ab", buffering=0) as log:
            process = subprocess.Popen(command_args, stdout=log, stderr=log)
            try:
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Blender review exceeded the requested time")
                    completed = sum(1 for _ in outputs.rglob("*.png"))
                    atomic_json(folder / "progress.json", {"completed_images": completed, "planned_images": planned,
                                                          "form": name, "stage": "rendering"})
                    _, used, _ = read_gpu()
                    peak = max(peak, used)
                    time.sleep(1)
                if process.returncode:
                    raise RuntimeError(f"Blender exited {process.returncode}; see render log")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        reports[name] = json.loads((outputs / name / "motion_report.json").read_text())["status"]
    completed = sum(1 for _ in outputs.rglob("*.png"))
    if completed != planned:
        raise RuntimeError(f"Expected {planned} PNGs, got {completed}")
    render_seconds = round(time.monotonic() - started, 3)
    metering = render_metering(render_seconds)
    manifest = {"kind": "blender_review", "source_commit": SOURCE, "source_sha256": sha(SOURCE_ROOT / "scripts" / runner),
                "suite_sha256": suite_sha, "suite_version": json.loads(SUITE.read_text())["version"],
                "blender": "5.3.0", "engine": "EEVEE", "input_sha256": request["input_sha256"],
                "gpu": gpu_name, "vram_total_mib": gpu_total, "peak_device_memory_mib": peak,
                "render_seconds": render_seconds, "metering": metering, "params": params.model_dump(),
                "model_sha256": {name: sha(inputs / path) for name, path in assets["forms"].items()},
                "donor_sha256": sha(inputs / assets["donor"]), "cc0_control_sha256": sha(inputs / assets["cc0_control"]),
                "motion_review_status": reports, "images": completed, "game_runtime_allowed": False,
                "files": [{"path": path.relative_to(outputs).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size}
                          for path in sorted(outputs.rglob("*")) if path.is_file()]}
    atomic_json(outputs / "manifest.json", manifest)
    temporary = folder / "result.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as result:
        for file in sorted(outputs.rglob("*")):
            if file.is_file():
                result.write(file, file.relative_to(outputs).as_posix())
    target = folder / "result.zip"
    temporary.replace(target)
    atomic_json(folder / "result-meta.json", {"sha256": sha(target), "bytes": target.stat().st_size,
                                            "images": completed, "render_seconds": render_seconds,
                                            "motion_review_status": reports, "metering": metering})
    atomic_json(folder / "progress.json", {"completed_images": completed, "planned_images": planned, "stage": "completed"})


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    job_dir = Path(sys.argv[1]).resolve()
    try:
        render(job_dir)
    except Exception as error:
        atomic_json(job_dir / "worker-error.json", {"code": type(error).__name__, "message": str(error)})
        raise
