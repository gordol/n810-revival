"""Isolated admission entry point. No renderer selection or device access."""
import json
from pathlib import Path
import signal
import sys


def main():
    # -I excludes ambient Python paths. Only this release's code is authority.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    signal.alarm(14)
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        from map_library_provider import admit_provider
        if len(sys.argv) != 4:
            raise ValueError('Invalid admission arguments')
        reference = admit_provider(*sys.argv[1:])
        result = dict(reference=reference.to_mapping(), error=None)
    except Exception as error:
        result = dict(reference=None, error=str(error)[:2048])
    raw = json.dumps(result, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > 65536:
        raw = b'{"reference":null,"error":"Map validation result exceeds its limit"}'
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
