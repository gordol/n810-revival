"""Fresh interpreter entry for bounded local pack operations.

This file is called only by Worker with fixed operation names. Resource checks,
map decoding, copying, and publication all happen here, outside the UI process.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from worker import HANDLER, MAX_OUTPUT, MAX_RESULT, PRESETS, inventory_digest, validate_dependencies

EXISTING = {
    "lakewood": "pack", "lakewood-lod": "lakewood-lod-pack",
    "puget": "puget-pack", "puget-lod": "puget-lod-pack",
    "lakewood-fine": "lakewood-fine-pack",
    "lakewood-fine-lod": "lakewood-fine-lod-pack",
    "rainier": "rainier-pack", "rainier-lod": "rainier-lod-pack",
}


def fail_deadline(*unused):
    # Kill the entire owned session, including the nested bake. This remains
    # active even if the UI process disappears without calling Worker.close().
    try:
        os.write(2, b"Worker exceeded wall-clock deadline\n")
    finally:
        os.killpg(os.getpgrp(), signal.SIGKILL)


def limits(deadline):
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    cpu = math.ceil(deadline) + 5
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    signal.signal(signal.SIGALRM, fail_deadline)
    signal.setitimer(signal.ITIMER_REAL, deadline)


def check_staging(directory):
    count = total = 0
    for root, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs:
            if (Path(root) / name).is_symlink():
                raise ValueError("Worker created a directory symlink")
        for name in files:
            item = (Path(root) / name).lstat()
            if not stat.S_ISREG(item.st_mode):
                raise ValueError("Worker created an unsupported file")
            count += 1
            total += item.st_size
            if count > 1030 or total > MAX_OUTPUT + MAX_RESULT:
                raise ValueError("Worker output exceeded disk budget")


def summary(descriptor):
    allowed = ("artifact_id", "state", "compatible", "bytes", "path",
               "compatibility_reason", "manifest_sha256", "canonical_manifest_sha256")
    return {key: descriptor[key] for key in allowed if key in descriptor}


@contextmanager
def directory_fd(path):
    """Cleanup needs only stdlib, including when resource validation fails."""
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd
    finally:
        os.close(fd)


def cleanup_job(directory):
    """Remove bulk staging through a no-follow descriptor, inside this child."""
    with directory_fd(directory) as fd:
        for name in os.listdir(fd):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                shutil.rmtree(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)


def cleanup_stale(directory):
    """The inherited exclusive lease excludes every other active operation."""
    if not directory.name.startswith("operation-"):
        raise ValueError("Invalid operation staging directory")
    with directory_fd(directory.parent) as fd:
        names = [name for name in os.listdir(fd)
                 if name.startswith("operation-") and name != directory.name]
        if len(names) > 128:
            raise ValueError("Too many stale operation directories")
        for name in names:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if info.st_uid != os.getuid():
                raise ValueError("Stale staging is not owned by this user")
            if stat.S_ISDIR(info.st_mode):
                shutil.rmtree(name, dir_fd=fd)
            else:
                # In particular, never follow a symlink pretending to be a job.
                os.unlink(name, dir_fd=fd)


def stop_bake(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def write_result(directory, result):
    data = json.dumps(result, sort_keys=True, allow_nan=False).encode()
    if len(data) > MAX_RESULT:
        raise ValueError("Worker result exceeds size bound")
    temporary = directory / ".result.json"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, directory / "result.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("prepare", "import_existing", "import_artifact", "refresh"), required=True)
    parser.add_argument("--resource-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--lease-fd", type=int, required=True)
    parser.add_argument("--preset", choices=PRESETS)
    parser.add_argument("--artifact-id")
    args = parser.parse_args()
    if os.getpgrp() != os.getpid():
        parser.error("Worker must own its process group")
    if not 0 < args.deadline <= 120:
        parser.error("Invalid worker deadline")
    lease = os.fstat(args.lease_fd)
    if not stat.S_ISREG(lease.st_mode) or lease.st_uid != os.getuid():
        parser.error("Invalid worker lease")
    limits(args.deadline)
    result = dict(operation=args.operation, artifact=None, catalog=[], message="")
    process = None
    try:
        cleanup_stale(args.directory)
        raw = (HERE / "dependency-inventory.json").read_bytes()
        if not 0 < len(raw) <= 256 * 1024:
            raise ValueError("Invalid dependency inventory size")
        inventory = json.loads(raw)
        if inventory_digest(inventory) != args.inventory_sha256:
            raise ValueError("Dependency recipe changed before worker startup")
        validate_dependencies(args.resource_root, inventory)
        # These are the reviewed original resource modules, checked above.
        # Keep our reviewed operation modules ahead of the resource directory.
        sys.path.insert(1, str(args.resource_root))
        from artifact_store import ArtifactStore
        store = ArtifactStore(args.state_root, resource_root=args.resource_root)
        descriptor = None
        if args.operation == "prepare":
            if args.preset not in PRESETS:
                raise ValueError("A fixed preparation preset is required")
            output = args.directory / "pack"
            process = subprocess.Popen(
                [sys.executable, "-I", "-B", str(args.resource_root / HANDLER),
                 "--region", args.preset, "--output", str(output)],
                stdin=subprocess.DEVNULL, pass_fds=(args.lease_fd,),
            )
            while process.poll() is None:
                check_staging(args.directory)
                time.sleep(.02)
            code = process.wait()
            if code != 0:
                raise ValueError("Bake exited with status " + str(code))
            check_staging(args.directory)
            validate_dependencies(args.resource_root, inventory)
            descriptor = store.publish_pack(output)
            result["message"] = "Map pack prepared and published; import is a separate action"
        elif args.operation == "import_existing":
            if args.preset not in EXISTING:
                raise ValueError("A fixed existing-pack preset is required")
            source = args.resource_root / Path(HANDLER).parent / EXISTING[args.preset]
            descriptor = store.import_pack(source)
            result["message"] = "Existing map pack imported; viewer activation is separate"
        elif args.operation == "import_artifact":
            descriptor = store.import_artifact(args.artifact_id)
            result["message"] = "Published map pack imported; viewer activation is separate"
        else:
            result["message"] = "Map Library catalog refreshed"
        validate_dependencies(args.resource_root, inventory)
        if descriptor is not None:
            result["artifact"] = summary(descriptor)
        result["catalog"] = [summary(row) for row in store.list_artifacts()]
        cleanup_job(args.directory)
        write_result(args.directory, result)
        return 0
    except Exception as error:
        stop_bake(process)
        result.update(artifact=None, catalog=[], message=str(error)[:2048])
        try:
            cleanup_job(args.directory)
        except OSError as cleanup_error:
            result["message"] = (result["message"] + "; staging cleanup failed: "
                                 + str(cleanup_error))[:2048]
        write_result(args.directory, result)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        os.close(args.lease_fd)


if __name__ == "__main__":
    raise SystemExit(main())
