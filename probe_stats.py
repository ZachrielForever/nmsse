# probe_stats.py -- dump the raw material for the Overview redesign
import json
from collections import Counter

doc = json.load(open("specimens/save5_readable.json"))

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

# 1) the big one: the stats table(s) -- event/id + int/float values
for path, val in find_all(doc, "Stats"):
    print(f"=== Stats at {path} ===")
    tbl = val.get("Table", []) if isinstance(val, dict) else []
    for row in tbl:
        eid = row.get("Event", row)
        iv = row.get("IntValue", "-")
        fv = row.get("FloatValue", "-")
        if isinstance(eid, dict):
            eid = eid.get("Stat", eid)
        print(f"  {eid:<45} int={iv}  float={fv}")
    print(f"  ({len(tbl)} entries)")

# 2) language learning state
for key in ("KnownWords", "KnownWordGroups"):
    for path, val in find_all(doc, key):
        if isinstance(val, dict):
            summary = {k: (len(v) if isinstance(v, (list, dict)) else v)
                       for k, v in list(val.items())[:8]}
            print(f"=== {key} at {path}: {summary}")
        else:
            print(f"=== {key} at {path}: {len(val)} entries")

# 3) ownership counts for the vanity stats
for key in ("ShipOwnership", "Multitools", "FleetFrigates",
            "SquadronPilots", "SettlementStatesV2", "Pets",
            "Milestones", "RevealBlackHoles", "TotalPlayTime"):
    for path, val in find_all(doc, key):
        n = len(val) if isinstance(val, (list, dict)) else val
        print(f"{key:<20} at {path}: {n!r}")