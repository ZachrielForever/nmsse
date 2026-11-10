"""Declarative quick-edit targets.

Paths use friendly key names (post-mapping). A recipe whose path does not
resolve in the loaded save renders greyed with 'not found in this save',
so nothing silently pretends to work. Confidence reflects how verified
each field is against the live format.
"""

RECIPES = [
    {"group": "Currency", "label": "Units", "conf": "high",
     "path": ["PlayerStateData", "Units"], "dtype": "int"},
    {"group": "Currency", "label": "Nanites", "conf": "high",
     "path": ["PlayerStateData", "Nanites"], "dtype": "int"},
    {"group": "Currency", "label": "Quicksilver", "conf": "low",
     "path": ["PlayerStateData", "Specials"], "dtype": "int"},
    {"group": "Progress", "label": "Unlock all seasonal rewards", "conf": "low",
     "path": ["PlayerStateData", "SeasonalRewards"], "dtype": "bool",
     "note": "needs triage on live save"},
    {"group": "Progress", "label": "Unlock all words", "conf": "low",
     "path": ["PlayerStateData", "WordKnowledge"], "dtype": "bool",
     "note": "needs triage on live save"},
]


def resolve(obj, path):
    cur = obj
    for seg in path:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def apply_recipe(obj, recipe, value):
    cur = obj
    for seg in recipe["path"][:-1]:
        cur = cur[seg]
    cur[recipe["path"][-1]] = value