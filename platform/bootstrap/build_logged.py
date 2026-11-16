#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Retain build output, inherit private stdin, and preserve the build exit status."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import uuid


def run(command, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    print(f"Build log: {log.resolve()}", flush=True)
    with os.fdopen(fd, "wb") as output:
        # Inherit stdin: password/setup input must never pass through the logger.
        with subprocess.Popen(command, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as child:
            for line in child.stdout:
                output.write(line)
                output.flush()
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            status = child.wait()
        output.write(f"\nBuild exit status: {status}\n".encode())
    print(f"Build {'failed' if status else 'completed'}; log: {log.resolve()}", flush=True)
    return status if status >= 0 else 128 - status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply a build command after --")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log = args.log or Path("dist/build-logs") / f"n810-{stamp}-{uuid.uuid4().hex[:8]}.log"
    return run(command, log)


if __name__ == "__main__":
    sys.exit(main())
