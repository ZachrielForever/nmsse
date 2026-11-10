#!/usr/bin/env python3
"""decode_v3.py -- dependency-free LZ4 block container codec for .hg saves.

Container: repeated [u32 magic 0xFEEDA1E5][u32 comp size][u32 uncomp size]
[u32 zero pad][lz4 block]. Uncompressed chunk size 0x80000 (512KB) per docs.
Encoding uses literal-only (store-mode) LZ4 blocks: valid, larger, portable.

Usage:
  python decode_v3.py test FILE
  python decode_v3.py decode FILE OUT
  python decode_v3.py encode IN OUT
"""
import json
import struct
import sys
from pathlib import Path

MAGIC = 0xFEEDA1E5
BLOCK_UNCOMP = 0x80000


# ------------------------------------------------ pure-python lz4 block
def lz4_block_decompress(src, uncompressed_size):
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = src[i]; i += 1
                lit_len += b
                if b != 255:
                    break
        dst += src[i:i + lit_len]
        i += lit_len
        if i >= n:
            break                        # last sequence: literals only
        moff = src[i] | (src[i + 1] << 8); i += 2
        mlen = (token & 0xF) + 4
        if (token & 0xF) == 15:
            while True:
                b = src[i]; i += 1
                mlen += b
                if b != 255:
                    break
        start = len(dst) - moff
        for k in range(mlen):            # byte-at-a-time: overlap-safe
            dst.append(dst[start + k])
    if len(dst) != uncompressed_size:
        print(f"warning: produced {len(dst):,} bytes, header promised "
              f"{uncompressed_size:,}", file=sys.stderr)
    return bytes(dst)


def _lit_length_bytes(total):
    """Extension bytes encoding a literal length (token nibble == 15)."""
    out = bytearray()
    rem = total - 15
    while rem >= 255:
        out.append(255)
        rem -= 255
    out.append(rem)
    return bytes(out)


def lz4_block_compress_store(chunk):
    """Valid LZ4 block: one literal-only sequence covering the whole chunk."""
    return b"\xf0" + _lit_length_bytes(len(chunk)) + chunk


# ------------------------------------------------------- container layer
def parse_blocks(data):
    blocks, pos = [], 0
    while pos + 16 <= len(data):
        magic, comp, uncomp, pad = struct.unpack_from("<IIII", data, pos)
        if magic != MAGIC:
            raise ValueError(f"bad magic {magic:#x} at block {len(blocks)} "
                             f"(offset {pos}) -- container theory bust")
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
    payload = b"".join(lz4_block_decompress(raw, uncomp)
                       for raw, uncomp in blocks)
    return payload, blocks


def compress_to_container(payload):
    out = bytearray()
    for off in range(0, len(payload), BLOCK_UNCOMP):
        chunk = payload[off:off + BLOCK_UNCOMP]
        comp = lz4_block_compress_store(chunk)
        out += struct.pack("<IIII", MAGIC, len(comp), len(chunk), 0)
        out += comp
    return bytes(out)


# ---------------------------------------------------------------- modes
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
    blob = compress_to_container(body + b"\x00")     # restore NUL terminator
    Path(outpath).write_bytes(blob)
    back, _ = decompress_file(outpath)               # roundtrip check
    assert back.rstrip(b"\x00") == body, "roundtrip mismatch!"
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