#!/usr/bin/env python3
"""NMS save editor entry point."""
import sys
from PySide6.QtWidgets import QApplication
from editor import MainWindow


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()