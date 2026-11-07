#!/usr/bin/env python3
"""Assemble an N810 MBR image while proving partition 1 is unchanged."""
import argparse, hashlib, os, struct

SECTOR = 512
P1_START, P1_SECTORS = 16, 1_966_064
P2_START, P2_SECTORS = 1_966_080, 1_966_080
IMAGE_SECTORS = 3_932_160

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--partition1", required=True)
    p.add_argument("--partition2", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    if a.output.startswith("/dev/"):
        p.error("device output is forbidden")
    expected = {a.partition1: P1_SECTORS * SECTOR, a.partition2: P2_SECTORS * SECTOR}
    for path, size in expected.items():
        if os.path.getsize(path) != size:
            p.error(f"{path}: expected {size} bytes")
    if os.path.exists(a.output):
        p.error(f"refusing to overwrite {a.output}")
    p1_hash = digest(a.partition1)
    mbr = bytearray(SECTOR)
    mbr[440:444] = bytes.fromhex("be23308f")
    def entry(offset, ptype, start, sectors):
        mbr[offset:offset+16] = struct.pack("<B3sB3sII", 0, b"\0\0\0", ptype, b"\0\0\0", start, sectors)
    entry(446, 0x0B, P1_START, P1_SECTORS)
    entry(462, 0x83, P2_START, P2_SECTORS)
    mbr[510:512] = b"\x55\xaa"
    with open(a.output, "xb") as out:
        out.truncate(IMAGE_SECTORS * SECTOR)
        out.seek(0); out.write(mbr)
        out.seek(P1_START * SECTOR)
        with open(a.partition1, "rb") as src:
            for block in iter(lambda: src.read(1024 * 1024), b""): out.write(block)
        out.seek(P2_START * SECTOR)
        with open(a.partition2, "rb") as src:
            for block in iter(lambda: src.read(1024 * 1024), b""): out.write(block)
    with open(a.output, "rb") as image:
        image.seek(P1_START * SECTOR)
        h = hashlib.sha256()
        left = P1_SECTORS * SECTOR
        while left:
            block = image.read(min(left, 1024 * 1024)); h.update(block); left -= len(block)
    if h.hexdigest() != p1_hash:
        os.unlink(a.output)
        raise SystemExit("partition 1 preservation check failed")
    with open(a.output + ".sha256", "w") as f:
        f.write(f"{digest(a.output)}  {os.path.basename(a.output)}\n")
    print(f"Built full image; preserved partition 1 sha256={p1_hash}")

if __name__ == "__main__": main()
