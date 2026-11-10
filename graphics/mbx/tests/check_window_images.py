# SPDX-License-Identifier: MIT
"""Host-side residency admission, sampler encoding and subset-cache checks."""
import os
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mbx-window-") as tmp:
    for name in ("window_images", "window_resources", "window_encoder", "texture_subset", "texture_resident"):
        sources = [root / "tests" / ("test_" + name + ".c")]
        if name == "window_encoder":
            sources += [root / "common" / ("mbx_vgp_" + part + ".c") for part in ("wire", "draw", "transform", "isa")]
        binary = str(Path(tmp) / name)
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-variable", "-Wno-misleading-indentation", "-fsanitize=address,undefined",
            "-I" + str(root / "common"), *map(str, sources), "-o", binary], check=True)
        subprocess.run([binary], check=True)
