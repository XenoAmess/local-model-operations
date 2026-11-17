#!/usr/bin/env python3
"""Launch one workload as a sibling of Paseo, bounded by kernel cgroups."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from resource_guard import ROOT, GIB, available_bytes, bounded_environment


def memory_high_gib(maximum, explicit=None):
    if type(maximum) is not int or not 1<=maximum<=80:
        raise ValueError('Workload hard memory limit must be between1and80GiB')
    if explicit is not None:
        if type(explicit) is not int or not 1<=explicit<=maximum:
            raise ValueError('Soft memory limit must be positive and no larger than the hard limit')
        return explicit
    return 79 if maximum==80 else max(1,maximum-(8 if maximum>=16 else 2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unit', required=True)
    parser.add_argument('--memory-gib', type=int, default=80, choices=range(1, 81))
    parser.add_argument('--memory-high-gib',type=int)
    parser.add_argument('--wait', action='store_true')
    parser.add_argument('--runtime-max-seconds',type=int,choices=range(1,3601))
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A workload command is required')
    try:
        high=memory_high_gib(args.memory_gib,args.memory_high_gib)
    except ValueError as error:
        parser.error(str(error))
    unit = args.unit.removesuffix('.service')
    if not re.fullmatch(r'llmlab-[a-z0-9-]+', unit) or unit == 'llmlab-guard':
        parser.error('Use a unique llmlab-... workload name')
    config_dir = Path.home() / '.config/systemd/user'
    config_dir.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'systemd/llmlab.slice'
    (config_dir / source.name).write_text(source.read_text())
    watchdog = f'''[Unit]
Description=Keep host memory available for Paseo and Codex

[Service]
Type=exec
ExecStart={sys.executable} {ROOT / 'scripts/memory_watchdog.py'}
MemoryMax=128M
MemorySwapMax=0
OOMPolicy=kill
Restart=no
'''
    (config_dir / 'llmlab-guard.service').write_text(watchdog)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'start', 'llmlab-guard.service'], check=True)
    if available_bytes() < 28 * GIB:
        raise SystemExit('Host reserve below 28 GiB; refusing to start workload')
    subprocess.run(['systemctl', '--user', 'start', 'llmlab.slice'], check=True)
    group = subprocess.check_output(['systemctl', '--user', 'show', 'llmlab.slice', '-p', 'ControlGroup', '--value'], text=True).strip()
    hard_limit = (Path('/sys/fs/cgroup') / group.lstrip('/') / 'memory.max').read_text().strip()
    if hard_limit != str(88 * GIB):
        raise SystemExit(f'Hard limit did not take effect: {hard_limit}')
    # Large pinned/UVA models cannot reclaim their live host tensors. A soft
    # limit far below the hard limit can indefinitely throttle initialization.
    # Keep the 80 GiB hard bound and the independent aggregate/host reserve.
    launch = ['systemd-run', '--user', '--unit', unit, '--slice', 'llmlab.slice',
              '--working-directory', str(ROOT.parent), '--property', 'Type=exec',
              '--property', 'MemoryAccounting=yes', '--property', f'MemoryHigh={high}G',
              '--property', f'MemoryMax={args.memory_gib}G', '--property', 'MemorySwapMax=1G',
              '--property', 'OOMPolicy=kill', '--property', 'OOMScoreAdjust=500',
              '--property', 'KillMode=control-group', '--property', f'TimeoutStopSec={2 if args.runtime_max_seconds else 15}',
              '--property', 'Restart=no', '--property', 'TasksMax=384',
              '--property', 'LimitCORE=0',
              '--property', 'UMask=0077']
    if args.runtime_max_seconds:
        launch += ['--property',f'RuntimeMaxSec={args.runtime_max_seconds}']
    # Explicit proxy variables are used if present; never log credentials.
    environment = bounded_environment()
    names = ['PATH', 'MAX_JOBS', 'NVCC_THREADS', 'FLASHINFER_NVCC_THREADS',
             'CMAKE_BUILD_PARALLEL_LEVEL', 'TORCHINDUCTOR_COMPILE_THREADS',
             'TOKENIZERS_PARALLELISM', 'HF_HUB_DISABLE_XET', 'HF_XET_HIGH_PERFORMANCE',
             'PYTHONUNBUFFERED', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
             'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy']
    for name in names:
        if name in environment:
            launch.append(f'--setenv={name}={environment[name]}')
    if args.wait:
        launch += ['--wait']
    launch += ['--'] + command
    entry = {'time': time.time(), 'unit': unit + '.service', 'aggregate_memory_max_bytes': 88 * GIB,
             'workload_memory_max_bytes': args.memory_gib * GIB,
             'workload_memory_high_bytes': high * GIB, 'command': command}
    with (ROOT / 'logs/isolated-launches.jsonl').open('a') as out:
        out.write(json.dumps(entry) + '\n')
    return subprocess.call(launch)


if __name__ == '__main__':
    raise SystemExit(main())
