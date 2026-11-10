"""Tab package: one module per tab, plus the registry that orders them.

Each tab module exposes build(win) -> QWidget and optionally refresh(win),
called whenever a slot loads. Unwritten tabs render as stubs in registry
order until their module exists.
"""
from importlib import import_module

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# (title, module, blurb, phase) -- blurb/phase shown only while stubbed
REGISTRY = [
    ("Overview", "overview", None, None),
    ("Account", "account",
     "accountdata.hg: expedition rewards, entitlements, platform history.",
     "Phase 5"),
    ("Suit & Inventory", "suit",
     "Exosuit slot grid: general / tech / cargo, slot classes, damage.",
     "Phase 1"),
    ("Language", "language",
     "Learned words per alien race, per word group.", "Phase 4"),
    ("Companions", "companions",
     "Pets: trust, traits, eggs, accessories, unlocked slots.", "Phase 3"),
    ("Planet-side", "planetside",
     "Ground/sea vehicles, settlements, bases & storage chests.",
     "Phase 3-4"),
    ("Starship", "starship",
     "Ship roster + active ship: inventory, health, class, seeds.",
     "Phase 2"),
    ("Multitool", "multitool",
     "Tool roster + active tool: inventory, stats, archived tools.",
     "Phase 2"),
    ("Fleet", "fleet",
     "Freighter, frigates, squadron pilots, fleet expeditions.", "Phase 3"),
    ("Progress", "progress",
     "Missions, milestones, expedition stage state, discoveries.",
     "Phase 4"),
    ("Raw JSON", "rawjson", None, None),
]


def _stub(title, blurb, phase):
    def build(win):
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel(f"<big><b>{title}</b></big><br><br>{blurb}"
                     f"<br><br><i>Scheduled: {phase}</i>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 0, Qt.AlignTop)
        lay.addStretch(1)
        return w
    return build


def load_tabs(win):
    """Mount every registry tab. Returns [(title, widget, refresh_fn)]."""
    out = []
    for title, mod, blurb, phase in REGISTRY:
        try:
            m = import_module("." + mod, __package__)
            out.append((title, m.build(win), getattr(m, "refresh", None)))
        except ModuleNotFoundError:
            out.append((title, _stub(title, blurb, phase)(win), None))
    return out