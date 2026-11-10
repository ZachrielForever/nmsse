"""Key mapping: obfuscated token <-> readable name, with convert/apply CLI."""
import json
import sys


class KeyMap:
    """Bidirectional token map for NMS obfuscated JSON keys."""

    def __init__(self, fwd):
        self.fwd = dict(fwd)
        self.rev = {}
        self.collisions = []
        for tok, name in fwd.items():
            if name in self.rev:
                self.collisions.append((name, self.rev[name], tok))
                continue
            self.rev[name] = tok
        # v0.1 compatibility: jsonmodel.py reads .obf for display names
        self.obf = self.fwd

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("entries"), dict):
            data = data["entries"]
        if not isinstance(data, dict):
            raise ValueError("Mapping JSON must be a {token: name} object")
        return cls(data)

    @property
    def size(self):
        return len(self.fwd)

    def get(self, key, default=None):
        return self.fwd.get(key, default)

    def label(self, key):
        """Friendly name if known, else the raw token."""
        return self.fwd.get(key, key)

    def annotate(self, obj):
        """Recursively rename tokens -> friendly names (returns new object)."""
        return _walk(obj, self.fwd)

    def deannotate(self, obj):
        """Recursively rename friendly names -> tokens (returns new object)."""
        return _walk(obj, self.rev)


def _walk(obj, table):
    if isinstance(obj, dict):
        return {table.get(k, k): _walk(v, table) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, table) for v in obj]
    return obj


# --------------------------------------------------------------------- CLI

def convert(tsv_path, out_path):
    """Convert nmstoolkit TSV (token<TAB>Name) to mapping JSON."""
    fwd, skipped = {}, 0
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                skipped += 1
                continue
            fwd[parts[0]] = parts[1]
    km = KeyMap(fwd)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fwd, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{len(fwd)} mappings written to {out_path}")
    if skipped:
        print(f"warning: {skipped} malformed lines skipped")
    if km.collisions:
        print(f"warning: {len(km.collisions)} duplicate friendly names "
              f"(deannotate keeps the first token)")
    return km


def apply_map(map_path, in_path, out_path):
    """Annotate a decoded save dump with friendly keys, for browsing."""
    km = KeyMap.load(map_path)
    with open(in_path, "r", encoding="utf-8") as f:
        docs = json.load(f)
    out = km.annotate(docs)
    total, known = _coverage(docs, km.fwd)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"wrote {out_path}")
    print(f"key coverage: {known}/{total} ({100 * known / total:.1f}%)")
    if km.collisions:
        for name, a, b in km.collisions[:5]:
            print(f"  duplicate name {name!r}: {a} / {b}")


def _coverage(obj, fwd):
    total = known = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            total += 1
            if k in fwd:
                known += 1
            t, n = _coverage(v, fwd)
            total += t
            known += n
    elif isinstance(obj, list):
        for v in obj:
            t, n = _coverage(v, fwd)
            total += t
            known += n
    return total, known


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "convert":
        convert(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 5 and sys.argv[1] == "apply":
        apply_map(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print("usage:")
        print("  python mapping.py convert <jsonmap.txt> <out.json>")
        print("  python mapping.py apply <map.json> <decoded.json> <out.json>")
        sys.exit(1)