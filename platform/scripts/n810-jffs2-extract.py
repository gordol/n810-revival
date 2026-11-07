#!/usr/bin/env python3
import argparse
import collections
import ctypes
import ctypes.util
import os
import stat
import struct
import sys
import zlib

MAGIC = 0x1985
NODE_DIRENT = 0xE001
NODE_INODE = 0xE002

_lzo = None


def jffs_crc(data):
    # Linux crc32(0, ...) is the raw CRC-32 state, without zlib's
    # initial/final complement convention.
    return (zlib.crc32(data, 0xffffffff) ^ 0xffffffff) & 0xffffffff


def rtime_decompress(src, destlen):
    positions = [0] * 256
    out = bytearray()
    pos = 0
    while len(out) < destlen:
        value = src[pos]
        repeat = src[pos + 1]
        pos += 2
        out.append(value)
        back = positions[value]
        positions[value] = len(out)
        for _ in range(repeat):
            out.append(out[back])
            back += 1
    return bytes(out[:destlen])


def decompress(kind, src, destlen):
    global _lzo
    if kind == 0:
        return src
    if kind == 1:
        return b"\0" * destlen
    if kind == 2:
        return rtime_decompress(src, destlen)
    if kind == 6:
        return zlib.decompress(src)
    if kind == 7:
        if _lzo is None:
            library = ctypes.util.find_library("lzo2")
            if not library:
                for candidate in (
                    "/opt/homebrew/lib/liblzo2.dylib",
                    "/usr/local/lib/liblzo2.dylib",
                    "liblzo2.so.2",
                ):
                    if os.path.exists(candidate):
                        library = candidate
                        break
            if not library:
                raise RuntimeError("LZO2 library not found")
            _lzo = ctypes.CDLL(library)
            _lzo.lzo1x_decompress_safe.argtypes = [
                ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_size_t),
            ]
            _lzo.lzo1x_decompress_safe.restype = ctypes.c_int
        source = ctypes.create_string_buffer(src)
        target = ctypes.create_string_buffer(destlen)
        target_len = ctypes.c_size_t(destlen)
        rc = _lzo.lzo1x_decompress_safe(
            source, len(src), target, ctypes.byref(target_len))
        if rc != 0 or target_len.value != destlen:
            raise ValueError(f"LZO rc={rc} size={target_len.value}, expected={destlen}")
        return target.raw[:destlen]
    raise ValueError(f"unsupported compression {kind}")


def strip_oob(source, dest, page=2048, oob=64):
    with open(source, "rb") as src, open(dest, "wb") as dst:
        while True:
            data = src.read(page)
            if not data:
                break
            if len(data) != page:
                raise ValueError("short NAND data page")
            dst.write(data)
            if len(src.read(oob)) != oob:
                raise ValueError("short NAND OOB record")


def scan(image):
    data = open(image, "rb").read()
    dirents = {}
    inodes = collections.defaultdict(list)
    counts = collections.Counter()
    bad_crc = collections.Counter()
    unsupported = collections.Counter()
    off = 0
    limit = len(data) - 12
    while off <= limit:
        magic, nodetype, totlen, hdr_crc = struct.unpack_from("<HHII", data, off)
        if magic != MAGIC or totlen < 12 or off + totlen > len(data):
            off += 4
            continue
        if jffs_crc(data[off:off + 8]) != hdr_crc:
            bad_crc["header"] += 1
            off += 4
            continue
        counts[f"0x{nodetype:04x}"] += 1
        if nodetype == NODE_DIRENT and totlen >= 40:
            fields = struct.unpack_from("<HHIIIIII4BII", data, off)
            _, _, _, _, pino, version, ino, mctime, nsize, dtype, _, _, node_crc, name_crc = fields
            name = data[off + 40:off + 40 + nsize]
            if jffs_crc(data[off:off + 32]) != node_crc:
                bad_crc["dirent_node"] += 1
            elif jffs_crc(name) != name_crc:
                bad_crc["dirent_name"] += 1
            else:
                key = (pino, name)
                old = dirents.get(key)
                if old is None or version > old[0]:
                    dirents[key] = (version, ino, dtype, off)
        elif nodetype == NODE_INODE and totlen >= 68:
            vals = struct.unpack_from("<HHIIIIIHHIIIIIIIBBHII", data, off)
            (_, _, _, _, ino, version, mode, uid, gid, isize, atime, mtime,
             ctime, foffset, csize, dsize, compr, usercompr, flags,
             data_crc, node_crc) = vals
            payload = data[off + 68:off + 68 + csize]
            if jffs_crc(data[off:off + 60]) != node_crc:
                bad_crc["inode_node"] += 1
            elif compr != 1 and jffs_crc(payload) != data_crc:
                bad_crc["inode_data"] += 1
            else:
                inodes[ino].append({
                    "version": version, "mode": mode, "uid": uid, "gid": gid,
                    "isize": isize, "mtime": mtime, "offset": foffset,
                    "csize": csize, "dsize": dsize, "compr": compr,
                    "payload": payload, "physical": off,
                })
                if compr not in (0, 1, 2, 6, 7):
                    unsupported[compr] += 1
        off = (off + totlen + 3) & ~3
    return dirents, inodes, counts, bad_crc, unsupported


