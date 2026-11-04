"""One explicitly approved, bounded local fixed-v2 map bake; no remote jobs."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

PRESETS = ("lakewood", "lakewood-lod", "puget", "puget-lod",
           "lakewood-fine", "lakewood-fine-lod", "rainier", "rainier-lod")
HANDLER = "experiments/map-drag-trial/regional-pack-v2/bake.py"
MAX_LOG = 16384
MAX_OUTPUT = 5 * 1024 * 1024
MAX_RESULT = 65536
CHILD_ENTRY = Path(__file__).with_name("worker_child.py")
OPERATIONS = ("prepare", "import_existing", "import_artifact", "refresh")


def validate_summary(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid catalog entry")
    allowed = {"artifact_id", "state", "compatible", "bytes", "path",
               "compatibility_reason", "manifest_sha256", "canonical_manifest_sha256"}
    if (set(value) - allowed or not isinstance(value.get("artifact_id"), str)
            or not re.fullmatch("[0-9a-f]{64}", value["artifact_id"])
            or value.get("state") not in ("published", "imported")
            or type(value.get("compatible")) is not bool
            or type(value.get("bytes")) is not int
            or not 0 < value["bytes"] <= MAX_OUTPUT):
        raise ValueError("Invalid catalog summary")
    for name in ("path", "compatibility_reason", "manifest_sha256", "canonical_manifest_sha256"):
        if name in value and (not isinstance(value[name], str) or len(value[name]) > 2048):
            raise ValueError("Catalog text exceeds bound")


def inventory_digest(inventory):
    return hashlib.sha256(json.dumps(inventory, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def validate_dependencies(resource_root, inventory):
    """Hash all pinned inputs without importing or executing their contents."""
    resource_root = Path(resource_root).resolve()
    project = resource_root.parents[1]
    if not isinstance(inventory, dict) or inventory.get("version") != 1:
        raise ValueError("Unsupported dependency inventory")
    rows = inventory.get("files")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError("Invalid dependency inventory")
    seen = set()
    for row in rows:
        relative = row.get("path") if isinstance(row, dict) else None
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or Path(relative).is_absolute()
                or any(part in ("", ".", "..") for part in relative.split("/"))
                or relative in seen):
            raise ValueError("Invalid dependency path")
        seen.add(relative)
        path = project
        for part in relative.split("/"):
            path = path / part
            if stat.S_ISLNK(path.lstat().st_mode):
                raise ValueError("Dependency symlinks are not supported")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != row.get("bytes"):
                raise ValueError("Dependency size changed: " + relative)
            digest = hashlib.sha256()
            while block := stream.read(65536):
                digest.update(block)
        if digest.hexdigest() != row.get("sha256"):
            raise ValueError("Dependency checksum changed: " + relative)
    expected_handler = str((resource_root / HANDLER).relative_to(project))
    if expected_handler not in seen:
        raise ValueError("Bake handler is missing from dependency inventory")
    return inventory_digest(inventory)



class Worker:
    """The UI polls this process; there is no independent daemon or thread."""
    def __init__(self, preset, resource_root, staging_root, inventory, deadline=120,
                 *, operation="prepare", state_root=None, artifact_id=None):
        if operation not in OPERATIONS:
            raise ValueError("Unsupported worker operation")
        if operation in ("prepare", "import_existing") and preset not in PRESETS:
            raise ValueError("Unsupported map preset")
        if not 0 < deadline <= 120:
            raise ValueError("Invalid worker deadline")
        self.resource_root = Path(resource_root).resolve()
        self.inventory = inventory
        self.dependency_sha256 = inventory_digest(inventory)
        self.operation = operation
        self.result = None
        staging_root = Path(staging_root).absolute()
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_root = Path(state_root).absolute() if state_root is not None else staging_root.parent
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lease = os.open(state_root / "worker.lease", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(lease)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Unsafe worker lease file")
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ValueError) as error:
            os.close(lease)
            raise ValueError("A worker still owns this state directory") from error
        try:
            self.directory = Path(tempfile.mkdtemp(prefix="operation-", dir=staging_root))
        except BaseException:
            os.close(lease)
            raise
        self.output = self.directory / "pack"
        self.log_path = self.directory / "worker.log"
        self.result_path = self.directory / "result.json"
        self.log = bytearray()
        self.log_truncated = False
        self.started = time.monotonic()
        self.deadline = deadline
        self.termination_started = None
        self.kill_sent = False
        self.stdout_eof = False
        self.cancelled = False
        self.done = False
        self.error = None
        self.returncode = None
        env = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT"):
            env.pop(name, None)
        for name, relative in (("HOME", "home"), ("XDG_CACHE_HOME", "cache"),
                               ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                               ("XDG_STATE_HOME", "state"), ("TMPDIR", "tmp"),
                               ("TMP", "tmp"), ("TEMP", "tmp")):
            destination = self.directory / relative
            destination.mkdir(mode=0o700, exist_ok=True)
            env[name] = str(destination)
        try:
            command = [sys.executable, "-I", "-B", str(CHILD_ENTRY),
                       "--operation", operation, "--resource-root", str(self.resource_root),
                       "--state-root", str(state_root), "--directory", str(self.directory),
                       "--inventory-sha256", self.dependency_sha256,
                       "--deadline", str(deadline), "--lease-fd", str(lease)]
            if preset is not None:
                command.extend(["--preset", preset])
            if artifact_id is not None:
                command.extend(["--artifact-id", artifact_id])
            self.process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True,
                cwd=self.directory, env=env, pass_fds=(lease,),
            )
            os.set_blocking(self.process.stdout.fileno(), False)
        except BaseException:
            process = getattr(self, "process", None)
            if process is not None:
                self._signal(signal.SIGKILL)
                process.wait()
                process.stdout.close()
            # Setup created at most these empty directories. Any child output
            # is reclaimed by the next child, never recursively by the UI.
            for name in ("home", "cache", "config", "data", "state", "tmp"):
                try:
                    (self.directory / name).rmdir()
                except OSError:
                    pass
            try:
                self.directory.rmdir()
            except OSError:
                pass
            raise
        finally:
            os.close(lease)

    def _signal(self, signum):
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            pass

    def _terminate(self, reason):
        if self.termination_started is None:
            self.error = reason
            self.termination_started = time.monotonic()
            self._signal(signal.SIGTERM)

    def cancel(self):
        self.cancelled = True
        self._terminate("Cancelled by user")

    @property
    def readiness_fd(self):
        stream = getattr(getattr(self, 'process', None), 'stdout', None)
        if self.done or self.stdout_eof or stream is None or stream.closed:
            return None
        return stream.fileno()

    @property
    def next_deadline(self):
        if self.done:
            return None
        if self.termination_started is None:
            return self.started+self.deadline
        if self.kill_sent:
            return None
        return self.termination_started+1

    def _drain(self):
        # Drain at most 64 KiB per UI poll, retaining only the first 16 KiB.
        if self.stdout_eof or self.process.stdout.closed:
            return
        for _ in range(16):
            try:
                data = os.read(self.process.stdout.fileno(), 4096)
            except BlockingIOError:
                break
            if not data:
                self.stdout_eof = True
                break
            available = MAX_LOG - len(self.log)
            self.log.extend(data[:available])
            self.log_truncated |= len(data) > available

    def poll(self):
        if self.done:
            return True
        self._drain()
        now = time.monotonic()
        if now - self.started >= self.deadline:
            self._terminate("Worker exceeded wall-clock deadline")
        if self.termination_started is not None and now - self.termination_started >= 1 and not self.kill_sent:
            self._signal(signal.SIGKILL)
            self.kill_sent = True
        code = self.process.poll()
        if code is None:
            return False
        self.returncode = self.process.wait()
        # Reap/terminate any descendants that retained this process group.
        self._signal(signal.SIGKILL)
        self._drain()
        self.process.stdout.close()
        self.log_path.write_bytes(self.log)
        self.log_path.chmod(0o600)
        self.done = True
        try:
            result_fd = os.open(self.result_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(result_fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_RESULT:
                    raise ValueError("Invalid worker result size")
                raw = stream.read(MAX_RESULT + 1)
            if len(raw) != info.st_size or len(raw) > MAX_RESULT:
                raise ValueError("Worker result changed while reading")
            result = json.loads(raw)
            if (not isinstance(result, dict) or result.get("operation") != self.operation
                    or not isinstance(result.get("catalog"), list)
                    or len(result["catalog"]) > 64
                    or not isinstance(result.get("message"), str)
                    or len(result["message"]) > 2048):
                raise ValueError("Invalid worker result")
            for row in result["catalog"]:
                validate_summary(row)
            if result.get("artifact") is not None:
                validate_summary(result["artifact"])
            self.result = result
            if self.error is None and code != 0:
                self.error = result["message"]
        except (ValueError, OSError) as error:
            if self.error is None:
                if code < 0 and time.monotonic() - self.started >= self.deadline:
                    self.error = "Worker exceeded wall-clock deadline"
                elif code != 0:
                    self.error = "Worker exited with status " + str(code)
                else:
                    self.error = str(error)
        return True

    def close(self):
        if not self.done:
            self.cancel()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._signal(signal.SIGKILL)
                self.process.wait()
            self.poll()
