#!/usr/bin/env python3
"""Prepare only the pinned experimental FROST checkout in a bounded unit."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "9638468d752dbc97fc252be3a973855a0c4e9651"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    source = ROOT / "tools/vendor/cudnn-frontend-frost-candidate"
    source.parent.mkdir(parents=True, exist_ok=True)
    if not (source / ".git").exists():
        subprocess.run(["git", "init", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "remote", "add", "origin", "https://github.com/NVIDIA/cudnn-frontend.git"], check=True)
    subprocess.run(["git", "-C", str(source), "fetch", "--depth", "1", "origin", COMMIT], check=True, timeout=180)
    subprocess.run(["git", "-C", str(source), "checkout", "--detach", COMMIT], check=True)
    assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == COMMIT
    patch = ROOT / "deployment/minimax-h3/frost-aot-explicit-engines.patch"
    if patch.exists():
        applied = subprocess.run(["git", "-C", str(source), "apply", "--reverse", "--check", str(patch)], capture_output=True).returncode == 0
        if not applied:
            subprocess.run(["git", "-C", str(source), "apply", "--check", str(patch)], check=True)
            subprocess.run(["git", "-C", str(source), "apply", str(patch)], check=True)
    output = ROOT / "outputs/video-queue/engineering-tests-after-S42-20261121"
    output.mkdir(parents=True, exist_ok=True)
    record = {"source": str(source), "commit": COMMIT, "isolation": isolation,
              "production_packages_modified": False, "status": "source_prepared_build_pending"}
    if patch.exists():
        record.update(aot_host_dispatch_patch=str(patch), aot_host_dispatch_patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
                      attention_kernel_sources_modified=False)
    (output / "source-preparation.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    if args.build:
        environment = output / "frost-env"
        python = environment / "bin/python"
        if not python.exists():
            subprocess.run(["uv", "venv", str(environment), "--python", str(ROOT / "FastVideo/.venv/bin/python")], check=True)
        site = next((environment / "lib").glob("python*/site-packages"))
        (site / "readonly-production-dependencies.pth").write_text(
            "import site; site.addsitedir(" + repr(str(ROOT / "FastVideo/.venv/lib/python3.12/site-packages")) + ")\n")
        env = dict(os.environ, CUDA_PATH=str(ROOT / "tools/cuda"), CUDAToolkit_ROOT=str(ROOT / "tools/cuda"),
                   CUDNN_PATH=str(ROOT / "FastVideo/.venv/lib/python3.12/site-packages/nvidia/cudnn"))
        env["PATH"] = str(environment / "bin") + ":" + str(ROOT / "FastVideo/.venv/bin") + ":" + str(ROOT / "tools/cuda/bin") + ":" + env["PATH"]
        env["PYTHONPATH"] = str(source / "python")
        subprocess.run(["uv", "pip", "install", "--python", str(python), "--no-deps", "nanobind>=3.0.1,<4"], check=True, env=env, timeout=180)
        python_include = subprocess.check_output([str(python), "-c", "import sysconfig;print(sysconfig.get_path('include'))"], text=True).strip()
        # New glibc's feature macros conflict with uv CPython headers if C++
        # standard headers come first. Pre-include Python.h, without changing
        # upstream sources or GPU arithmetic flags. Demote only GCC 15's
        # free-nonheap-object warning in this host Python extension build.
        build_env = dict(env, CXXFLAGS="-include " + str(Path(python_include) / "Python.h")
                         + " -Wno-error=free-nonheap-object")
        if not list((source / "python/cudnn").glob("_compiled_module*.so")):
            subprocess.run(["uv", "pip", "install", "--python", str(python), "--no-deps", "--no-build-isolation", "-e", str(source)],
                           check=True, env=build_env, timeout=900)
        subprocess.run([str(python), "-c", "import cudnn, pathlib; print('candidate import:', cudnn.__file__); "
                        + "assert pathlib.Path(cudnn.__file__).resolve() == pathlib.Path(" + repr(str(source / "python/cudnn/__init__.py")) + ").resolve()"],
                       check=True, env=env)
        cuda = ROOT / "tools/cuda"
        if not (cuda / "bin/cuobjdump").exists():
            extra = output / "cuda-extra/nvidia/cu13/bin/cuobjdump"
            if not extra.exists():
                raise RuntimeError("Install nvidia-cuda-cuobjdump 13.2 into this run's cuda-extra target first")
            overlay = output / "cuda-overlay"
            (overlay / "bin").mkdir(parents=True, exist_ok=True)
            for entry in cuda.iterdir():
                if entry.name != "bin" and not (overlay / entry.name).exists():
                    (overlay / entry.name).symlink_to(entry.resolve())
            for entry in (cuda / "bin").iterdir():
                if not (overlay / "bin" / entry.name).exists():
                    (overlay / "bin" / entry.name).symlink_to(entry.resolve())
            if not (overlay / "bin/cuobjdump").exists():
                (overlay / "bin/cuobjdump").symlink_to(extra)
            cuda = overlay
        with (output / "frost-build.log").open("w") as log:
            subprocess.run([str(python), str(source / "aot/sm120/build.py"), "--out", str(output / "frost-aot"),
                            "--classes", "d128_nomask", "--jobs", "2", "--cuda", str(cuda)],
                           check=True, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
        record.update(status="aot_built_gpu_test_pending", environment=str(environment),
                      library=str(output / "frost-aot/lib/libcudnn_frontend_aot_sm120.so"))
        (output / "source-preparation.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
