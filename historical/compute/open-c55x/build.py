#!/usr/bin/env python3
"""Build the pinned open C55x binutils CVS snapshot in a NEW local directory.

Requires Linux, Python 3, a C compiler, make, flex, bison and CVS. Modern
config.sub/config.guess are supplied explicitly (e.g. Debian autotools-dev).
No network, installation, firmware, or physical-device operation is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import zipfile

SOURCE_SHA256 = "96f4cb5cdb63d047852166fb70137f1269f0766b699b024d3a2365a26b7527eb"
SOURCE_SIZE = 15999400
CFLAGS = ("-O2 -g -std=gnu89 -fcommon "
          "-Wno-error=implicit-function-declaration "
          "-Wno-error=incompatible-pointer-types")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--cvs", default="cvs")
    parser.add_argument("--config-sub", type=Path, required=True)
    parser.add_argument("--config-guess", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4, choices=range(1, 17))
    args = parser.parse_args()
    snapshot = args.snapshot.resolve()
    if snapshot.stat().st_size != SOURCE_SIZE:
        raise ValueError("snapshot size mismatch")
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("snapshot hash mismatch")
    cvs = shutil.which(args.cvs)
    if not cvs:
        raise ValueError("CVS executable not found")
    helpers = [args.config_sub.resolve(), args.config_guess.resolve()]
    for helper in helpers:
        if not helper.is_file():
            raise ValueError(f"missing host helper: {helper}")
    root = args.workspace.resolve()
    root.mkdir()  # Refuse to mix with existing source/builds.
    repo = root / "repository"
    with zipfile.ZipFile(snapshot) as archive:
        if sum(m.file_size for m in archive.infolist()) > 256 * 1024 * 1024:
            raise ValueError("unexpected snapshot expansion size")
        for member in archive.infolist():
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe archive path")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("unexpected symlink")
            if member.is_dir():
                continue
            destination = repo / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
            destination.chmod(mode & 0o777 or 0o644)

    def command(argv, log, cwd=root, env=None):
        with (root / log).open("w") as output:
            result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env,
                                    stdout=output, stderr=subprocess.STDOUT,
                                    timeout=600)
        if result.returncode:
            raise RuntimeError(f"command failed ({result.returncode}); see {root / log}")

    cvsroot = repo / "c55x-binutils"
    if not (cvsroot / "CVSROOT").exists():
        command([cvs, "-f", "-d", cvsroot, "init"], "cvs-init.log")
    command([cvs, "-f", "-d", cvsroot, "checkout", "-P", "-d", "source", "binutils"],
            "checkout.log")
    development = root / "source-dev"
    shutil.copytree(root / "source", development, ignore=shutil.ignore_patterns("CVS"))
    helper_hashes = {}
    for helper, name in zip(helpers, ("config.sub", "config.guess")):
        shutil.copy2(helper, development / name)
        helper_hashes[name] = hashlib.sha256(helper.read_bytes()).hexdigest()
    build = root / "build"
    build.mkdir()
    env = {**os.environ, "CFLAGS": CFLAGS}
    command(["sh", development / "configure", "--target=c55x", "--disable-nls",
             "--disable-werror", "--disable-shared", "--prefix=" + str(root / "install")],
            "configure.log", build, env)
    command(["make", f"-j{args.jobs}", "MAKEINFO=true", "all-binutils", "all-gas", "all-ld"],
            "build.log", build, env)
    versions = {}
    for name, rel in (("as", "gas/as-new"), ("objdump", "binutils/objdump"),
                      ("objcopy", "binutils/objcopy"), ("ld", "ld/ld-new")):
        versions[name] = subprocess.check_output([str(build / rel), "--version"],
                                                text=True, timeout=10).splitlines()[0]
    result = {"status": "BUILT", "source_sha256": SOURCE_SHA256,
              "target": "c55x", "cflags": CFLAGS, "host_helper_sha256": helper_hashes,
              "versions": versions, "hardware_execution": False}
    (root / "build-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
