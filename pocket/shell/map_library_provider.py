"""Verified local map providers. Call admission/open only in background workers.

The reviewed Archive reader injection owns all cell decoding. This adapter binds
those reads to a retained directory descriptor and binds approvals to full data
inventory and the executing installed viewer, without changing built-in packs.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

import map_tiles
import map_palette

MAX_APPROVAL_BYTES = 1024 * 1024
MAX_APPROVAL_RECORDS = 256
MAX_APPROVAL_STORE_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PACK_BYTES = 5 * 1024 * 1024
STYLE = "fixed-geographic-elevation-low-relief-v2"
HASH = re.compile(r"[0-9a-f]{64}\Z")
VIEWER_MODULES = ("map_tiles.py", "map_palette.py", "packed_map.py",
                  "map_terrain.py", "offline_map.py", "paint.py")
MAP_SOURCES = ("n810-map-next.py", "n810-map-rgb.py", "n810-map.py", "n810-walk-map.py")
ENTRY_FIELDS = {"version", "format", "artifact_id", "raw_manifest_sha256",
                "canonical_manifest_sha256", "semantic_identity", "files", "bytes",
                "coverage", "viewer", "membership"}


def canonical(value):
    """The exact v1 inventory/approval hash input; no trailing newline.

JSON uses sorted keys, compact separators, ASCII escaping, UTF-8 encoding, and
rejects non-finite numbers. Inventory is {basename:{bytes:int,sha256:64hex}};
it includes manifest.json with its RAW byte hash and every listed tile. Hashing
the raw manifest separately preserves formatting-sensitive artifact identity.
"""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


@dataclass(frozen=True)
class ApprovedProviderRef:
    version: int
    artifact_id: str
    entry_sha256: str
    initial_view: tuple

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1:
            raise ValueError("Unsupported approved provider reference")
        if (not isinstance(self.artifact_id, str) or not HASH.fullmatch(self.artifact_id)
                or not isinstance(self.entry_sha256, str) or not HASH.fullmatch(self.entry_sha256)):
            raise ValueError("Invalid approved provider identity")
        value = self.initial_view
        if (type(value) is not tuple or len(value) != 3
                or not _finite(value[0], -84.999999, 84.999999)
                or not _finite(value[1], -179.999999, 179.999999)
                or not _finite(value[2], .001, 2000)):
            raise ValueError("Invalid approved provider initial view")

    def to_mapping(self):
        return {"version": self.version, "artifact_id": self.artifact_id,
                "entry_sha256": self.entry_sha256,
                "initial_view": {"center": list(self.initial_view[:2]), "span": self.initial_view[2]}}

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, Mapping) or set(value) != {
                "version", "artifact_id", "entry_sha256", "initial_view"}:
            raise ValueError("Invalid approved provider reference fields")
        view = value["initial_view"]
        if (not isinstance(view, Mapping) or set(view) != {"center", "span"}
                or type(view["center"]) is not list or len(view["center"]) != 2):
            raise ValueError("Invalid approved provider initial view fields")
        return cls(value["version"], value["artifact_id"], value["entry_sha256"],
                   tuple(view["center"]) + (view["span"],))


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError("Duplicate JSON key")
        result[name] = value
    return result


def _json(data):
    def invalid(value):
        raise ValueError("Non-finite JSON constant")
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=invalid)
    except (TypeError, RecursionError, UnicodeError) as error:
        raise ValueError("Invalid provider JSON") from error


@contextmanager
def _directory(path, private=False):
    """Bind every directory component without following symlinks."""
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        info = os.fstat(fd)
        if private and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("Provider state directory must be private and owned")
        yield fd
    finally:
        os.close(fd)


def _read_at(fd, name, limit, private=False):
    if not isinstance(name, str) or not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("Invalid provider filename")
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(child, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.getuid())
                or before.st_mode & 0o022 or not 0 < before.st_size <= limit):
            raise ValueError("Unsafe or oversized provider file")
        if private and (before.st_uid != os.getuid() or before.st_mode & 0o077):
            raise ValueError("Provider metadata must be private and owned")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if (len(data) != before.st_size or len(data) > limit
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("Provider file changed while reading")
        return data


def _read_relative(root, relative, limit):
    parts = relative.split("/")
    if (relative.startswith("/") or "\\" in relative
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError("Invalid viewer source path")
    with _directory(root.joinpath(*parts[:-1])) as fd:
        return _read_at(fd, parts[-1], limit)


def _member(library_root, artifact_id):
    """Current import membership is mandatory; historic approval is not enough."""
    with _directory(library_root, private=True) as fd:
        raw = _read_at(fd, "library.json", 65536, private=True)
    value = _json(raw)
    if (not isinstance(value, dict) or set(value) != {"version", "artifacts"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["artifacts"], list) or len(value["artifacts"]) > 64
            or any(not isinstance(item, str) or not HASH.fullmatch(item) for item in value["artifacts"])
            or len(set(value["artifacts"])) != len(value["artifacts"])):
        raise ValueError("Invalid imported map index")
    if artifact_id not in value["artifacts"]:
        raise ValueError("Map artifact is not imported")
    return digest(raw)



class BoundArchive(map_tiles.Archive):
    """Same reviewed Archive validation/decoder, with its optional safe reader.

    Required upstream interface: Archive(..., reader=None). The reader must be
    called for manifest and every tile disk read; no decoder is copied here.
    The caller must close this archive when its provider is replaced or closed.
    """
    def __init__(self, root, hot_tiles=24):
        self._directory_reader = map_tiles.BoundPackReader(root)
        try:
            super().__init__(root, hot_tiles=hot_tiles, reader=self._directory_reader)
        except BaseException:
            self._directory_reader.close()
            raise

    def close(self):
        super().close()


def _scan(library_root, artifact_id):
    path = library_root / "artifacts" / artifact_id
    archive = BoundArchive(path, hot_tiles=1)
    try:
        raw = archive._directory_reader.read("manifest.json", MAX_MANIFEST_BYTES)
        if _json(raw) != archive.manifest:
            raise ValueError("Manifest changed during provider validation")
        inventory = {"manifest.json": {"bytes": len(raw), "sha256": digest(raw)}}
        total = len(raw)
        for level in archive.levels:
            for key, item in level["tiles"].items():
                data = archive._directory_reader.read(item["file"], 65536)
                if len(data) != item["bytes"] or digest(data) != item["sha256"]:
                    raise ValueError("Provider tile checksum differs")
                x, y = map(int, key.split(","))
                archive._load(level, (x, y), lambda: False)
                inventory[item["file"]] = {"bytes": len(data), "sha256": digest(data)}
                total += len(data)
                if total > MAX_PACK_BYTES:
                    raise ValueError("Provider pack exceeds size limit")
        if set(archive._directory_reader.names()) != set(inventory):
            raise ValueError("Provider pack has unlisted files")
        if digest(canonical(inventory)) != artifact_id:
            raise ValueError("Artifact content address does not match its bytes")
        with _directory(path) as current:
            opened, now = os.fstat(archive._directory_reader.fd), os.fstat(current)
            if (opened.st_dev, opened.st_ino) != (now.st_dev, now.st_ino):
                raise ValueError("Artifact directory was replaced during verification")
        coverage = [{key: level[key] for key in
                     ("id", "center", "span", "width", "height", "bbox", "spacing_m")}
                    for level in archive.levels]
        evidence = dict(artifact_id=artifact_id, raw_manifest_sha256=digest(raw),
                        canonical_manifest_sha256=digest(canonical(archive.manifest)),
                        semantic_identity=archive.manifest["identity"],
                        files=inventory, bytes=total, coverage=coverage)
        archive.clear_hot()
        return archive, evidence
    except BaseException:
        archive.close()
        raise


def _viewer(manifest, viewer_root):
    """Bind the selected-provider reader, not the default built-in renderer.

    Runtime's selected-provider contract executes Viewport from the admitted
    vendor/packet-console/n810-map-next.py, compiling the same bytes verified
    against viewer.sources. The unchanged default vendor/packet-console helper is
    outside this provider contract; no ambient source/map overrides are accepted.
    """
    modules = {}
    for name in VIEWER_MODULES:
        raw = _read_relative(viewer_root, name, 2 * 1024 * 1024)
        modules[name] = {"bytes": len(raw), "sha256": digest(raw)}
    # The implementation executing this call must match the claimed viewer.
    for module, name in ((map_tiles, "map_tiles.py"), (map_palette, "map_palette.py")):
        source = Path(module.__file__)
        with _directory(source.parent) as fd:
            raw = _read_at(fd, source.name, 2 * 1024 * 1024)
        if digest(raw) != modules[name]["sha256"]:
            raise ValueError("Executing map module differs from the supplied viewer root")
    palette = manifest["palette"]
    if (manifest["style"] != STYLE or palette["version"] != map_palette.PALETTE_VERSION
            or palette["breakpoints"] != json.loads(json.dumps(map_palette.BREAKPOINTS))
            or palette["sha256"] != modules["map_palette.py"]["sha256"]):
        raise ValueError("Map pack palette differs from the executing viewer")
    packet = viewer_root / "vendor" / "packet-console"
    with _directory(packet / "maps") as fd:
        names = sorted(os.listdir(fd))
        if not 1 <= len(names) <= 124:
            raise ValueError("Executing map source catalog exceeds bound")
        for name in names:
            if not stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                raise ValueError("Executing map source catalog contains non-files")
    expected = set(MAP_SOURCES) | {"maps/" + name for name in names}
    declared = {item["file"]: item["sha256"] for item in manifest["sources"]}
    if set(declared) != expected:
        raise ValueError("Map pack source inventory differs from the executing viewer")
    sources = {}
    for name in sorted(expected):
        raw = _read_relative(packet, name, 64 * 1024 * 1024)
        checksum = digest(raw)
        if checksum != declared[name]:
            raise ValueError("Map pack source differs from executing viewer: " + name)
        sources[name] = {"bytes": len(raw), "sha256": checksum}
    identity = dict(sources=manifest["sources"], palette=palette,
                    center=manifest["levels"][0]["center"], span=manifest["levels"][0]["span"],
                    widths=[level["width"] for level in manifest["levels"]],
                    terrain=True, roads=True)
    if digest(json.dumps(identity, sort_keys=True).encode()) != manifest["identity"]:
        raise ValueError("Map pack semantic input identity differs")
    value = {"layout": "installed-selected-packet-v2", "modules": modules, "sources": sources}
    return dict(value, sha256=digest(canonical(value)))


@contextmanager
def _approval_lock(library_root):
    with _directory(library_root, private=True) as fd:
        child = os.open("approved-provider.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                        | os.O_NONBLOCK, 0o600, dir_fd=fd)
    try:
        info = os.fstat(child)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe approved provider publication lock")
        try:
            fcntl.flock(child, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Approved provider publication is busy") from error
        yield
    finally:
        os.close(child)


def _approval_capacity(fd, incoming_bytes):
    count = total = 0
    scanned = 0
    removed_temporary = False
    with os.scandir(fd) as entries:
        for entry in entries:
            scanned += 1
            if scanned > MAX_APPROVAL_RECORDS + 128:
                raise ValueError("Approved provider directory exceeds enumeration bound")
            if re.fullmatch(r"\.approval-[0-9a-f]{32}", entry.name):
                info = entry.stat(follow_symlinks=False)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o077
                        or not 0 <= info.st_size <= MAX_APPROVAL_BYTES):
                    raise ValueError("Unsafe unpublished provider temporary file")
                os.unlink(entry.name, dir_fd=fd)
                removed_temporary = True
                continue
            count += 1
            if count > MAX_APPROVAL_RECORDS:
                raise ValueError("Approved provider record capacity reached")
            if not re.fullmatch(r"[0-9a-f]{64}\.json", entry.name):
                raise ValueError("Unexpected approved provider storage entry")
            info = entry.stat(follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or not 0 < info.st_size <= MAX_APPROVAL_BYTES):
                raise ValueError("Unsafe approved provider storage entry")
            total += info.st_size
            if total > MAX_APPROVAL_STORE_BYTES:
                raise ValueError("Approved provider storage capacity reached")
    if removed_temporary:
        os.fsync(fd)
    if count >= MAX_APPROVAL_RECORDS or total + incoming_bytes > MAX_APPROVAL_STORE_BYTES:
        raise ValueError("Approved provider storage capacity reached")


def _publish_entry(library_root, entry):
    with _approval_lock(library_root):
        return _publish_locked_entry(library_root, entry)


def _publish_locked_entry(library_root, entry):
    data = canonical(entry)
    if len(data) > MAX_APPROVAL_BYTES:
        raise ValueError("Approved provider record exceeds size limit")
    checksum = digest(data)
    with _directory(library_root, private=True) as root:
        try:
            os.mkdir("approved-providers", mode=0o700, dir_fd=root)
            os.fsync(root)
        except FileExistsError:
            pass
    directory = library_root / "approved-providers"
    with _directory(directory, private=True) as fd:
        name = checksum + ".json"
        try:
            existing = _read_at(fd, name, MAX_APPROVAL_BYTES, private=True)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != data:
                raise ValueError("Existing approved provider record differs")
            # The previous publication may have linked successfully but failed
            # its directory fsync. Retry must finish that durability step.
            os.fsync(fd)
            return checksum
        _approval_capacity(fd, len(data))
        # Link publication is atomic and refuses to replace an existing record.
        temporary = ".approval-" + os.urandom(16).hex()
        child = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=fd)
        try:
            with os.fdopen(child, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            except FileExistsError:
                if _read_at(fd, name, MAX_APPROVAL_BYTES, private=True) != data:
                    raise ValueError("Approved provider publication conflict")
            os.fsync(fd)
        finally:
            os.unlink(temporary, dir_fd=fd)
    return checksum


def _validate_entry(entry):
    if (not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS
            or type(entry["version"]) is not int or entry["version"] != 2
            or entry["format"] != STYLE):
        raise ValueError("Unsupported approved provider record schema")
    for key in ("artifact_id", "raw_manifest_sha256", "canonical_manifest_sha256",
                "semantic_identity"):
        if not isinstance(entry[key], str) or not HASH.fullmatch(entry[key]):
            raise ValueError("Invalid approved provider record identity")
    if (not isinstance(entry["files"], dict) or not 2 <= len(entry["files"]) <= 1025
            or "manifest.json" not in entry["files"]):
        raise ValueError("Invalid approved provider file inventory")
    total = 0
    for name, item in entry["files"].items():
        if (not isinstance(name, str) or "/" in name or "\\" in name
                or name not in ("manifest.json",) and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.tile", name)
                or not isinstance(item, dict) or set(item) != {"bytes", "sha256"}
                or type(item["bytes"]) is not int or not 0 < item["bytes"] <= MAX_MANIFEST_BYTES
                or not isinstance(item["sha256"], str) or not HASH.fullmatch(item["sha256"])):
            raise ValueError("Invalid approved provider inventory member")
        if name != "manifest.json" and item["bytes"] > 65536:
            raise ValueError("Approved provider tile exceeds size bound")
        total += item["bytes"]
    if (type(entry["bytes"]) is not int or total != entry["bytes"] or total > MAX_PACK_BYTES
            or digest(canonical(entry["files"])) != entry["artifact_id"]
            or entry["files"]["manifest.json"]["sha256"] != entry["raw_manifest_sha256"]):
        raise ValueError("Approved provider inventory identity differs")
    coverage = entry["coverage"]
    if not isinstance(coverage, list) or not 1 <= len(coverage) <= 3:
        raise ValueError("Invalid approved provider coverage")
    seen = set()
    for level in coverage:
        if (not isinstance(level, dict) or set(level) != {
                "id", "center", "span", "width", "height", "bbox", "spacing_m"}
                or not isinstance(level["id"], str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", level["id"])
                or level["id"] in seen
                or type(level["width"]) is not int or not 2 <= level["width"] <= 1024
                or type(level["height"]) is not int or not 2 <= level["height"] <= 512
                or not _finite(level["span"], .001, 2000)
                or type(level["center"]) is not list or len(level["center"]) != 2
                or not _finite(level["center"][0], -84.999999, 84.999999)
                or not _finite(level["center"][1], -179.999999, 179.999999)
                or type(level["bbox"]) is not list or len(level["bbox"]) != 4
                or any(not _finite(value, -180, 180) for value in level["bbox"])
                or not _finite(level["spacing_m"], 0, 80000)):
            raise ValueError("Invalid approved provider coverage level")
        seen.add(level["id"])
    viewer = entry["viewer"]
    if (not isinstance(viewer, dict) or set(viewer) != {"layout", "modules", "sources", "sha256"}
            or viewer["layout"] != "installed-selected-packet-v2"
            or not isinstance(viewer["modules"], dict) or set(viewer["modules"]) != set(VIEWER_MODULES)
            or not isinstance(viewer["sources"], dict) or not 5 <= len(viewer["sources"]) <= 128
            or not set(MAP_SOURCES).issubset(viewer["sources"])):
        raise ValueError("Invalid approved provider viewer fingerprint")
    for name, item in list(viewer["modules"].items()) + list(viewer["sources"].items()):
        if (not isinstance(name, str) or "\\" in name or name.startswith("/")
                or any(part in ("", ".", "..") for part in name.split("/"))
                or not isinstance(item, dict) or set(item) != {"bytes", "sha256"}
                or type(item["bytes"]) is not int or not 0 < item["bytes"] <= 64 * 1024 * 1024
                or not isinstance(item["sha256"], str) or not HASH.fullmatch(item["sha256"])):
            raise ValueError("Invalid approved provider viewer source")
    if viewer["sha256"] != digest(canonical({key: viewer[key] for key in ("layout", "modules", "sources")})):
        raise ValueError("Approved provider viewer fingerprint differs")
    membership = entry["membership"]
    if (not isinstance(membership, dict) or set(membership) != {"artifact_id", "imported"}
            or membership["artifact_id"] != entry["artifact_id"]
            or membership["imported"] is not True):
        raise ValueError("Invalid approved provider membership assertion")


def _initial(entry):
    first = entry["coverage"][0]
    return tuple(first["center"]) + (first["span"],)


def admit_provider(library_root, artifact_id, viewer_root):
    """Fully verify an imported pack and publish its immutable approval record."""
    if not isinstance(artifact_id, str) or not HASH.fullmatch(artifact_id):
        raise ValueError("Invalid map artifact identity")
    library_root = Path(os.path.abspath(library_root))
    viewer_root = Path(os.path.abspath(viewer_root))
    _member(library_root, artifact_id)
    archive, evidence = _scan(library_root, artifact_id)
    try:
        viewer = _viewer(archive.manifest, viewer_root)
        entry = dict(version=2, format=STYLE, **evidence, viewer=viewer,
                     membership={"artifact_id": artifact_id, "imported": True})
        _validate_entry(entry)
        # Recheck membership after the expensive verification, without requiring
        # unrelated imports to change this artifact's stable approval identity.
        _member(library_root, artifact_id)
        checksum = _publish_entry(library_root, entry)
        return ApprovedProviderRef(1, artifact_id, checksum, _initial(entry))
    finally:
        archive.close()


def open_provider(library_root, ref, viewer_root):
    """Reverify an approval and return (safe Archive, entry) to a render worker."""
    if not isinstance(ref, ApprovedProviderRef):
        ref = ApprovedProviderRef.from_mapping(ref)
    library_root = Path(os.path.abspath(library_root))
    viewer_root = Path(os.path.abspath(viewer_root))
    _member(library_root, ref.artifact_id)
    with _directory(library_root / "approved-providers", private=True) as fd:
        raw = _read_at(fd, ref.entry_sha256 + ".json", MAX_APPROVAL_BYTES, private=True)
    if digest(raw) != ref.entry_sha256:
        raise ValueError("Approved provider record checksum differs")
    entry = _json(raw)
    _validate_entry(entry)
    if canonical(entry) != raw or entry["artifact_id"] != ref.artifact_id:
        raise ValueError("Approved provider record is not canonical or names another artifact")
    archive, evidence = _scan(library_root, ref.artifact_id)
    try:
        if any(entry[key] != value for key, value in evidence.items()):
            raise ValueError("Approved provider evidence differs from current artifact bytes")
        if _initial(entry) != ref.initial_view:
            raise ValueError("Approved provider initial view was substituted")
        if _viewer(archive.manifest, viewer_root) != entry["viewer"]:
            raise ValueError("Executing viewer changed after provider admission")
        _member(library_root, ref.artifact_id)
        archive.limit = 24
        archive.entry = entry
        archive.artifact_id = ref.artifact_id
        return archive, entry
    except BaseException:
        archive.close()
        raise
