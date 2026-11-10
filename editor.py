"""Skeleton tabbed UI: layered views over one loaded save."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QTabWidget, QToolBar, QTreeView, QVBoxLayout, QWidget,
)

import decode
import discovery
from jsonmodel import JsonModel
from mapping import KeyMap
from session import SaveSession

APP_DIR = Path(__file__).resolve().parent

# (title, what it will show, phase) -- stubs until their phase lands
STUB_TABS = [
    ("Suit & Inventory",
     "Exosuit slot grid: general / tech / cargo, slot classes, damage.",
     "Phase 1"),
    ("Language",
     "Learned words per alien race, per word group.", "Phase 4"),
    ("Companions",
     "Pets: trust, traits, eggs, accessories, unlocked slots.", "Phase 3"),
    ("Planet-side",
     "Ground/sea vehicles, settlements, bases & storage chests.", "Phase 3-4"),
    ("Starship",
     "Ship roster + active ship: inventory, health, class, seeds.", "Phase 2"),
    ("Multitool",
     "Tool roster + active tool: inventory, stats, archived tools.", "Phase 2"),
    ("Fleet",
     "Freighter, frigates, squadron pilots, fleet expeditions.", "Phase 3"),
    ("Progress",
     "Missions, milestones, expedition stage state, discoveries.", "Phase 4"),
    ("Account",
     "accountdata.hg: expedition rewards, entitlements, platform history.",
     "Phase 5"),
]


class _SignalStub:
    def __init__(self, fn):
        self._fn = fn
    def emit(self, *a):
        self._fn(*a)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NMS Save Editor")
        self.resize(1100, 720)
        self.session = None
        self.keymap = None
        self._auto_keymap()
        self._build_toolbar()
        self._build_tabs()
        self.statusBar().showMessage("Searching for saves…")
        self._autodetect()

    # ------------------------------------------------------------ startup
    def _auto_keymap(self):
        for name in ("data/keys_all.json", "data/keys_save.json"):
            p = APP_DIR / name
            if p.is_file():
                try:
                    self.keymap = KeyMap.load(str(p))
                    return
                except Exception:
                    pass

    def _autodetect(self):
        self.combo_profile.clear()
        profiles = discovery.find_profiles()
        if not profiles:
            self.statusBar().showMessage(
                "No saves found automatically -- pick the folder manually.")
            return
        for pf in profiles:
            stamp = datetime.fromtimestamp(pf["latest_mtime"])
            self.combo_profile.addItem(
                f'{pf["account"]}  ({stamp:%Y-%m-%d %H:%M})',
                pf["path"])
        self.combo_profile.setCurrentIndex(0)   # newest activity first
        self._on_profile(0)

    # ----------------------------------------------------------- toolbar
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.combo_profile = QComboBox()
        self.combo_profile.setMinimumWidth(340)
        self.combo_profile.currentIndexChanged.connect(self._on_profile)
        tb.addWidget(QLabel(" Profile: "))
        tb.addWidget(self.combo_profile)

        self.combo_slot = QComboBox()
        self.combo_slot.setMinimumWidth(160)
        self.combo_slot.currentIndexChanged.connect(self._on_slot)
        tb.addWidget(QLabel(" Slot: "))
        tb.addWidget(self.combo_slot)

        self.act_save = QAction("Save", self)
        self.act_save.triggered.connect(self.save_now)
        self.act_save.setEnabled(False)
        tb.addAction(self.act_save)

    # -------------------------------------------------------------- tabs
    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._tab_overview(), "Overview")
        for title, blurb, phase in STUB_TABS:
            self.tabs.addTab(self._stub_tab(title, blurb, phase), title)
        self.tabs.addTab(self._tab_raw(), "Raw JSON")

    def _stub_tab(self, title, blurb, phase):
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel(f"<big><b>{title}</b></big><br><br>{blurb}"
                     f"<br><br><i>Scheduled: {phase}</i>")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 0, Qt.AlignTop)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------- overview
    def _tab_overview(self):
        self.overview_host = QWidget()
        self.overview_lay = QVBoxLayout(self.overview_host)
        self.overview_form = QFormLayout()
        self.overview_lay.addLayout(self.overview_form)
        self.overview_lay.addStretch(1)
        return self.overview_host

    def _overview_set(self, label, value):
        # remove any existing row with this label, then append
        for i in range(self.overview_form.rowCount()):
            if self.overview_form.itemAt(i, QFormLayout.LabelRole) is not None:
                pass
        self.overview_form.addRow(QLabel(f"<b>{label}</b>"), QLabel(str(value)))

    def _populate_overview(self):
        while self.overview_form.count():
            item = self.overview_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        s = self.session
        if not s or not s.view:
            return
        secs = s.playtime or 0
        self._overview_set("Format", f"{s.method}, "
                          f"{s.report.get('doc_count', 1)} doc(s)")
        self._overview_set("Play time", f"{secs:,} s  (~{secs/3600:.1f} h)")
        self._overview_set("Units", f"{s.units:,}")
        self._overview_set("Nanites", f"{s.nanites:,}")
        self._overview_set("Quicksilver", f"{s.quicksilver:,}")
        self._overview_set("Health", s.health)
        self._overview_set("Shield", s.shield)

    # ----------------------------------------------------------- raw tab
    def _tab_raw(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        hb = QHBoxLayout()
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Filter keys…")
        hb.addWidget(QLabel("Filter"), 0)
        hb.addWidget(self.edit_filter, 1)
        lay.addLayout(hb)

        self.tree_json = QTreeView()
        lay.addWidget(self.tree_json, 1)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(500)
        self._filter_timer.timeout.connect(
            lambda: self._set_filter(self.edit_filter.text()))
        self.edit_filter.textChanged.connect(lambda _: self._filter_timer.start())
        return w

    def _set_filter(self, text):
        model = self.tree_json.model()
        if isinstance(model, QSortFilterProxyModel):
            model.setFilterFixedString(text)
            if text:
                self.tree_json.expandAll()

    def _populate_raw(self):
        if not self.session or not self.session.view:
            return
        obj = (self.session.view[0]
               if len(self.session.view) == 1 else self.session.view)
        model = JsonModel(obj, self.keymap)
        model.edited = _SignalStub(self._mark_dirty)
        proxy = QSortFilterProxyModel()
        proxy.setFilterKeyColumn(0)
        proxy.setRecursiveFilteringEnabled(True)
        proxy.setSourceModel(model)
        self.tree_json.setModel(proxy)
        self.tree_json.expandToDepth(0)

    # ------------------------------------------------------------ events
    def _on_profile(self, _idx):
        path = self.combo_profile.currentData()
        if not path:
            return
        self.session = SaveSession(path, self.keymap)
        self.combo_slot.blockSignals(True)
        self.combo_slot.clear()
        for slot_path, mtime in self.session.list_slots():
            label = discovery.slot_name(slot_path)
            self.combo_slot.addItem(label, slot_path)
        self.combo_slot.blockSignals(False)
        if self.combo_slot.count():
            self.combo_slot.setCurrentIndex(0)   # triggers _on_slot

    def _on_slot(self, _idx):
        path = self.combo_slot.currentData()
        if not (self.session and path):
            return
        try:
            report = self.session.load_slot(path)
        except decode.DecodeError as e:
            self.statusBar().showMessage(
                f"Decode failed: {e.report.get('failure', e)}")
            self._populate_overview()
            self._populate_raw()
            return
        self._populate_overview()
        self._populate_raw()
        self.act_save.setEnabled(True)
        self.statusBar().showMessage(
            f"Loaded {Path(path).name} via '{self.session.method}' "
            f"({report.get('doc_count', 1)} doc). Edits in Raw JSON are live.")

    def _mark_dirty(self, _=None):
        if self.session:
            self.session.mark_dirty()

    def save_now(self):
        if self.session:
            self.statusBar().showMessage(self.session.save())