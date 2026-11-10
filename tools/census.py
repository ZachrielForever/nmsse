#!/usr/bin/env python3
"""census.py -- structural inventory of a decoded save JSON.

Produces a collapsed schema of every key: type, size, and child keys,
assuming lists are homogeneous (first element sketched).

Usage:
  python tools/census.py specimens/save5_readable.json [--depth 4]
  python tools/census.py specimens/save5_readable.json \
      --peek Stats --peek KnownWords --peek KnownWordGroups
"""
import argparse
import json
import sys


def brief(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, int):
        return f"int {v}"
    if isinstance(v, float):
        return f"float {v:g}"
    if isinstance(v, str):
        s = v if len(v) <= 48 else v[:45] + "..."
        return f'str "{s}"'
    if isinstance(v, dict):
        return f"dict{{{len(v)} keys}}"
    if isinstance(v, list):
        if not v:
            return "list[0]"
        kinds = "|".join(sorted({type(x).__name__ for x in v}))
        return f"list[{len(v)}] of {kinds}"
    return type(v).__name__


def sketch(obj, depth, maxdepth, indent=0, prefix=""):
    pad = "  " * indent
    print(f"{pad}{prefix}{brief(obj)}")
    if depth >= maxdepth:
        return
    child_indent = indent + 1
    if isinstance(obj, dict):
        for k, v in obj.items():
            print(f"{'  ' * child_indent}{k}: {brief(v)}")
            if isinstance(v, (dict, list)):
                sketch(v, depth + 1, maxdepth, child_indent + 1)
    elif isinstance(obj, list):
        if obj and isinstance(obj[0], (dict, list)):
            sketch(obj[0], depth + 1, maxdepth, child_indent, prefix="[0] ")


def find_all(o, key, path="", hits=None):
    hits = hits if hits is not None else []
    if isinstance(o, dict):
        for k, v in o.items():
            child = f"{path}/{k}"
            if k == key:
                hits.append((child, v))
            find_all(v, key, child, hits)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            find_all(v, key, f"{path}[{i}]", hits)
    return hits


def peek(value, maxchars=1200):
    if isinstance(value, list):
        sample = value[0] if value else value
        txt = json.dumps(sample, ensure_ascii=False)
        note = f"  (list of {len(value)}, first element)"
    else:
        txt = json.dumps(value, ensure_ascii=False)
        note = ""
    if len(txt) > maxchars:
        txt = txt[:maxchars] + " …TRUNCATED"
    print(txt + note)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--peek", action="append", default=[],
                    help="print full content of subtrees under this key")
    args = ap.parse_args()

    doc = json.load(open(args.file, encoding="utf-8"))

    if args.peek:
        for key in args.peek:
            for i, (path, val) in enumerate(find_all(doc, key)):
                if i >= 3:
                    print(f"… ({len(find_all(doc, key))} total, showing 3)")
                    break
                print(f"\n=== peek '{key}' at {path} ===")
                peek(val)
        return

    sketch(doc, 0, args.depth)
    print(file=sys.stderr)
    print("done -- schema above", file=sys.stderr)


if __name__ == "__main__":
    main()