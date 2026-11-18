"""Verify the shipped A/B runtime against its source commit without mounting the kit."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from ab_media import verify


def check(kit, debugfs):
    kit, manifest = verify(kit)
    slot = kit / "slot.ext4"
    repo = Path(__file__).resolve().parents[2]
    commit = manifest["source_commit"]
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("Invalid installer source commit")

    def read(image, path):
        return subprocess.check_output([debugfs, "-R", "cat " + path, str(image)], stderr=subprocess.DEVNULL)

    def source(path):
        return subprocess.check_output(["git", "show", commit + ":" + path], cwd=repo)

    kernel = json.loads((kit / "KERNEL-BUILD.json").read_text())
    patch = source("platform/kernel/n810-device-fixes.patch")
    if hashlib.sha256(patch).hexdigest() != kernel["device_patch_sha256"]:
        raise ValueError("Kernel device patch mismatch")
    scripts = {
        "/usr/local/lib/n810-pocket/native-template/owner_session.py": "platform/bootstrap/gpu_runtime/owner_session.py",
        "/usr/lib/n810-ab/etc/init.d/n810-audio": "platform/device/n810-audio.init",
        "/usr/local/sbin/n810-audio": "platform/scripts/n810-audio",
        "/usr/local/sbin/n810-bluetooth": "platform/scripts/n810-bluetooth",
        "/usr/local/sbin/n810-bluetooth-address": "platform/scripts/n810-bluetooth-address",
    }
    for target, original in scripts.items():
        if read(slot, target) != source(original):
            raise ValueError("Installed file differs from source: " + target)
    files = ["/usr/bin/amixer", "/usr/bin/aplay", "/usr/bin/arecord",
             "/lib/modules/" + kernel["release"] + "/kernel/sound/soc/ti/snd-soc-n810.ko"]
    doom = "/usr/local/share/pocket/shell/apps/doom-app/"
    files.extend(doom + name for name in ("build/bridge.so", "build/doom-engine", "vendor/freedoom-0.13.0/freedoom1.wad"))
    for path in files:
        stat = subprocess.check_output([debugfs, "-R", "stat " + path, str(slot)], stderr=subprocess.DEVNULL, text=True)
        if "Type: regular" not in stat or not re.search(r"\bSize:\s*[1-9]\d*", stat):
            raise ValueError("Missing or empty installed runtime: " + path)
    print(f"Verified kit checksums, kernel patch, {len(scripts)} installed source files and {len(files)} runtime dependencies for {commit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    parser.add_argument("--debugfs", default=shutil.which("debugfs") or "debugfs")
    args = parser.parse_args()
    check(args.kit, args.debugfs)
