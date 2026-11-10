"""Layered .hg decode/encode with honest probe reporting and roundtrip checks.

Format families, learned by triage on live saves:
  - LZ4 container (save5/save6, current game): repeated
    [u32 magic 0xFEEDA1E5][u32 comp size][u32 uncomp size][u32 zero pad][block],
    chunked at 0x80000 uncompressed; payload is JSON + trailing NULs.
    Re-encoded as literal-only (store-mode) LZ4 blocks: valid, larger, portable.
  - raw JSON (older slots, accountdata): one or more JSON docs + NULs.
  - mf_* files: unknown binary format; detected and refused loudly.
"""
import gzip
import json
import struct
import zlib

MAGIC = 0xFEEDA1E5
MF_MAGIC = 0x16C93197          # mf_* files start with this; format unknown
BLOCK_UNCOMP = 0x80000

_JSON_DECODER = json.JSONDecoder()

class DecodeError(Exception):
    def __init__(self, report):
        super().__init__(report.get("failure", "decode failed"))
        self.report = report

def Path_read(path):
    with open(path, "rb") as f:
        return f.read()

def head_summary(data, n=32):
    bs = data[:n]
    ascii_ = "".join(chr(c) if 32 <= c < 127 else "." for c in bs)
    return bs.hex(), ascii_

def probe_file(path):
    data = Path_read(path)
    hx, ax = head_summary(data)
    return {"file": str(path), "size": len(data),
            "head_hex": hx, "head_ascii": ax}

# ----------------------------------------------- pure-python LZ4 block
def _lz4_decompress(src, uncompressed_size):
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
        if moff >= mlen:                 # non-overlapping: bulk slice copy
            dst += dst[start:start + mlen]
        else:                            # overlapping: byte-at-a-time
            for k in range(mlen):
                dst.append(dst[start + k])
    if len(dst) != uncompressed_size:
        raise ValueError(f"lz4 block produced {len(dst):,} bytes, "
                         f"header promised {uncompressed_size:,}")
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

def _lz4_compress_store(chunk):
    """Valid LZ4 block: one literal-only sequence covering the whole chunk."""
    return b"\xf0" + _lit_length_bytes(len(chunk)) + chunk

# -------------------------------------------------------- LZ4 container
def _parse_blocks(data):
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

def _lz4_decode_body(data, report):
    """LZ4 container bytes -> JSON docs. Raises on any structural fault."""
    blocks = _parse_blocks(data)
    report["container_blocks"] = len(blocks)
    report["block_sizes"] = [(len(r), u) for r, u in blocks][:8]
    report["notes"].append(
        f"LZ4 container: {len(blocks)} block(s), "
        f"sizes {[(len(r), u) for r, u in blocks]}")
    payload = b"".join(_lz4_decompress(raw, uncomp) for raw, uncomp in blocks)
    nuls = len(payload) - len(payload.rstrip(b"\x00"))
    report["suffix_nuls"] = nuls
    if nuls:
        report["notes"].append(f"{nuls} trailing NUL terminator byte(s)")
    text = payload.rstrip(b"\x00").decode("utf-8")
    return _parse_stream(text, report)

def _compress_container(body):
    out = bytearray()
    for off in range(0, len(body), BLOCK_UNCOMP):
        chunk = body[off:off + BLOCK_UNCOMP]
        comp = _lz4_compress_store(chunk)
        out += struct.pack("<IIII", MAGIC, len(comp), len(chunk), 0)
        out += comp
    return bytes(out)

# ------------------------------------------------------------- strategies
def _gzip_multi(payload):
    """Decompress possibly-concatenated gzip members."""
    out = b""
    pos = 0
    while pos < len(payload):
        dec = zlib.decompressobj(zlib.MAX_WBITS | 16)
        out += dec.decompress(payload[pos:])
        if not dec.eof:
            raise ValueError("truncated gzip member")
        if not dec.unused_data:
            break
        pos = len(payload) - len(dec.unused_data)
    return out