def live_paths(dirents):
    children = collections.defaultdict(list)
    for (pino, name), (_, ino, dtype, physical) in dirents.items():
        if ino:
            children[pino].append((name, ino, dtype, physical))
    paths = {1: [b""]}
    queue = collections.deque([1])
    seen_dirs = {1}
    entries = []
    while queue:
        pino = queue.popleft()
        for name, ino, dtype, physical in children[pino]:
            for parent in paths[pino]:
                path = parent + b"/" + name
                entries.append((path, ino, dtype, physical))
                paths.setdefault(ino, []).append(path)
            if dtype == 4 and ino not in seen_dirs:
                seen_dirs.add(ino)
                queue.append(ino)
    return entries


def reconstruct(nodes):
    latest = max(nodes, key=lambda n: (n["version"], n["physical"]))
    size = latest["isize"]
    out = bytearray(size)
    covered = bytearray(size)
    for node in sorted(nodes, key=lambda n: (n["version"], n["physical"]), reverse=True):
        start = min(node["offset"], size)
        end = min(node["offset"] + node["dsize"], size)
        if start >= end or all(covered[start:end]):
            continue
        chunk = decompress(node["compr"], node["payload"], node["dsize"])
        if len(chunk) != node["dsize"]:
            raise ValueError(f"decompressed {len(chunk)}, expected {node['dsize']}")
        for pos in range(start, end):
            if not covered[pos]:
                out[pos] = chunk[pos - node["offset"]]
                covered[pos] = 1
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--strip-to")
    ap.add_argument("--image", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--match", action="append", default=[])
    ap.add_argument("--extract-dir")
    args = ap.parse_args()
    if args.source:
        strip_oob(args.source, args.strip_to)
    dirents, inodes, counts, bad_crc, unsupported = scan(args.image)
    entries = live_paths(dirents)
    print(f"image_bytes={os.path.getsize(args.image)}")
    print(f"node_counts={dict(counts)}")
    print(f"valid_dirents={len(dirents)} inode_numbers={len(inodes)} live_paths={len(entries)}")
    print(f"bad_crc={dict(bad_crc)} unsupported_compression={dict(unsupported)}")
    matches = []
    needles = [x.lower().encode() for x in args.match]
    for path, ino, dtype, physical in sorted(entries):
        if args.list or any(n in path.lower() for n in needles):
            print(f"{ino:8d} type={dtype:2d} dirent@0x{physical:08x} {os.fsdecode(path)}")
        if needles and any(n in path.lower() for n in needles):
            matches.append((path, ino, dtype))
    if args.extract_dir:
        os.makedirs(args.extract_dir, exist_ok=True)
        for path, ino, dtype in matches:
            if dtype not in (8, 10):
                continue
            try:
                content = reconstruct(inodes[ino])
            except Exception as exc:
                print(f"ERROR {os.fsdecode(path)}: {exc}", file=sys.stderr)
                continue
            safe = path.lstrip(b"/").replace(b"/", b"__")
            target = os.path.join(args.extract_dir, os.fsdecode(safe))
            with open(target, "wb") as f:
                f.write(content)
            latest = max(inodes[ino], key=lambda n: (n["version"], n["physical"]))
            print(f"EXTRACT {target} size={len(content)} mode={latest['mode']:o} latest_version={latest['version']}")


if __name__ == "__main__":
    main()
