#!/usr/bin/env python3
"""Check the exact local upload tree without printing possible secrets."""
from pathlib import Path
import hashlib
import gzip
import zlib
import json
import os
import re
import subprocess
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SKIP_DIRS = {".git", ".venv-docs", "site", "__pycache__"}
DENIED_DIRS = {"artifacts", "backups", "inputs", "audit", "kernel", "outputs"}
DENIED_SUFFIXES = {".nand", ".img", ".ext4", ".jffs2", ".ko", ".elf", ".ppm", ".iso", ".tar", ".gz", ".xz", ".zip", ".bin", ".data", ".pem", ".p12", ".pfx", ".key", ".sqlite", ".db"}
SECRETS = {
    "private key": re.compile(rb"-----BEGIN (?:OPENSSH|RSA|DSA) PRIVATE KEY-----"),
    "WPA key": re.compile(rb"(?m)^\s*psk\s*=\s*(?:\"[^\"\r\n]+\"|[0-9a-fA-F]{64})\s*$"),
    "service token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})"),
    "local home path": re.compile(rb"/Users/[A-Za-z0-9._-]+/"),
}
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}


def files():
    if (ROOT / ".git").exists():
        names = [raw.decode() for raw in subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT).split(b"\0") if raw]
        paths = (ROOT / name for name in names)
    else:
        paths = (path for path in ROOT.rglob("*")
                 if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts))
    for path in paths:
        if path.is_symlink():
            yield path, "symlink"
        elif path.is_file():
            yield path, "file"


def main():
    errors = []
    excluded = [value.casefold().encode() for value in os.environ.get("PUBLICATION_REJECT_TEXT", "").split("|") if value]
    if (ROOT / ".git").exists() and subprocess.check_output(
            ["git", "diff", "--name-only", "-z"], cwd=ROOT):
        errors.append("tracked files have unstaged changes; stage or discard them before checking")
    if (ROOT / ".git").exists() and subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT):
        errors.append("untracked files remain; review and stage or exclude them")
    release_assets = json.loads((ROOT / "tools/release-assets.json").read_text())["files"]
    reviews = {name.removeprefix("docs/"): dict(entry, reviewed=True, provenance="Reviewed release asset")
               for name, entry in release_assets.items() if entry["kind"] == "media"}
    reviewed = set()
    data_reviews = {name: dict(entry, reviewed=True, provenance="Reviewed authored asset")
                    for name, entry in release_assets.items() if entry["kind"] == "authored-data"}
    seen_data = set()
    for path, kind in files():
        name = path.relative_to(ROOT).as_posix()
        if kind == "symlink":
            errors.append(f"{name}: symlink requires separate review")
            continue
        map_output = (
            name.startswith(('pocket/data/', 'pocket/shell/map-assets/accepted-preview/',
                             'pocket/shell/data/elevation-',
                             'pocket/shell/vendor/packet-console/map-sources/',
                             'pocket/shell/vendor/packet-console/maps/',
                             'pocket/shell/vendor/map-library-resources/packet-console/maps/'))
            or name.startswith('pocket/shell/data/') and ('etopo' in name or '3dep' in name)
        )
        if map_output and not name.endswith('README.md'):
            errors.append(f"{name}: map downloads and generated packs must remain local build products")
        if path.parts[len(ROOT.parts)] in DENIED_DIRS:
            errors.append(f"{name}: private/generated directory")
        if any(part in {".private", "node_modules"} for part in path.relative_to(ROOT).parts):
            errors.append(f"{name}: generated credentials or dependency directory")
        data = path.read_bytes()
        approved_data = False
        if name in data_reviews:
            entry = data_reviews[name]
            approved_data = entry.get("reviewed") and entry.get("provenance") and entry.get("sha256") == hashlib.sha256(data).hexdigest()
            if not approved_data:
                errors.append(f"{name}: data needs hash-matched review")
            seen_data.add(name)
        if path.suffix.lower() in DENIED_SUFFIXES:
            if not (approved_data and path.suffix.lower() == ".gz"):
                errors.append(f"{name}: binary/device payload extension")
        scan_data = data
        if approved_data and path.suffix.lower() == ".gz":
            try: scan_data = gzip.decompress(data)
            except (OSError, EOFError): errors.append(f"{name}: invalid reviewed gzip data")
        elif approved_data and data.startswith(b"CWAMB01\0"):
            try:
                _, width, height, count = struct.unpack_from('<8sHHH', data)
                assert (width, height) == (64, 32) and 1 <= count <= 256
                start = 14 + count * 4
                offsets = struct.unpack_from('<2049I', data, start)
                base = start + 2049 * 4
                assert offsets[0] == 0 and offsets[-1] == len(data) - base
                chunks = [zlib.decompress(data[base+a:base+b]) for a, b in zip(offsets, offsets[1:])]
                assert all(len(chunk) == (i // 64 + 1) * (i % 64 + 1) for i, chunk in enumerate(chunks))
                scan_data = b''.join(chunks)
            except (ValueError, AssertionError, struct.error, zlib.error):
                errors.append(f"{name}: invalid ambient lookup table")
        elif approved_data and path.suffix.lower() in {".zlib", ".n8t", ".n8w", ".n8b"}:
            try: scan_data = zlib.decompress(data if path.suffix == ".zlib" else data[4:])
            except zlib.error: errors.append(f"{name}: invalid reviewed compressed data")
        if any(value in scan_data.lower() for value in excluded):
            errors.append(f"{name}: excluded private text; inspect locally")
        if data[:4] == b"\x7fELF" or data.startswith(b"NOLO img"):
            errors.append(f"{name}: executable/device image")
        for label, pattern in SECRETS.items():
            if pattern.search(scan_data):
                errors.append(f"{name}: possible {label}; inspect privately")
        if path.is_relative_to(DOCS) and path.suffix.lower() in MEDIA:
            key = path.relative_to(DOCS).as_posix()
            entry = reviews.get(key, {})
            if not entry.get("reviewed") or entry.get("sha256") != hashlib.sha256(data).hexdigest() or not entry.get("provenance"):
                errors.append(f"{name}: media needs hash-matched review")
            reviewed.add(key)
    for key in data_reviews.keys() - seen_data:
        errors.append(f"{key}: data review entry has no tracked file")
    for key in reviews.keys() - reviewed:
        errors.append(f"{key}: review entry has no media")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Publication input check passed for the local tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
