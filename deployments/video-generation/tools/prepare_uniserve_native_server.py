#!/usr/bin/env python3
"""Install a private Rust toolchain or build the isolated UniServe server."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("toolchain", "build"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    require_isolation()
    source = ROOT / "tools/vendor/uniserve-candidate"
    env = os.environ.copy()
    env.update(CARGO_HOME=str(source / ".cargo-local"), RUSTUP_HOME=str(source / ".rustup-local"),
               RUSTUP_TOOLCHAIN="1.96.0", CARGO_BUILD_JOBS="2", RAYON_NUM_THREADS="2",
               CARGO_NET_GIT_FETCH_WITH_CLI="true", CARGO_HTTP_MULTIPLEXING="false",
               UV_CONCURRENT_DOWNLOADS="1", UV_CONCURRENT_BUILDS="1",
               CUDA_VISIBLE_DEVICES="", PYO3_PYTHON=str(source / ".venv/bin/python"))
    env["PATH"] = ":".join((str(source / ".cargo-local/bin"), str(source / ".venv/bin"),
                             str(ROOT / "FastVideo/.venv/bin"), str(ROOT / "tools/cuda/bin"), env["PATH"]))
    if args.action == "toolchain":
        installer = source / "rustup-init"
        previous = source / ".rustup-init"
        if previous.exists() and not installer.exists():
            previous.replace(installer)
        if not installer.exists():
            url = "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init"
            with urllib.request.urlopen(url, timeout=60) as response, installer.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            installer.chmod(0o700)
        subprocess.run([str(installer), "-y", "--no-modify-path", "--profile", "minimal", "--default-toolchain", "1.96.0"], env=env, check=True)
        subprocess.run([str(Path.home() / ".local/bin/uv"), "pip", "install", "--python", str(source / ".venv/bin/python"), "setuptools-rust>=1.11"], env=env, check=True)
    else:
        subprocess.run([str(Path.home() / ".local/bin/uv"), "pip", "install", "--python", str(source / ".venv/bin/python"),
                        "--no-deps", "--no-build-isolation", "-e", str(source)], env=env, cwd=source, check=True)


if __name__ == "__main__":
    main()
