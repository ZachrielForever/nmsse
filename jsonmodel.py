"""Recursive read/write tree model over decoded JSON documents."""
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt


class _Node:
    __slots__ = ("container", "key", "parent", "row", "_kids", "_loaded",
                 "forced")

    def __init__(self, container, key, parent=None, row=0, forced=None):
        self.container = container      # dict or list that holds us
        self.key = key                  # dict key or list index
        self.parent = parent
        self.row = row
        self._kids = []
        self._loaded = False
        self.forced = forced            # set only on the synthetic root

    def value(self):
        if self.forced is not None:
            return self.forced
        try:
            return self.container[self.key]
        except (KeyError, IndexError):
            return None

    def populate(self):
        if self._loaded:
            return
        v = self.value()
        kids = []
        if isinstance(v, dict):
            for r, k in enumerate(v):
                kids.append(_Node(v, k, self, r))
        elif isinstance(v, list):
            for r in range(len(v)):
                kids.append(_Node(v, r, self, r))
        self._kids = kids
        self._loaded = True


class JsonModel(QAbstractItemModel):
    """Editable tree over a dict/list/scalar. keymap kept for API compat."""

    def __init__(self, obj, keymap=None, parent=None):
        super().__init__(parent)
        self.keymap = keymap
        self.edited = None              # editor assigns a SignalStub
        if not isinstance(obj, (dict, list)):
            obj = {"value": obj}
        # Synthetic root: forced to the doc; its children ARE the top level.
        self._root = _Node(None, None, None, 0, forced=obj)
        self._root.populate()

    # ------------------------------------------------------ Qt plumbing
    def columnCount(self, parent=None):
        return 2

    def rowCount(self, parent=None):
        if parent is None or not parent.isValid():
            return len(self._root._kids)
        node = parent.internalPointer()
        node.populate()
        return len(node._kids)

    def index(self, row, column, parent=None):
        if parent is None or not parent.isValid():
            if 0 <= row < len(self._root._kids):
                return self.createIndex(row, column, self._root._kids[row])
            return QModelIndex()
        p = parent.internalPointer()
        p.populate()
        if row < 0 or row >= len(p._kids):
            return QModelIndex()
        return self.createIndex(row, column, p._kids[row])

    def parent(self, index):
        node = index.internalPointer() if index.isValid() else self._root
        p = node.parent
        if p is None or p is self._root:
            return QModelIndex()
        return self.createIndex(p.row, 0, p)

    def hasChildren(self, parent=None):
        if parent is None or not parent.isValid():
            return bool(self._root._kids)
        return isinstance(parent.internalPointer().value(), (dict, list))

    # ------------------------------------------------------ display
    @staticmethod
    def scalar_repr(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "null"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return "{...}"
        if isinstance(v, list):
            return "[...]"
        return str(v)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        node = index.internalPointer()
        if index.column() == 0:
            k = node.key
            return f"[{k}]" if isinstance(node.container, list) else str(k)
        v = node.value()
        if role == Qt.EditRole and isinstance(v, (dict, list)):
            return None
        return self.scalar_repr(v)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ("Key", "Value")[section]
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 1:
            v = index.internalPointer().value()
            if not isinstance(v, (dict, list)):
                base |= Qt.ItemIsEditable
        return base

    # ------------------------------------------------------ editing
    @staticmethod
    def _parse(text, old):
        if isinstance(old, bool):
            t = text.strip().lower()
            if t in ("true", "1", "yes"):
                return True
            if t in ("false", "0", "no"):
                return False
            raise ValueError("not a bool")
        if isinstance(old, int):
            return int(text)
        if isinstance(old, float):
            return float(text)
        return text                     # strings (incl. NMS "0x.." forms)

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or index.column() != 1:
            return False
        node = index.internalPointer()
        old = node.value()
        if isinstance(old, (dict, list)):
            return False
        try:
            new = self._parse(value, old)
        except ValueError:
            return False
        node.container[node.key] = new
        self.dataChanged.emit(index, index)
        if self.edited is not None:
            self.edited.emit()
        return True