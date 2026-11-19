# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the shared source flasher build from Pocket Setup without blocking input."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile


def build(progress, cancelled):
    repository = Path(__file__).resolve().parents[2]
    script = repository / 'platform/flasher/build.py'
    if not script.is_file() or not (repository / 'Makefile').is_file():
        raise ValueError('Building the host flasher requires the full source checkout')
    progress('Building the pinned host flasher; no tablet is accessed…')
    output = repository / 'dist/flasher'
    environment = os.environ.copy()
    # The wizard always builds for this host. Cross builds use Make explicitly.
    environment.pop('FLASHER_TARGET', None)
    environment.pop('FLASHER_OUTPUT', None)
    with tempfile.TemporaryFile(mode='w+b') as log:
        process = subprocess.Popen(['make', 'flasher', 'FLASHER_TARGET=native',
                                    'FLASHER_OUTPUT=' + str(output)],
                                   cwd=repository, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                if cancelled.wait(.1):
                    raise InterruptedError('Flasher build cancelled')
            if process.returncode:
                log.seek(max(0, log.tell() - 4096))
                lines = log.read().decode('utf-8', 'replace').splitlines()
                detail = next((line for line in reversed(lines) if not line.startswith('make:')), 'Build failed')
                raise RuntimeError(detail[:512])
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    record = json.loads((output / 'BUILD.json').read_text())
    return {'state': 'flasher_built', 'binary': str(output / '0xFFFF'),
            'source_revision': record['identity']['source_revision']}
