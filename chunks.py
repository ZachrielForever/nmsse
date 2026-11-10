#!/usr/bin/env python3
"""chunks.py -- pragmatic same-length editing of hybrid saves.

Usage:
  python chunks.py find FILE NEEDLE        # offsets of a literal byte string
  python chunks.py nums  FILE              # numeric literals with offsets
  python chunks.py edit  FILE OFFSET NEW   # same-length substitution w/ backup
"""
import re
import shutil
import sys
import time
from pathlib import Path

NUM = re.compile(rb"-?[0-9]+(?:\.[0-9]+)?")

def find(path, needle):
    data = Path(path).expanduser().read_bytes()
    pat = needle.encode("utf-8").decode("unicode_escape").encode("latin-1")
    hits = [m.start() for m in re.finditer(re.escape(pat), data)]
    for h in hits:
        print(f"@{h:7d}  ctx: {data[max(0,h-16):h+24]!r}")
    if not hits:
        print("no hits")

def nums(path):
    data = Path(path).expanduser().read_bytes()
    start = data.find(b'{"')
    for m in NUM.finditer(data, max(start, 1)):
        print(f"@{m.start():7d}  {m.group().decode()}")

def edit(path, offset, newtext):
    p = Path(path).expanduser()
    data = p.read_bytes()
    blob = newtext.encode("utf-8").decode("unicode_escape").encode("latin-1")
    old = data[offset:offset + len(blob)]
    if not old:
        sys.exit("refusing: nothing at that offset")
    if len(old) != len(blob):
        sys.exit(f"refusing: length-changing edit "
                 f"({len(blob)} given, {len(old)} on disk)")
    bak = p.with_name(p.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(p, bak)
    p.write_bytes(data[:offset] + blob + data[offset + len(blob):])
    print(f"edited @{offset}: {old!r} -> {blob!r}")
    print(f"backup: {bak}")
    print("size unchanged, all other bytes byte-identical")

def main():
    if sys.argv[1] == "find":
        find(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "nums":
        nums(sys.argv[2])
    elif sys.argv[1] == "edit":
        edit(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    else:
        print(__doc__)

if __name__ == "__main__":
    main()