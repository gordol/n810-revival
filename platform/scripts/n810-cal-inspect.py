#!/usr/bin/env python3
"""Inspect Nokia CAL blocks in a raw MTD image without modifying it."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path


HEADER = struct.Struct("<4sBBH16sIII")
MAGIC = b"ConF"


def cal_crc32(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc & 0xFFFFFFFF


def scan(image: bytes) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    start = 0
    while True:
        offset = image.find(MAGIC, start)
        if offset < 0:
            return records
        start = offset + 1
        if offset + HEADER.size > len(image):
            continue
        raw_header = image[offset : offset + HEADER.size]
        magic, header_version, version, flags, raw_name, length, data_crc, header_crc = HEADER.unpack(raw_header)
        end = offset + HEADER.size + length
        if magic != MAGIC or header_version != 2 or end > len(image):
            continue
        payload = image[offset + HEADER.size : end]
        name = raw_name.split(b"\0", 1)[0].decode("ascii", "replace")
        records.append(
            {
                "offset": offset,
                "name": name,
                "version": version,
                "flags": flags,
                "length": length,
                "header_crc": header_crc,
                "header_crc_ok": cal_crc32(raw_header[:-4]) == header_crc,
                "data_crc": data_crc,
                "data_crc_ok": cal_crc32(payload) == data_crc,
                "payload": payload,
            }
        )


def pmm_summary(payload: bytes) -> dict[str, object] | None:
    if len(payload) != 0x600 or not payload.startswith(b"BME-PMM-BLOCK01"):
        return None
    active_mask = payload[16]
    elements = []
    for number in range(2, 32):
        pos = 0x200 + number * 16
        elem = payload[pos : pos + 12]
        if len(elem) != 12:
            break
        ident, flags, group, padding, field1, field2 = struct.unpack("<BBBBII", elem)
        if ident not in (0, 0xFF):
            elements.append(
                {
                    "element": number,
                    "id": f"0x{ident:02x}",
                    "flags": f"0x{flags:02x}",
                    "adc_group": group,
                    "field1": field1,
                    "field1_signed": struct.unpack("<i", struct.pack("<I", field1))[0],
                    "field2": field2,
                }
            )
    return {"active_group_mask": f"0x{active_mask:02x}", "group1_elements": elements}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()

    image = args.image.read_bytes()
    records = scan(image)
    if args.name:
        records = [record for record in records if record["name"] == args.name]
    printable = []
    for record in records:
        item = {key: value for key, value in record.items() if key != "payload"}
        summary = pmm_summary(record["payload"])
        if summary:
            item["pmm"] = summary
        printable.append(item)
    print(json.dumps(printable, indent=2))

    if args.extract:
        valid = [record for record in records if record["header_crc_ok"] and record["data_crc_ok"]]
        if len(valid) != 1:
            print(f"refusing extraction: expected one valid matching record, found {len(valid)}", file=sys.stderr)
            return 2
        args.extract.write_bytes(valid[0]["payload"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
