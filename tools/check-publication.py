#!/usr/bin/env python3
"""Check the exact local upload tree without printing possible secrets."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
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
    if (ROOT / ".git").exists() and subprocess.check_output(
            ["git", "diff", "--name-only", "-z"], cwd=ROOT):
        errors.append("tracked files have unstaged changes; stage or discard them before checking")
    if (ROOT / ".git").exists() and subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT):
        errors.append("untracked files remain; review and stage or exclude them")
    reviews = json.loads((DOCS / "assets/screenshots/review.json").read_text())
    reviewed = set()
    for path, kind in files():
        name = path.relative_to(ROOT).as_posix()
        if kind == "symlink":
            errors.append(f"{name}: symlink requires separate review")
            continue
        if path.parts[len(ROOT.parts)] in DENIED_DIRS:
            errors.append(f"{name}: private/generated directory")
        if path.suffix.lower() in DENIED_SUFFIXES:
            errors.append(f"{name}: binary/device payload extension")
        data = path.read_bytes()
        if data[:4] == b"\x7fELF" or data.startswith(b"NOLO img"):
            errors.append(f"{name}: executable/device image")
        for label, pattern in SECRETS.items():
            if pattern.search(data):
                errors.append(f"{name}: possible {label}; inspect privately")
        if path.is_relative_to(DOCS) and path.suffix.lower() in MEDIA:
            key = path.relative_to(DOCS).as_posix()
            entry = reviews.get(key, {})
            if not entry.get("reviewed") or entry.get("sha256") != hashlib.sha256(data).hexdigest() or not entry.get("provenance"):
                errors.append(f"{name}: media needs hash-matched review")
            reviewed.add(key)
    for key in reviews.keys() - reviewed:
        errors.append(f"{key}: review entry has no media")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Publication input check passed for the local tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
