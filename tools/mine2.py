#!/usr/bin/env python3
"""mine2.py -- grammar mining for hybrid .hg saves. v3

Usage:
  python mine2.py census save5.hg
  python mine2.py tlv save5.hg
  python mine2.py delta old.hg new.hg
  python mine2.py sub old.hg new.hg     # byte-delta histogram + headers
"""
import struct
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

LITERALS = (b"true", b"false", b"null")
VALUE_START = b'"-0123456789[{ \t\r\n'
STOP = b',]}"'

def load(path):
    data = Path(path).expanduser().read_bytes()
    j = data.find(b'{"')
    return data, (j if j >= 0 else 0)

def head_line(data, start):
    print(f"  json-start: {start}, first 24 bytes: {data[:24].hex()}")

def last_key_before(payload, i, back=120):
    window = payload[max(0, i - back):i]
    k = window.rfind(b'":')
    if k < 0:
        return "?"
    s = max(window.rfind(b'"', 0, k), window.rfind(b',', 0, k))
    key = window[s + 1:k]
    return key.decode("latin-1") if 0 < len(key) <= 20 else "?"

def census(path):
    data, start = load(path)
    payload = data[start:]
    print(f"== census: {Path(path).name} (payload {len(payload):,}) ==")
    head_line(data, start)
    tags, weird, shown = Counter(), [], 0
    i = 1
    while i < len(payload):
        if payload[i - 1:i] in (b":", b",", b"["):
            if payload[i:i + 1] in VALUE_START or any(
                    payload[i:i + len(l)] == l for l in LITERALS):
                i += 1
                continue
            j = i
            while j < len(payload) and payload[j:j + 1] not in STOP:
                j += 1
            if j == i:
                if len(weird) < 12:
                    weird.append((start + i, payload[i - 24:i + 8]))
                i += 1
                continue
            tags[payload[i]] += 1
            if shown < 35:
                print(f"@{start + i:6d} key='{last_key_before(payload, i - 1)}' "
                      f"tag={payload[i]:#04x} span={j - i} "
                      f"hex={payload[i:j][:20].hex()}")
                shown += 1
            i = j
        else:
            i += 1
    print("-- tags: " + ", ".join(f"{t:#04x}x{c}"
                                   for t, c in tags.most_common(25)))
    print(f"-- total real binary tokens: {sum(tags.values())}")
    print("-- structural oddities:")
    for off, ctx in weird:
        print(f"   @{off}: {ctx.hex()}")
    print()

def tlv_test(path):
    data, start = load(path)
    payload = data[start:]
    starts = [i for i in range(1, len(payload) - 8)
              if payload[i - 1:i] in (b":", b",")]
    stats = defaultdict(lambda: [0, 0])
    fw = Counter()
    for i in starts:
        if payload[i:i + 1] in VALUE_START or any(
                payload[i:i + len(l)] == l for l in LITERALS):
            continue
        tag = payload[i]
        ln = struct.unpack_from("<H", payload, i + 1)[0]
        end = i + 3 + ln
        stats[tag][1] += 1
        if end < len(payload) and payload[end:end + 1] in b',]}':
            stats[tag][0] += 1
        for w in (2, 4, 8):
            if payload[i + w:i + w + 1] in b',]}':
                fw[w] += 1
    print(f"== TLV test ({Path(path).name}) ==")
    ranked = sorted(((h / t, t, h, tag) for tag, (h, t) in stats.items()
                     if t >= 8), reverse=True)
    for rate, trials, hits, tag in ranked[:15]:
        print(f"tag {tag:#04x}: {hits}/{trials} framed ({rate:.0%})")
    print(f"-- fixed-width landing: +2:{fw[2]}  +4:{fw[4]}  +8:{fw[8]}")
    print()

def delta(old, new):
    a, ja = load(old)
    b, jb = load(new)
    a, b = a[ja:], b[jb:]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    changed = sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in ops)
    print(f"== delta: {Path(old).name} vs {Path(new).name} ==")
    print(f"payload sizes: {len(a):,} vs {len(b):,}, hunks: {len(ops)}, "
          f"~{changed:,} changed bytes")
    for tag, i1, i2, j1, j2 in ops[:40]:
        ca, cb = a[i1:i2], b[j1:j2]
        pa = "".join(chr(x) if 32 <= x < 127 else "." for x in ca[:40])
        pb = "".join(chr(x) if 32 <= x < 127 else "." for x in cb[:40])
        print(f"\n{tag} A[{i1}:{i2}]({i2-i1}B) B[{j1}:{j2}]({j2-j1}B)")
        print(f"  A: {ca[:40].hex()}  |{pa}|")
        print(f"  B: {cb[:40].hex()}  |{pb}|")

def sub(old, new):
    a, ja = load(old)
    b, jb = load(new)
    print(f"== headers ==")
    head_line(a, ja)
    head_line(b, jb)
    print(f"  header u16@4: A={struct.unpack_from('<H', a, 4)[0]:#06x} "
          f"B={struct.unpack_from('<H', b, 4)[0]:#06x} "
          f"(delta {(struct.unpack_from('<H', b, 4)[0] - struct.unpack_from('<H', a, 4)[0]) & 0xFFFF})")
    a, b = a[ja:], b[jb:]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    hist, pairs, unequal = Counter(), 0, 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        if (i2 - i1) != (j2 - j1):
            unequal += 1
            continue
        for k in range(i2 - i1):
            hist[(b[j1 + k] - a[i1 + k]) & 0xFF] += 1
            pairs += 1
    print(f"\n== byte-delta histogram ({pairs} pairs in {unequal} skipped "
          f"unequal hunks) ==")
    for d, c in hist.most_common(12):
        pct = 100 * c / max(pairs, 1)
        print(f"  delta {d:#04x} ({d:3d}): {c:6d}  ({pct:.1f}%)")
    top = hist.most_common(1)
    if top and top[0][1] / max(pairs, 1) > 0.5:
        print(f"\n--> DOMINANT delta {top[0][0]:+#d}: additive obfuscation "
              "layer CONFIRMED. Next: recover per-save key via known plaintext.")
    else:
        print("\n--> no dominant delta; the +3s were localized, key may be "
              "position-dependent. Report the histogram tail.")
    print()

def main():
    mode = sys.argv[1]
    if mode == "census":
        census(sys.argv[2])
    elif mode == "tlv":
        tlv_test(sys.argv[2])
    elif mode == "delta":
        delta(sys.argv[2], sys.argv[3])
    elif mode == "sub":
        sub(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)

if __name__ == "__main__":
    main()