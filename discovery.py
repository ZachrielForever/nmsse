"""Auto-discovery of NMS save folders across Steam libraries and platforms."""
import os
import re
from pathlib import Path

GAME_ID = "275850"
COMPAT = (f"steamapps/compatdata/{GAME_ID}/pfx/drive_c/users/steamuser/"
          "AppData/Roaming/HelloGames/NMS")


def _vdf_libraries():
    """Extra Steam library roots, parsed from Valve's own libraryfolders.vdf."""
    home = Path.home()
    vdfs = [
        home / ".local/share/Steam/steamapps/libraryfolders.vdf",
        home / ".steam/steam/steamapps/libraryfolders.vdf",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/"
               "steamapps/libraryfolders.vdf",
    ]
    out, seen = [], set()
    for vdf in vdfs:
        try:
            text = vdf.read_text(errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r'"path"\s*"([^"]+)"', text):
            p = Path(m.group(1).replace("\\\\", "\\"))
            if str(p) not in seen and p.is_dir():
                seen.add(str(p))
                out.append(p)
    return out


def _steam_roots():
    home = Path.home()
    roots = [home / ".local/share/Steam", home / ".steam/steam",
             home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
             *_vdf_libraries()]
    out, seen = [], set()
    for r in roots:
        if r.is_dir() and str(r) not in seen:
            seen.add(str(r))
            out.append(r)
    return out


def find_profiles():
    """Every NMS profile (st_<steamid>) on this machine.

    Returns [{path, source, account, latest_mtime}] sorted newest first.
    """
    profiles, seen = [], {}

    def add(p, source):
        p = Path(p)
        if not p.is_dir() or not any(p.glob("*.hg")):
            return
        p = p.resolve()
        if p in seen:
            seen[p]["latest_mtime"] = max(seen[p]["latest_mtime"],
                                          _newest_hg(p))
            return
        seen[p] = {"path": str(p), "source": source, "account": p.name,
                   "latest_mtime": _newest_hg(p)}

    for root in _steam_roots():
        base = root / COMPAT
        if base.is_dir():
            for st in base.glob("st_*"):
                add(st, f"Steam: {root}")
    if os.environ.get("APPDATA"):                      # native Windows build
        base = Path(os.environ["APPDATA"]) / "HelloGames" / "NMS"
        if base.is_dir():
            for st in base.glob("st_*"):
                add(st, "Windows native")
    profiles = sorted(seen.values(), key=lambda d: -d["latest_mtime"])
    return profiles


def _newest_hg(folder):
    mt = 0
    for p in Path(folder).glob("*.hg"):
        try:
            mt = max(mt, p.stat().st_mtime)
        except OSError:
            pass
    return mt


def slot_name(path):
    """Human label for a save-slot file (save.hg -> Slot 1, etc.)."""
    name = Path(path).stem
    if name == "save":
        return "Slot 1"
    if name.startswith("save") and name[4:].isdigit():
        return f"Slot {int(name[4:]) + 1}"
    return name