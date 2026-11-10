"""Editor shell: profile discovery, slot lifecycle, tab mounting, saving."""
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox, QLabel, QMainWindow, QTabWidget, QToolBar,
)

import decode
import discovery
import tabs
from mapping import KeyMap
from session import SaveSession

APP_DIR = Path(__file__).resolve().parent


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NMS Save Editor")
        self.resize(1100, 720)
        self.session = None
        self.keymap = None
        self._refreshers = []
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
                f'{pf["account"]}  ({stamp:%Y-%m-%d %H:%M})', pf["path"])
        self.combo_profile.setCurrentIndex(0)   # triggers _on_profile

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
        self.tabs_widget = QTabWidget()
        self.setCentralWidget(self.tabs_widget)
        self._refreshers = []
        for title, widget, refresher in tabs.load_tabs(self):
            self.tabs_widget.addTab(widget, title)
            if refresher:
                self._refreshers.append(refresher)

    def _refresh_all(self):
        for fn in self._refreshers:
            fn(self)

    # ------------------------------------------------------------ events
    def _on_profile(self, _idx):
        path = self.combo_profile.currentData()
        if not path:
            return
        self.session = SaveSession(path, self.keymap)
        self.combo_slot.blockSignals(True)
        self.combo_slot.clear()
        for slot_path, mtime in self.session.list_slots():
            self.combo_slot.addItem(discovery.slot_name(slot_path),
                                    slot_path)
        self.combo_slot.blockSignals(False)
        if self.combo_slot.count():
            self.combo_slot.setCurrentIndex(0)

    def _on_slot(self, _idx):
        path = self.combo_slot.currentData()
        if not (self.session and path):
            return
        try:
            report = self.session.load_slot(path)
        except decode.DecodeError as e:
            self.statusBar().showMessage(
                f"Decode failed: {e.report.get('failure', e)}")
            self._refresh_all()      # tabs reset to their empty state
            return
        self._refresh_all()
        self.act_save.setEnabled(True)
        self.statusBar().showMessage(
            f"Loaded {Path(path).name} via '{self.session.method}' "
            f"({report.get('doc_count', 1)} doc).")

    def _mark_dirty(self, _=None):
        if self.session:
            self.session.mark_dirty()

    def save_now(self):
        if self.session:
            self.statusBar().showMessage(self.session.save())
            self._refresh_all()      # current values repaint from source