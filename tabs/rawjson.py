"""Raw JSON tab: editable tree with debounced recursive filtering."""
from PySide6.QtCore import QSortFilterProxyModel, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QTreeView, QVBoxLayout, QWidget,
)

from jsonmodel import JsonModel


class _SignalStub:
    def __init__(self, fn):
        self._fn = fn

    def emit(self, *a):
        self._fn(*a)


def build(win):
    w = QWidget()
    lay = QVBoxLayout(w)
    hb = QHBoxLayout()
    win.edit_filter = QLineEdit()
    win.edit_filter.setPlaceholderText("Filter keys…")
    hb.addWidget(QLabel("Filter"), 0)
    hb.addWidget(win.edit_filter, 1)
    lay.addLayout(hb)

    win.tree_json = QTreeView()
    lay.addWidget(win.tree_json, 1)

    timer = QTimer(win)
    timer.setSingleShot(True)
    timer.setInterval(500)
    timer.timeout.connect(
        lambda: _set_filter(win, win.edit_filter.text()))
    win.edit_filter.textChanged.connect(lambda _: timer.start())
    return w


def refresh(win):
    if not (win.session and win.session.view):
        return
    view = win.session.view
    obj = view[0] if len(view) == 1 else view
    model = JsonModel(obj, win.keymap)
    model.edited = _SignalStub(win._mark_dirty)
    proxy = QSortFilterProxyModel()
    proxy.setFilterKeyColumn(0)
    proxy.setRecursiveFilteringEnabled(True)
    proxy.setSourceModel(model)
    win.tree_json.setModel(proxy)
    win.tree_json.expandToDepth(0)


def _set_filter(win, text):
    model = win.tree_json.model()
    if isinstance(model, QSortFilterProxyModel):
        model.setFilterFixedString(text)
        if text:
            win.tree_json.expandAll()