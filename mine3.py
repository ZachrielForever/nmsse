#!/usr/bin/env python3
"""mine3.py -- band-scoped analysis of NMS hybrid save streams.

Usage:
  python mine3.py map FILE START END      # per-byte classification map
  python mine3.py runs FILE START END     # ASCII-run stats + preceding bytes
  python mine3.py frame FILE START END    # framing-candidate scorer
"""
import struct
import sys
from collections import Counter
from pathlib import Path

def band(path, start, end):
    data = Path(path).expanduser().read_bytes()
    return data[start:end]

def cls(b):
    ch = chr(b)
    if ch.isdigit():
        return "D"                    # digit
    if ch in ".-,":
        return "d"                    # numeric punctuation
    if 0x20 <= b <= 0x7e:
        return "a"                    # other ascii
    return "#"                        # non-ascii seam byte

def show_map(data):
    print("== map ==")
    for i in range(0, len(data), 64):
        row = data[i:i + 64]
        tags = "".join(cls(b) for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "·" for b in row)
        print(f"{i:6d}  {tags}")
        print(f"        {asc}")

def show_runs(data):
    print("== ascii runs (digit-runs + neighbors) ==")
    runs = Counter()
    seqs = []
    i = 0
    while i < len(data):
        if cls(data[i]) in "Dd":
            j = i
            while j < len(data) and cls(data[j]) in "Dd":
                j += 1
            pre = data[max(0, i - 3):i]
            runs[(j - i, pre.hex())] += 1
            seqs.append((i, j - i, pre.hex(), data[i:j]))
            i = j
        else:
            i += 1
    print("top (runlen, preceding-3-bytes):")
    for (rl, pre), c in runs.most_common(20):
        print(f"  runlen={rl:3d} pre={pre:<6s} x{c}")
    print("\nfirst 30 sequences:")
    for off, rl, pre, raw in seqs[:30]:
        txt = raw.decode("latin-1")
        print(f"  @{off:6d} pre={pre:<6s} len={rl:3d} |{txt[:32]}|")

def frame_score(data, hdr, tag_first):
    """Greedily decode: [tag?]len... Score = printable fraction weighted
    by successful full traversal. Returns (score, tokens, resync)."""
    best = (0.0, 0, -1)
    for resync in range(6):
        pos, tokens, ok_bytes, total = resync, 0, 0, 0
        while pos + hdr <= len(data):
            if tag_first:
                pos += 1
            ln = (data[pos] if hdr == 1
                  else struct.unpack_from("<H", data, pos)[0])
            pos += hdr
            if ln > len(data) - pos or ln > 4096:
                break
            chunk = data[pos:pos + ln]
            pr = sum(1 for b in chunk if 32 <= b <= 126)
            ok_bytes += pr
            total += ln
            tokens += 1
            pos += ln
        if total:
            score = (ok_bytes / total) * min(tokens, 400) / 400
            if score > best[0]:
                best = (score, tokens, resync)
    return best

def show_frame(data):
    print("== framing candidates ==")
    results = []
    for hdr in (1, 2):
        for tag_first in (False, True):
            score, tokens, resync = frame_score(data, hdr, tag_first)
            name = (f"[tag][{'u8' if hdr == 1 else 'u16le'} len]"
                    if tag_first else f"[{'u8' if hdr == 1 else 'u16le'} len]")
            results.append((score, name, tokens, resync))
    for score, name, tokens, resync in sorted(results, reverse=True):
        print(f"  {name:<22s} score={score:.3f} tokens={tokens} "
              f"resync={resync}")
    best = max(results)
    print(f"\n--> best: {best[1]} (resync {best[3]})")
    print("    if u16-le dominates with tag, compare tag values across tokens")
    print("    next: mine3.py frame on a band, then dump the tag histogram")

def main():
    mode, path, s, e = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    data = band(path, s, e)
    print(f"band [{s}:{e}] ({len(data)} bytes)\n")
    if mode == "map":
        show_map(data)
    elif mode == "runs":
        show_runs(data)
    elif mode == "frame":
        show_frame(data)

if __name__ == "__main__":
    main()