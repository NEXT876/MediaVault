import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from gui.main_window import MainWindow

# Ein einfaches, modernes Dark-Theme für PyQt6
DARK_STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: Arial;
}
QLineEdit, QTextEdit, QComboBox {
    background-color: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px;
}
QPushButton {
    background-color: #333;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px;
}
QPushButton:hover {
    background-color: #444;
}
QScrollBar:vertical {
    border: none;
    background: #1e1e1e;
    width: 12px;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 6px;
}
"""

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()