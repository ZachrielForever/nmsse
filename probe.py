#!/usr/bin/env python3
"""Standalone .hg anomaly scanner. Usage:
    python probe.py /path/to/save/folder
Prints a per-file census of binary anomalies so the real framing
rule can be derived from data instead of guesses.
"""
import json
import sys
from pathlib import Path

_CONTROL_OK = "\t\n\r"


def is_suspicious(ch):
    o = ord(ch)
    # raw control chars (illegal anywhere in JSON) and lone surrogates
    return (o < 0x20 and ch not in _CONTROL_OK) or 0xD800 <= o <= 0xDFFF


def scan_file(path, max_runs=30):
    data = path.read_bytes()
    print(f"\n===== {path.name} ({len(data):,} bytes) =====")

    idx = data.find(b'{"')
    if idx < 0:
        print("  no JSON start found in file")
        return
    if idx > 0:
        print(f"  header: {idx} bytes, hex: {data[:idx].hex()}")
    payload = data[idx:]
    text = payload.decode("utf-8", "surrogateescape")

    # tail bytes (checking for trailing NUL padding like the first Inspect saw)
    print(f"  tail: {data[-16:].hex()}")

    # census of suspicious runs
    runs = []
    i, n = 0, len(text)
    while i < n:
        if is_suspicious(text[i]):
            j = i
            while j < n and is_suspicious(text[j]):
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    lengths = sorted(r[1] for r in runs)
    print(f"  suspicious runs: {len(runs)}, lengths: {lengths[:40]}"
          + (" ..." if len(lengths) > 40 else ""))
    for off, ln in runs[:max_runs]:
        raw = payload[off:off + ln]
        before = text[max(0, off - 40):off]
        after = text[off + ln:off + ln + 24]
        print(f"  @{off} len={ln} hex={raw.hex()}")
        print(f"      before: {before!r}")
        print(f"      after : {after!r}")
    if len(runs) > max_runs:
        print(f"  ... {len(runs) - max_runs} more runs not shown")

    # what does a plain parse do?
    try:
        json.loads(text)
        print("  PARSES FULLY as JSON (!)")
    except json.JSONDecodeError as e:
        print(f"  parse error: {e.msg} at char {e.pos}")
        print(f"      context: {text[max(0, e.pos-24):e.pos+24]!r}")


def main():
    folder = Path(sys.argv[1]).expanduser()
    files = sorted(folder.glob("*.hg"),
                   key=lambda p: p.name)
    for f in files:
        try:
            scan_file(f)
        except Exception as e:
            print(f"\n===== {f.name} =====")
            print(f"  scanner blew up: {e.__class__.__name__}: {e}")


if __name__ == "__main__":
    main()