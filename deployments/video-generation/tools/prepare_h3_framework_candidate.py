#!/usr/bin/env python3
"""Install a pinned candidate's resolved dependencies outside production."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("framework", choices=("sglang", "uniserve"))
    parser.add_argument("--phase", choices=("dependencies", "kernels"), default="dependencies")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    source = ROOT / "tools/vendor" / (args.framework + "-candidate")
    output = ROOT / "outputs/framework-comparison-20261117"
    venv = source / ".venv"
    env = os.environ.copy()
    env.update(UV_CONCURRENT_DOWNLOADS="1", UV_CONCURRENT_BUILDS="1", UV_CONCURRENT_INSTALLS="2",
               CUDA_VISIBLE_DEVICES="", TORCH_CUDA_ARCH_LIST="12.0", CUDA_HOME=str(ROOT / "tools/cuda"),
               CARGO_BUILD_JOBS="2", RAYON_NUM_THREADS="2")
    env["PATH"] = str(ROOT / "tools/cuda/bin") + ":" + env["PATH"]
    uv = str(Path.home() / ".local/bin/uv")
    state = dict(framework=args.framework, phase=args.phase, started=time.time(), status="installing_" + args.phase,
                 source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
                 environment=str(venv), production_environment_modified=False)
    status_file = output / (args.framework + "-" + args.phase + "-setup.json")
    status_file.write_text(json.dumps(state, indent=2) + "\n")
    try:
        if args.phase == "kernels":
            subprocess.run([uv, "pip", "install", "--python", str(venv / "bin/python"), "--no-build-isolation", "--no-deps",
                            "-e", str(source / "uniserve_kernels")], cwd=source, env=env, check=True)
        else:
            if not (venv / "bin/python").exists():
                subprocess.run([uv, "venv", "--python", str(ROOT / ".venv-h3-2k/bin/python"), str(venv)], env=env, check=True)
            requirements = output / (args.framework + "-requirements.txt")
            overrides = []
            if args.framework == "uniserve":
                # uv pip compile resolves the workspace kernel as a relative
                # editable. Install dependencies first, then compile that kernel
                # in a separately bounded build unit with the installed Torch.
                text = "\n".join(line for line in requirements.read_text().splitlines() if not line.startswith("-e "))
                requirements = output / "uniserve-dependencies-only.txt"
                requirements.write_text(text + "\nsetuptools>=77\nwheel\n")
                override_file = output / "uniserve-dependency-overrides.txt"
                override_file.write_text("nvidia-nccl-cu13==2.30.4\n")
                overrides = ["--override", str(override_file)]
            subprocess.run([uv, "pip", "install", "--python", str(venv / "bin/python"), *overrides, "-r", str(requirements)], env=env, check=True)
        state["status"] = "dependencies_installed_source_import_not_yet_verified"
    except Exception as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        state["finished"] = time.time()
        status_file.write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    main()
