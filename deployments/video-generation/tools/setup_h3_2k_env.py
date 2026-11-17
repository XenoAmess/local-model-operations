#!/usr/bin/env python3
"""Create a separate Python entry point reusing verified local dependencies without modifying them."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    environment = ROOT / ".venv-h3-2k"
    production = ROOT / "FastVideo/.venv"
    base_python = subprocess.check_output([
        str(production / "bin/python"), "-c", "import sys;print(sys._base_executable)"
    ], text=True).strip()
    if not (environment / "bin/python").exists():
        subprocess.run(["uv", "venv", str(environment), "--python", base_python], check=True)
    site_packages = environment / "lib/python3.12/site-packages"
    (site_packages / "production-dependencies.pth").write_text(
        str(production / "lib/python3.12/site-packages") + "\n" + str(ROOT / "FastVideo") + "\n")
    command = """import json,sys,importlib.metadata as m
names=['torch','torchvision','diffusers','transformers','fastapi','uvicorn','accelerate','av','safetensors','gradio']
print(json.dumps({'python':sys.version,'packages':{name:m.version(name) for name in names}}))"""
    receipt = json.loads(subprocess.check_output([str(environment / "bin/python"), "-c", command], text=True))
    receipt.update({"environment": str(environment), "dependency_source": str(production),
                    "production_packages_modified": False, "fastvideo_source": str(ROOT / "FastVideo")})
    (ROOT / "deployment/minimax-h3/2k-environment.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Separate H3 2K environment ready; production dependencies unchanged")


if __name__ == "__main__":
    main()
