#!/usr/bin/env python3
"""mine5.py -- seam-vs-text statistics over a token zone.

Usage:
  python mine5.py seams A.hg B.hg 7b224f3439223a5b 1600
  python mine5.py flow  A.hg      7b224f3439223a5b 1600
"""
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

def zone(path, anchor_hex, length):
    data = Path(path).expanduser().read_bytes()
    anchor = bytes.fromhex(anchor_hex)
    idx = data.find(anchor)          # fixed-string search -- no regex lessons forgotten
    if idx < 0:
        sys.exit(f"anchor {anchor_hex} not found in {path}")
    start = idx + len(anchor)
    return data[start:start + length]

def is_text_byte(b):
    ch = chr(b)
    return ch.isdigit() or ch in ".-,\"[]{}"

def seams(path_a, path_b, anchor_hex, length):
    za, zb = zone(path_a, anchor_hex, length), zone(path_b, anchor_hex, length)
    sm = SequenceMatcher(None, za, zb, autojunk=False)
    static, volatile = Counter(), Counter()
    eq_bytes = ch_bytes = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            eq_bytes += i2 - i1
            for x in za[i1:i2]:
                static[x] += 1
        else:
            ch_bytes += max(i2 - i1, j2 - j1)
            for x in za[i1:i2]:
                volatile[x] += 1
            if tag != "replace" or (i2 - i1) != (j2 - j1):
                for x in zb[j1:j2]:
                    volatile[x] += 1
    def top(c, n=14):
        return ", ".join(f"{v:#04x}x{k}" for v, k in c.most_common(n))
    print(f"zone: {len(za):,} vs {len(zb):,} bytes | equal {eq_bytes:,} | changed {ch_bytes:,}")
    print(f"\n-- STATIC seams (bytes inside unchanged regions), top:")
    print(f"   {top(static)}")
    print(f"-- VOLATILE seams (bytes inside changed regions), top:")
    print(f"   {top(volatile)}")
    # range rollup: where does each class live?
    for name, c in (("static", static), ("volatile", volatile)):
        tot = sum(c.values()) or 1
        lo = sum(v for k, v in c.items() if k < 0x20) / tot
        mid = sum(v for k, v in c.items() if 0x20 <= k < 0x80) / tot
        hi = sum(v for k, v in c.items() if k >= 0x80) / tot
        print(f"-- {name}: <0x20 {lo:.0%} | 0x20-0x7f {mid:.0%} | >=0x80 {hi:.0%}")

def flow(path, anchor_hex, length):
    """Render the stream as typed tokens: NUM/WORD/STR/SEAM."""
    z = zone(path, anchor_hex, length)
    out, i = [], 0
    while i < len(z):
        b = z[i]
        if is_text_byte(b):
            j = i
            while j < len(z) and is_text_byte(z[j]):
                j += 1
            out.append(f"NUM|{z[i:j].decode('latin-1')}|" if any(chr(x).isdigit() for x in z[i:j])
                       else f"PUNCT|{z[i:j].decode('latin-1')}|")
            i = j
        elif chr(b).isalpha():
            j = i
            while j < len(z) and chr(z[j]).isalnum():
                j += 1
            out.append(f"WORD|{z[i:j].decode('latin-1')}|" if j - i >= 2
                       else f"SEAM<{b:02x}>")
            i = j
        else:
            out.append(f"SEAM<{b:02x}>")
            i += 1
    print(" ".join(out))

def main():
    if sys.argv[1] == "seams":
        seams(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
    elif sys.argv[1] == "flow":
        flow(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        print(__doc__)

if __name__ == "__main__":
    main()