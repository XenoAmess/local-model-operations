"""Fail closed unless a workload is inside the enforced experiment cgroup."""

import json
import os
from pathlib import Path

GIB = 2**30
ROOT = Path(__file__).resolve().parents[1]


def available_bytes():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable is unavailable')


def require_isolation():
    relative = next(line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
    parts = Path(relative).parts
    if 'llmlab.slice' not in parts or not parts[-1].startswith('llmlab-') or not parts[-1].endswith('.service'):
        raise RuntimeError('Refusing uncontained workload. Start with scripts/run_isolated.py.')
    parent = Path('/sys/fs/cgroup') / Path(*parts[1:parts.index('llmlab.slice') + 1])
    group = Path('/sys/fs/cgroup') / relative.lstrip('/')
    maximum = (parent / 'memory.max').read_text().strip()
    if maximum == 'max' or int(maximum) > 88 * GIB:
        raise RuntimeError('Experiment slice has no acceptable hard memory limit')
    if (group / 'memory.oom.group').read_text().strip() != '1':
        raise RuntimeError('Workload must use OOMPolicy=kill with memory.oom.group=1')
    if available_bytes() < 28 * GIB:
        raise RuntimeError('Host has less than 28 GiB available; workload not started')
    snapshot = {
        'cgroup': relative,
        'aggregate_memory_max_bytes': int(maximum),
        'workload_memory_max_bytes': (group / 'memory.max').read_text().strip(),
        'workload_swap_max_bytes': (group / 'memory.swap.max').read_text().strip(),
        'oom_group': 1,
        'host_available_bytes': available_bytes(),
    }
    return snapshot


def bounded_environment(engine=None):
    env = dict(os.environ)
    env.update({
        'MAX_JOBS': '2',
        'NVCC_THREADS': '1',
        'FLASHINFER_NVCC_THREADS': '1',
        'CMAKE_BUILD_PARALLEL_LEVEL': '2',
        'TORCHINDUCTOR_COMPILE_THREADS': '1',
        'TOKENIZERS_PARALLELISM': 'false',
        'HF_HUB_DISABLE_XET': '1',
        'HF_XET_HIGH_PERFORMANCE': '0',
        'PYTHONUNBUFFERED': '1',
    })
    if engine:
        env['OMP_NUM_THREADS'] = '1' if engine == 'vllm' else '16'
    return env