_STRATEGIES = [
    ("utf8-escaped", lambda p: p),
    ("identity", lambda p: p),
    ("gzip", lambda p: gzip.decompress(p)),
    ("gzip-multi", _gzip_multi),
    ("zlib", lambda p: zlib.decompress(p)),
    ("raw-deflate", lambda p: zlib.decompress(p, -15)),
]

# ------------------------------------------------------------ text tools
def _text_to_bytes(text, method):
    esc = "surrogateescape" if method == "utf8-escaped" else "strict"
    return text.encode("utf-8", esc)

def _bytes_to_text(raw, method):
    esc = "surrogateescape" if method == "utf8-escaped" else "strict"
    return raw.decode("utf-8", esc)

def _split_prefix(data, report):
    """Split a leading binary header (up to first b'{"') from JSON payload."""
    idx = data.find(b'{"')
    if 0 < idx < 4096:
        report["notes"].append(
            f"{idx}-byte binary header before JSON (hex: {data[:idx].hex()})")
        return data[:idx], data[idx:]
    return b"", data

def _strip_trailing_nuls(data, report):
    """NMS terminates save streams with NUL byte(s); count and remove."""
    nuls = len(data) - len(data.rstrip(b"\x00"))
    if nuls:
        report["suffix_nuls"] = nuls
        report["notes"].append(f"{nuls} trailing NUL terminator byte(s)")
        data = data[:-nuls]
    return data

def _parse_stream(text, report):
    """Parse possibly-concatenated JSON documents. Returns list of docs."""
    try:
        return [json.loads(text)]
    except json.JSONDecodeError as e:
        if "Extra data" not in str(e):
            raise
    docs = []
    idx, n = 0, len(text)
    while idx < n:
        while idx < n and text[idx] in " \t\r\n\x00":
            idx += 1
        if idx >= n:
            break
        obj, end = _JSON_DECODER.raw_decode(text, idx)
        docs.append(obj)
        idx = end
    report["notes"].append(f"stream contained {len(docs)} JSON documents")
    return docs

def _replace_binary_runs(text, report):
    """Swap raw non-UTF-8 byte runs (surrogates) for unique quoted tokens."""
    runs, out = {}, []
    i, n, run_id = 0, len(text), 0
    while i < n:
        o = ord(text[i])
        if 0xDC80 <= o <= 0xDCFF:          # surrogateescape stand-in byte
            j = i
            while j < n and 0xDC80 <= ord(text[j]) <= 0xDCFF:
                j += 1
            raw = bytes(ord(c) - 0xDC00 for c in text[i:j])
            token = f"\ue000{run_id}"
            runs[token] = raw
            out.append(f'"{token}"')
            run_id += 1
            i = j
        else:
            out.append(text[i])
            i += 1
    if len(runs) > 500:
        report["notes"].append(
            f"{len(runs)} binary runs is abnormally dense -- unrecognized "
            "variant; editing support is deferred")
    return "".join(out), runs

def _restore_binary_runs(text, runs):
    for token, raw in runs.items():
        text = text.replace(f'"{token}"',
                            raw.decode("utf-8", "surrogateescape"))
    return text

# ------------------------------------------------------------ core decode
def decode_file(path):
    """Return (docs, method, report) or raise DecodeError with report."""
    return _decode_bytes(Path_read(path), str(path))

