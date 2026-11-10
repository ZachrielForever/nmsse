"""SaveSession: one profile folder + one selected slot behind typed access."""
from pathlib import Path

import backup
import decode
from mapping import KeyMap

# PlayerStateData lives at different depths in old vs new format.
PLAYER_ROOTS = (( "BaseContext", "PlayerStateData"), ("PlayerStateData",))


class SaveSession:
    def __init__(self, profile_dir, keymap=None):
        self.profile = Path(profile_dir)
        self.keymap = keymap or KeyMap({})
        self.slot_path = None
        self.view = []          # annotated docs: what tabs read AND edit
        self.method = None
        self.report = {}
        self.dirty = False

    # -------------------------------------------------------------- slots
    def list_slots(self):
        """Save-slot files (not mf_*, not storage) with mtimes."""
        out = []
        for p in self.profile.glob("*.hg"):
            n = p.stem
            if n.startswith("mf_") or not (n == "save"
                                          or (n.startswith("save")
                                              and n[4:].isdigit())):
                continue
            out.append((str(p), p.stat().st_mtime))
        return sorted(out, key=lambda t: -t[1])

    def load_slot(self, path):
        docs, method, report = decode.decode_file(path)
        self.slot_path = str(path)
        self.method = method
        self.report = report
        self.view = [self.keymap.annotate(d) for d in docs]
        self.dirty = False
        return report

    # --------------------------------------------------------- accessors
    def at(self, *path, default=None):
        """Read from the annotated doc along an exact path."""
        node = self.view[0] if self.view else None
        for part in path:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def dig(self, *leaf, default=None):
        """Read a player-state field, trying every known root shape."""
        for root in PLAYER_ROOTS:
            v = self.at(*root, *leaf)
            if v is not None:
                return v
        return default

    @property
    def units(self):      return self.dig("Units", default=0)
    @property
    def nanites(self):    return self.dig("Nanites", default=0)
    @property
    def quicksilver(self):return self.dig("Specials", default=0)
    @property
    def health(self):     return self.dig("Health", default=0)
    @property
    def shield(self):     return self.dig("Shield", default=0)
    @property
    def playtime(self):
        return self.at("CommonStateData", "TotalPlayTime", default=0)

    # -------------------------------------------------------------- save
    def mark_dirty(self):
        self.dirty = True

    def save(self):
        """De-annotate, roundtrip-gate, write atomically. Returns status."""
        if not self.slot_path or not self.dirty:
            return "Nothing to save."
        out = [self.keymap.deannotate(d) for d in self.view]
        nuls = self.report.get("suffix_nuls", 0)
        if not decode.roundtrip_ok(out, self.method, suffix_nuls=nuls):
            return "Roundtrip check FAILED -- nothing written."
        bk = backup.make_backup(self.slot_path)
        blob = decode.encode_docs(out, self.method, suffix_nuls=nuls)
        tmp = Path(self.slot_path).with_suffix(".hg.tmp")
        tmp.write_bytes(blob)
        tmp.replace(self.slot_path)
        self.dirty = False
        return f"Saved. Backup: {bk}"

    # ------------------------------------------------------ write access
    def _player_dict(self):
        """The PlayerStateData dict, whichever root shape the save uses."""
        for root in PLAYER_ROOTS:
            node = self.view[0] if self.view else None
            for part in root:
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    node = None
                    break
            if isinstance(node, dict):
                return node
        return None

    def set_player(self, leaf, value):
        """Set a named player-state field (annotated key). True on success."""
        d = self._player_dict()
        if d is None or leaf not in d:
            return False
        d[leaf] = value
        self.dirty = True
        return True