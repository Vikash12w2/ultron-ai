from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from config import ASSETS

C = {
    "bg": "#0B0E13", "panel": "#0E1218", "card": "#11151C", "raised": "#171C25", "line": "#232A35",
    "text": "#E8EAEE", "muted": "#A3ACBA", "dim": "#8A94A5", "accent": "#E5484D", "button": "#C62F33",
    "blue": "#5AA9FF", "amber": "#F2C14E", "orange": "#FF9446", "user": "#1C2330",
}

STYLE = f"""
QWidget {{ background: {C['bg']}; color: {C['text']}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 14px; }}
QFrame#panel {{ background: {C['panel']}; }}
QFrame#sidebar {{ background: {C['panel']}; border-right: 1px solid {C['line']}; }}
QFrame#right {{ background: {C['panel']}; border-left: 1px solid {C['line']}; }}
QFrame#header {{ background: {C['panel']}; border-bottom: 1px solid {C['line']}; }}
QFrame#card {{ background: {C['card']}; border: 1px solid {C['line']}; border-radius: 10px; }}
QLabel#section {{ color: {C['dim']}; font-size: 11px; font-weight: 600; letter-spacing: 1px; background: transparent; }}
QLabel#muted {{ color: {C['muted']}; background: transparent; }}
QLabel {{ background: transparent; }}
QPushButton {{ background: {C['raised']}; border: 1px solid {C['line']}; border-radius: 10px; padding: 9px 14px; }}
QPushButton:hover {{ background: #1F2631; }}
QPushButton:disabled {{ color: #5d6573; }}
QPushButton#primary {{ background: {C['button']}; border: 0; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {C['accent']}; }}
QPushButton#newchat {{ background: #1A1214; border: 1px solid #3A2326; color: #FFD9DA; font-weight: 600; }}
QPushButton#link {{ background: transparent; border: 0; color: #7DBBFF; text-align: left; padding: 4px; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{ background: {C['card']}; border: 1px solid {C['line']};
    border-radius: 10px; padding: 8px; color: {C['text']}; selection-background-color: #2b3a52; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QListWidget::item {{ padding: 10px; border-radius: 8px; color: #B7BFCC; }}
QListWidget::item:selected {{ background: #1A202A; color: {C['text']}; }}
QTextBrowser {{ background: {C['bg']}; border: 0; }}
QProgressBar {{ background: #1E2530; border: 0; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {C['blue']}; border-radius: 3px; }}
QCheckBox {{ background: transparent; spacing: 8px; }}
QTableWidget {{ background: {C['card']}; gridline-color: {C['line']}; border: 1px solid {C['line']}; }}
QHeaderView::section {{ background: {C['panel']}; color: {C['muted']}; border: 0; padding: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2A3240; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QDialog {{ background: {C['card']}; }}
"""


def icon(name: str, color: str = C["text"], size: int = 20) -> QIcon:
    from PySide6.QtSvg import QSvgRenderer
    path = ASSETS / "icons" / f"{name}.svg"
    if not path.exists():
        return QIcon()
    data = path.read_text(encoding="utf-8").replace("currentColor", color).encode()
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(data)).render(painter)
    painter.end()
    return QIcon(pix)