def _decode_bytes(data, label):
    hx, ax = head_summary(data)
    report = {"file": label, "size": len(data),
             "head_hex": hx, "head_ascii": ax, "notes": [], "tries": []}

    first_magic = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0

    if first_magic == MAGIC:
        try:
            docs = _lz4_decode_body(data, report)
            report["strategy"] = "lz4-container"
            report["doc_count"] = len(docs)
            first = docs[0]
            report["top_keys"] = (list(first.keys())[:20]
                                  if isinstance(first, dict)
                                  else f"<{type(first).__name__}>")
            return docs, "lz4-container", report
        except Exception as e:
            report["tries"].append(f"lz4-container: {e.__class__.__name__}: {e}")

    if first_magic == MF_MAGIC:
        report["tries"].append(
            "mf-magic: this is an mf_* metadata file; its binary format "
            "is unknown and unsupported -- the paired save is what you edit")

    # ---- legacy raw-JSON path (older slots, accountdata) ----
    prefix, data = _split_prefix(data, report)
    report["prefix_bytes"] = prefix
    data = _strip_trailing_nuls(data, report)

    for name, fn in _STRATEGIES:
        try:
            raw = fn(data)
        except Exception as e:
            report["tries"].append(
                f"{name}: decompress failed ({e.__class__.__name__})")
            continue
        try:
            text = _bytes_to_text(raw, name)
        except UnicodeDecodeError as e:
            off = e.start
            lo, hi = max(0, off - 16), off + 16
            report["tries"].append(
                f"{name}: not UTF-8 (first bad byte at offset {off}, "
                f"context {raw[lo:hi].hex()})")
            continue

        runs = {}
        if name == "utf8-escaped":
            text, runs = _replace_binary_runs(text, report)
            report["bin_runs"] = runs

        try:
            docs = _parse_stream(text, report)
        except Exception as e:
            report["tries"].append(f"{name}: JSON parse failed: {e}")
            continue

        report["strategy"] = name
        report["doc_count"] = len(docs)
        first = docs[0]
        report["top_keys"] = (list(first.keys())[:20]
                              if isinstance(first, dict)
                              else f"<{type(first).__name__}>")
        return docs, name, report

    report["failure"] = "no strategy produced valid JSON"
    raise DecodeError(report)

# ------------------------------------------------------------ core encode
def encode_docs(docs, method, bin_runs=None, suffix_nuls=0):
    text = "".join(json.dumps(d, separators=(",", ":"), ensure_ascii=False)
                   for d in docs)
    if bin_runs:
        text = _restore_binary_runs(text, bin_runs)

    if method == "lz4-container":
        # faithful to observed format: JSON payload + NUL terminator(s)
        body = text.encode("utf-8") + b"\x00" * (suffix_nuls or 1)
        return _compress_container(body)

    return _text_to_bytes(text, method) + b"\x00" * suffix_nuls

def roundtrip_ok(docs, method, bin_runs=None, suffix_nuls=0):
    """Re-encode and re-decode; semantic equality must survive the loop."""
    try:
        blob = encode_docs(docs, method, bin_runs, suffix_nuls)
        back, _, _ = _decode_bytes(blob, "<roundtrip>")
        return back == docs
    except Exception:
        return False

# ------------------------------------------------------------ inspection
def inspect_report(path):
    """Full triage report for pasting back to a collaborator."""
    r = probe_file(path)
    r["lines"] = [f"file: {r['file']}",
                  f"size: {r['size']} bytes",
                  f"head hex: {r['head_hex']}",
                  f"head ascii: {r['head_ascii']}",
                  ""]
    try:
        docs, method, rep = decode_file(path)
        r["lines"] += [f"DECODE OK via strategy: {method}",
                       f"documents: {rep.get('doc_count')}",
                       f"top-level keys: {rep.get('top_keys')}"]
        if rep.get("container_blocks"):
            r["lines"] += [f"lz4 blocks: {rep['container_blocks']} "
                           f"sizes: {rep.get('block_sizes')}"]
        r["lines"] += [f"  {n}" for n in rep.get("notes", [])]
        r["decoded"] = True
    except DecodeError as e:
        r["lines"] += ["DECODE FAILED -- strategy log:"]
        r["lines"] += [f"  {t}" for t in e.report.get("tries", [])]
        if e.report.get("notes"):
            r["lines"] += ["notes:"] + [f"  {n}" for n in e.report["notes"]]
        r["decoded"] = False
    r["text"] = "\n".join(r["lines"])
    return r