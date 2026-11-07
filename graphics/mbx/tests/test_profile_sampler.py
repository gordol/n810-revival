"""Run on Linux: test_profile_sampler.py /path/to/profile-sampler.

For ARM emulation, put qemu and its arguments before the executable.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

command = sys.argv[1:]
assert command, 'Provide the sampler command'
with tempfile.TemporaryDirectory() as directory:
    output = Path(directory) / 'samples.jsonl'
    args = [str(output), '3', '10', str(os.getpid())]
    subprocess.run(command + args, check=True)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 3
    assert all(b['monotonic_ns'] > a['monotonic_ns'] for a, b in zip(rows, rows[1:]))
    records = [row['processes'][str(os.getpid())] for row in rows]
    assert len({row['start'] for row in records}) == 1
    assert all(b['ticks'] >= a['ticks'] for a, b in zip(records, records[1:]))
    assert all(row['collection_cpu_ns'] > 0 for row in rows)
    assert subprocess.run(command + args).returncode == 3
    for count, period, pid in [('0', '10', '1'), ('121', '10', '1'),
                               ('3x', '10', '1'), ('3', '10x', '1'), ('3', '10', '0')]:
        assert subprocess.run(command + [str(Path(directory) / 'bad'), count, period, pid]).returncode == 2
print('PASS profiler timestamps, process identity, CPU counters, exclusive output and invalid arguments')
