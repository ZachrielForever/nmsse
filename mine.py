#!/usr/bin/env python3
"""Grammar miner for hybrid-format .hg saves.

Usage:
    python mine.py save6.hg save5.hg
    (second file optional; enables aligned diff)
"""
import re
import struct
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

STOP = b',]}:'
VALUE_STARTERS = set('"-0123456789[{ \t\r\n')


def header_dump(data):
    n = data.find(b'{"')
    print(f"== header ==  (json starts at offset {n})")
    print(f"raw: {data[:24].hex()}")
    if 0 < n <= 24:
        h = data[:n]
        print(f"  u32@0  : {struct.unpack_from('<I', h, 0)[0]:#010x}  (magic)")
        print(f"  u16@4  : {struct.unpack_from('<H', h, 4)[0]:#06x}   <-- differs per file")
        print(f"  u16@6  : {struct.unpack_from('<H', h, 6)[0]:#06x}")
        print(f"  u32@8  : {struct.unpack_from('<I', h, 8)[0]:#010x}")
        print(f"  u64@10 : {struct.unpack_from('<Q', h, 10)[0]:#018x}")
        print(f"  f64@10 : {struct.unpack_from('<d', h, 10)[0]!r}")
    print()


def token_census(data):
    """Find spots where JSON expects a value but binary bytes sit instead."""
    n = data.find(b'{"')
    payload = data[n:]
    text = payload.decode("latin-1")  # byte-transparent view
    print("== binary token census ==")
    tags = Counter()
    lengths = Counter()
    key_tags = Counter()
    tokens_shown = 0
    for m in re.finditer(r'[:,\[]', text):
        i = m.end()
        if i >= len(text) or text[i] in VALUE_STARTERS:
            continue
        # binary token: grab tag byte + boundary hunt
        tag = ord(text[i])
        j = i
        while j < len(text) and ord(text[j]) not in STOP and ord(text[j]) != 0x22:
            j += 1
        blen = j - i
        tags[tag] += 1
        lengths[blen] += 1
        km = re.search(r'([A-Za-z0-9_>"!%^&]{1,6})":$', text[max(0, i - 14):i])
        key = km.group(1) if km else "?"
        key_tags[key] += 1
        if tokens_shown < 40:
            raw = payload[i:j + 1]
            print(f"@{n + i:6d} after '{key}': tag={tag:#04x} span={blen} "
                  f"bytes(hex)={raw[:16].hex()}")
            tokens_shown += 1
    print(f"\n-- tag frequency (top 20): "
          + ", ".join(f"{t:#04x}x{c}" for t, c in tags.most_common(20)))
    lens = sorted(lengths.items())
    print(f"-- span lengths: {lens[:40]}")
    print(f"-- keys followed by binary tokens (top 20): "
          + ", ".join(f"{k}x{c}" for k, c in key_tags.most_common(20)))
    print(f"-- total binary tokens: {sum(tags.values())}")
    print()


def enum_anchors(data):
    """Readable enum/string fragments -- alignment anchors for later."""
    text = data.decode("latin-1", "ignore")
    hits = re.findall(r'[A-Z][A-Z0-9_]{7,}', text)
    print(f"== enum-like anchors ==  total: {len(hits)}, top 30:")
    print(", ".join(sorted(set(hits))[:30]))
    print()


def aligned_diff(a, b):
    sa = a[a.find(b'{"'):] if b'{"' in a else a
    sb = b[b.find(b'{"'):] if b'{"' in b else b
    print(f"== aligned diff (payload bytes {len(sa):,} vs {len(sb):,}) ==")
    sm = SequenceMatcher(None, sa, sb, autojunk=False)
    eq_total = sum(bl.size for bl in sm.get_matching_blocks() if bl.size > 24)
    print(f"large matching regions cover ~{eq_total:,} bytes "
          f"({100 * eq_total / max(len(sa), len(sb)):.1f}% of longer file)")
    shown = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        print(f"  {tag}: fileA[{i1}:{i2}] ({i2-i1}B) vs fileB[{j1}:{j2}] ({j2-j1}B)")
        print(f"    A: {sa[max(0,i1-12):i2+12].hex()}")
        print(f"    B: {sb[max(0,j1-12):j2+12].hex()}")
        shown += 1
        if shown >= 20:
            print("  ... truncated")
            break
    print()


def main():
    paths = [Path(p).expanduser() for p in sys.argv[1:]]
    datas = [p.read_bytes() for p in paths]
    for p, d in zip(paths, datas):
        print(f"########## {p.name} ({len(d):,} bytes) ##########")
        header_dump(d)
        token_census(d)
        enum_anchors(d)
    if len(datas) == 2:
        aligned_diff(datas[0], datas[1])


if __name__ == "__main__":
    main()