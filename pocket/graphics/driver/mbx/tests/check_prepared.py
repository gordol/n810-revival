# SPDX-License-Identifier: MIT
"""Prepared-command parity and lifetime checks; local compiler, no device IO."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mbx-prepared-") as tmp:
    binary = str(Path(tmp) / "test")
    subprocess.run([
        os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-variable", "-Wno-misleading-indentation",
        "-fsanitize=address,undefined", "-I" + str(root / "common"),
        str(root / "tests/test_prepared.c"),
        *(str(root / "common" / name) for name in (
            "mbx_vgp_wire.c", "mbx_vgp_draw.c", "mbx_vgp_transform.c", "mbx_vgp_isa.c")),
        "-o", binary,
    ], check=True)
    subprocess.run([binary], check=True)
    legacy = str(Path(tmp) / "legacy")
    subprocess.run([
        os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-variable", "-Wno-misleading-indentation",
        "-fsanitize=address,undefined", "-I" + str(root / "common"),
        str(root / "tests/test_legacy_replay.c"),
        *(str(root / "common" / name) for name in (
            "mbx_vgp_wire.c", "mbx_vgp_draw.c", "mbx_vgp_transform.c", "mbx_vgp_isa.c")),
        "-o", legacy,
    ], check=True)
    subprocess.run([legacy], check=True)
    compiled = str(Path(tmp) / "compiled")
    subprocess.run([
        os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-variable", "-Wno-misleading-indentation",
        "-fsanitize=address,undefined", "-I" + str(root / "common"),
        str(root / "tests/test_command_cache.c"),
        *(str(root / "common" / name) for name in (
            "mbx_vgp_wire.c", "mbx_vgp_draw.c", "mbx_vgp_transform.c", "mbx_vgp_isa.c")),
        "-o", compiled,
    ], check=True)
    subprocess.run([compiled], check=True)
    service = (root / "kernel/mbx_render_service.h").read_text()
    start = service.index("static int gpu_service_open(")
    end = service.index("static void gpu_service_free_storage(", start)
    (Path(tmp) / "service_open.inc").write_text(service[start:end])
    free_start = service.index("static void gpu_service_free_storage(")
    free_end = service.index("static int gpu_service_close(", free_start)
    retire_start = service.index("static int gpu_service_retire_prepared(")
    retire_end = service.index("/* Cumulative diagnostics;", retire_start)
    (Path(tmp) / "service_retire.inc").write_text(service[free_start:retire_end])
    opened = str(Path(tmp) / "service-open")
    subprocess.run([
        os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-fsanitize=address,undefined", "-I" + str(root / "common"), "-I" + tmp,
        str(root / "tests/test_service_open.c"),
        *(str(root / "common" / name) for name in (
            "mbx_vgp_wire.c", "mbx_vgp_draw.c", "mbx_vgp_transform.c", "mbx_vgp_isa.c")),
        "-Wno-unused-variable", "-Wno-misleading-indentation", "-o", opened,
    ], check=True)
    subprocess.run([opened], check=True)
