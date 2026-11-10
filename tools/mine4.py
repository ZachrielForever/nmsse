#!/usr/bin/env python3
"""mine4.py -- record-table diff for token zones anchored on JSON keys.

Usage:
  python mine4.py recdiff A.hg B.hg ANCHOR_HEX LENGTH
  example:
  python mine4.py recdiff baseline.hg stepped.hg 7b224f3439223a5b 1600
  python mine4.py tokens A.hg ANCHOR_HEX LENGTH        # one-file record table
"""
import re
import sys
from pathlib import Path

BOUNDARY = re.compile(rb"\x00[\x10-\x2f]")

def zone(path, anchor_hex, length):
    data = Path(path).expanduser().read_bytes()
    idx = data.find(bytes.fromhex(anchor_hex))
    if idx < 0:
        sys.exit(f"anchor {anchor_hex} not found in {path}")
    return data[idx + len(bytes.fromhex(anchor_hex)):idx + len(bytes.fromhex(anchor_hex)) + length]

def tokenize(seg):
    out, i = [], 0
    while i < len(seg):
        if 32 <= seg[i] <= 126:
            j = i
            while j < len(seg) and 32 <= seg[j] <= 126:
                j += 1
            out.append(f"|{seg[i:j].decode('latin-1')}|")
            i = j
        else:
            out.append(f"<{seg[i]:02x}>")
            i += 1
    return " ".join(out)

def split_records(seg):
    ms = list(BOUNDARY.finditer(seg))
    starts = [0] + [m.start() for m in ms]
    ends = [m.start() for m in ms] + [len(seg)]
    return [seg[a:b] for a, b in zip(starts, ends)]

def recdiff(pa, pb, anchor_hex, length):
    ra, rb = split_records(zone(pa, anchor_hex, length)), \
             split_records(zone(pb, anchor_hex, length))
    print(f"A: {len(ra)} records, B: {len(rb)} records "
          f"(misalignment after inserts is possible -- watch for drift)")
    for n in range(max(len(ra), len(rb))):
        sa = ra[n] if n < len(ra) else b""
        sb = rb[n] if n < len(rb) else b""
        same = "  same" if sa == sb else "  DIFF"
        print(f"\n-- rec {n}{same}")
        print(f"  A: {tokenize(sa)}")
        if sa != sb:
            print(f"  B: {tokenize(sb)}")

def tokens(pa, anchor_hex, length):
    for n, rec in enumerate(split_records(zone(pa, anchor_hex, length))):
        print(f"\n-- rec {n}")
        print(f"  {tokenize(rec)}")

def main():
    if sys.argv[1] == "recdiff":
        recdiff(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
    elif sys.argv[1] == "tokens":
        tokens(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        print(__doc__)

if __name__ == "__main__":
    main()