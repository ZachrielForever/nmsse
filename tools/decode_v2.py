#!/usr/bin/env python3
"""decode_v2.py -- LZ4 block container codec for current-format .hg saves.

Container (per nmstoolkit documentation, to be verified against live files):
  repeated blocks: [u32 magic 0xFEEDA1E5][u32 comp_size][u32 uncomp_size]
                   [u32 zero pad][lz4 block data...]

Usage:
  python decode_v2.py test FILE       # parse container, decompress, summarize
  python decode_v2.py decode FILE OUT # write decompressed JSON
  python decode_v2.py encode IN OUT   # recompress JSON back into container
"""
import json
import struct
import sys
from pathlib import Path

import lz4.block

MAGIC = 0xFEEDA1E5
BLOCK_UNCOMP = 0x80000  # 512 KB per docs


def parse_blocks(data):
    blocks, pos = [], 0
    while pos + 16 <= len(data):
        magic, comp, uncomp, pad = struct.unpack_from("<IIII", data, pos)
        if magic != MAGIC:
            raise ValueError(f"bad magic {magic:#x} at block {len(blocks)} "
                             f"(offset {pos})")
        raw = data[pos + 16:pos + 16 + comp]
        if len(raw) != comp:
            raise ValueError(f"truncated block at offset {pos}")
        blocks.append((raw, uncomp))
        pos += 16 + comp
    if pos != len(data):
        raise ValueError(f"{len(data) - pos} trailing bytes after last block")
    return blocks


def decompress_file(path):
    blocks = parse_blocks(Path(path).expanduser().read_bytes())
    payload = b"".join(
        lz4.block.decompress(raw, uncompressed_size=uncomp)
        for raw, uncomp in blocks)
    return payload, blocks


def compress_to_container(payload):
    out = bytearray()
    for off in range(0, len(payload), BLOCK_UNCOMP):
        chunk = payload[off:off + BLOCK_UNCOMP]
        comp = lz4.block.compress(chunk, store_size=False,
                                  mode="default")
        out += struct.pack("<IIII", MAGIC, len(comp), len(chunk), 0)
        out += comp
    return bytes(out)


def test(path):
    payload, blocks = decompress_file(path)
    sizes = [(len(r), u) for r, u in blocks]
    print(f"blocks: {len(blocks)}, (comp, uncomp) per block: {sizes[:6]}")
    print(f"decompressed: {len(payload):,} bytes")
    print(f"tail: {payload[-8:]!r}")
    body = payload.rstrip(b"\x00")
    try:
        docs = json.loads(body.decode("utf-8"))
        keys = list(docs.keys())[:10] if isinstance(docs, dict) else type(docs)
        print(f"JSON: VALID. top keys: {keys}")
        print(f"first 200 chars: {body[:200].decode('utf-8', 'replace')}")
    except Exception as e:
        print(f"JSON parse failed: {e}")
        print(f"first 100 bytes: {payload[:100]!r}")


def decode(path, out):
    payload, _ = decompress_file(path)
    Path(out).write_bytes(payload.rstrip(b"\x00"))
    print(f"wrote {out} ({len(payload):,} bytes, NUL stripped)")


def encode(inpath, outpath):
    body = Path(inpath).expanduser().read_bytes()
    blob = compress_to_container(body + b"\x00")  # restore NUL terminator
    Path(outpath).write_bytes(blob)
    # self-check: roundtrip must be byte-exact
    payload, _ = decompress_file(outpath)
    assert payload.rstrip(b"\x00") == body, "roundtrip mismatch!"
    print(f"wrote {outpath} ({len(blob):,} bytes), roundtrip verified")


def main():
    m = sys.argv[1]
    if m == "test":
        test(sys.argv[2])
    elif m == "decode":
        decode(sys.argv[2], sys.argv[3])
    elif m == "encode":
        encode(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()