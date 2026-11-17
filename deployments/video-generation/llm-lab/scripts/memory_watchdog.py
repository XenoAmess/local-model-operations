#!/usr/bin/env python3
"""Stop only llmlab.slice when host memory pressure threatens the session."""

import json
from pathlib import Path
import subprocess
import time

from resource_guard import available_bytes, GIB, ROOT


def main():
    log = ROOT / 'logs/memory-watchdog.jsonl'
    low_samples = 0
    minimum = available_bytes()
    last_report = 0
    while True:
        available = available_bytes()
        minimum = min(minimum, available)
        low_samples = low_samples + 1 if available < 24 * GIB else 0
        stop = available < 16 * GIB or low_samples >= 3
        now = time.time()
        if stop or now - last_report >= 30:
            entry = {'time': now, 'host_available_bytes': available,
                     'minimum_available_bytes': minimum, 'event': 'memory_reserve_stop' if stop else 'sample'}
            with log.open('a') as out:
                out.write(json.dumps(entry) + '\n')
            last_report = now
        if stop:
            subprocess.run(['systemctl', '--user', 'stop', 'llmlab.slice'], check=False, timeout=25)
            low_samples = 0
            # The launcher requires a running guard. No automatic workload restart.
            raise SystemExit(75)
        time.sleep(1)


if __name__ == '__main__':
    main()
