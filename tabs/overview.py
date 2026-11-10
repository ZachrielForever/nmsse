"""Overview tab: save biography -- scoreboard, currencies, stats, languages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

# Curated labels for stat IDs seen in real saves; unknown IDs are
# prettified mechanically rather than guessed at semantically.
STAT_LABELS = {
    "^DEATHS": "Deaths",
    "^TIMES_IN_SPACE": "Times entered space",
    "^DIST_WARP": "Warps made",
    "^ATLAS_LOOPS": "Atlas loops",
    "^ROAD_KILL": "Roadkill",
    "^ALIENS_MET": "Aliens met",
    "^TRA_MET": "Traders met",
    "^APP_SESSIONS": "Game sessions",
    "^BIG_SCAN_MIN": "Large scans",
    "^RARE_SCANNED": "Rare scans",
    "^TUTORIAL": "Tutorial steps",
    "^SCIENTIST_LORE": "Scientist lore",
}

CURRENCIES = (("Units", "Units"), ("Nanites", "Nanites"),
              ("Quicksilver", "Specials"))


def _pretty_stat(sid):
    return STAT_LABELS.get(sid, sid.lstrip("^").replace("_", " ").title())


def _fmt_time(secs):
    h, rem = divmod(int(secs or 0), 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _count(session, leaf):
    v = session.dig(leaf, default=[])
    return len(v) if isinstance(v, (list, dict)) else 0


def build(win):
    host = QWidget()
    outer = QVBoxLayout(host)
    win._ov = {}

    # ------------------------------------------------ scoreboard
    board = QGroupBox("Save summary")
    grid = QGridLayout(board)
    rows = [("Play time", lambda s: _fmt_time(s.playtime))]
    for label, leaf in (("Ships owned", "ShipOwnership"),
                        ("Multitools", "Multitools"),
                        ("Squadron pilots", "SquadronPilots"),
                        ("Frigates", "FleetFrigates")):
        rows.append((label, lambda s, lf=leaf: f"{_count(s, lf)}"))
    for i, (label, fn) in enumerate(rows):
        val = QLabel("--")
        grid.addWidget(QLabel(f"<b>{label}</b>"), i, 0)
        grid.addWidget(val, i, 1)
        win._ov[f"board/{label}"] = (fn, val)
    grid.setColumnStretch(2, 1)
    outer.addWidget(board)

    # ------------------------------------------------ currencies (editable)
    cur = QGroupBox("Currencies  (set a value, push, then Save in toolbar)")
    cg = QGridLayout(cur)
    for i, (label, leaf) in enumerate(CURRENCIES):
        current = QLabel("--")
        edit = QLineEdit()
        edit.setPlaceholderText("set to…")
        btn = QPushButton("Push")
        cg.addWidget(QLabel(f"<b>{label}</b>"), i, 0)
        cg.addWidget(current, i, 1)
        cg.addWidget(edit, i, 2)
        cg.addWidget(btn, i, 3)
        btn.clicked.connect(
            lambda _=False, lf=leaf, e=edit, w=win: _push(w, lf, e))
        win._ov[f"cur/{leaf}"] = current
    cg.setColumnStretch(4, 1)
    outer.addWidget(cur)

    # ------------------------------------------------ stats (scrollable)
    stats_box = QGroupBox("Lifetime statistics")
    sl = QVBoxLayout(stats_box)
    inner = QWidget()
    win._ov["stats_form"] = QFormLayout(inner)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(inner)
    scroll.setMinimumHeight(220)
    sl.addWidget(scroll)
    outer.addWidget(stats_box, 1)

    # ------------------------------------------------ languages
    lang = QGroupBox("Languages")
    lg = QGridLayout(lang)
    for j, name in enumerate(("Word groups tracked",
                              "Individual words learned",
                              "Group fluency by race")):
        val = QLabel("--")
        lg.addWidget(QLabel(f"<b>{name}</b>"), 0, j * 2)
        lg.addWidget(val, 0, j * 2 + 1)
        win._ov[f"lang/{name}"] = val
    lg.setColumnStretch(6, 1)
    outer.addWidget(lang)

    outer.addStretch(1)
    return host


def _push(win, leaf, edit):
    if not win.session:
        return
    try:
        v = int(edit.text().strip().replace(",", "").replace("_", ""))
    except ValueError:
        win.statusBar().showMessage(f"Invalid number for {leaf}")
        return
    if win.session.set_player(leaf, v):
        win._mark_dirty()
        refresh(win)
        win.statusBar().showMessage(
            f"{leaf} set to {v:,} -- use Save in the toolbar to write.")
    else:
        win.statusBar().showMessage(f"{leaf} not found in this save.")


def refresh(win):
    s = win.session
    if not s or not s.view:
        return
    for key, (fn, lbl) in win._ov.items():
        if key.startswith("board/"):
            lbl.setText(fn(s))
        elif key.startswith("cur/"):
            leaf = key.split("/", 1)[1]
            lbl.setText(f"{s.dig(leaf, default=0):,}")
        elif key == "lang/Word groups tracked":
            lbl.setText(str(_count(s, "KnownWordGroups")))
        elif key == "lang/Individual words learned":
            lbl.setText(str(_count(s, "KnownWords")))
        elif key == "lang/Group fluency by race":
            groups = s.dig("KnownWordGroups", default=[])
            if isinstance(groups, list) and groups:
                width = max(len(g.get("Races", [])) for g in groups
                            if isinstance(g, dict))
                counts = [0] * width
                for g in groups:
                    for i, known in enumerate(g.get("Races", [])):
                        counts[i] += 1 if known else 0
                lbl.setText("  ".join(f"R{i+1}: {c}" for i, c in
                                      enumerate(counts)))
            else:
                lbl.setText("none recorded")

    # stats table: only non-zero counters, grouped
    form = win._ov.get("stats_form")
    if form is None:
        return
    while form.rowCount():
        form.removeRow(0)
    groups = s.dig("Stats", default=[])
    shown = 0
    for gi, grp in enumerate(groups):
        if not isinstance(grp, dict):
            continue
        entries = [r for r in grp.get("Stats", [])
                   if isinstance(r, dict) and isinstance(r.get("Value"), dict)
                   and r["Value"]]
        if not entries:
            continue
        gid = grp.get("GroupId", f"GROUP {gi}")
        if len(groups) > 1:
            form.addRow(QLabel(f"<u>{gid.lstrip('^').title()}</u>"), QLabel(""))
        for r in entries:
            val = r["Value"].get("IntValue", r["Value"].get("FloatValue", "?"))
            form.addRow(QLabel(_pretty_stat(r.get("Id", "?"))),
                        QLabel(f"{val:,}" if isinstance(val, int) else str(val)))
            shown += 1
    if not shown:
        form.addRow(QLabel("<i>No non-zero stats recorded.</i>"), QLabel(""))