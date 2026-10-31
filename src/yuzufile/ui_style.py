"""Silver tool windows and sculpted controls inspired by Tangerine."""
from string import Template
from PySide6.QtGui import QColor, QPalette

COLORS = {'canvas': '#f6f6f6',
 'surface': '#ffffff',
 'text': '#454545',
 'muted': '#737373',
 'icon': '#707070',
 'border': '#dddddd',
 'border_hover': '#bcbcbc',
 'shadow': '#d3d3d3',
 'icon_well': '#e9e9e9',
 'hover': '#e8e8e8',
 'brand': '#ed6b2e',
 'accent': '#d65b25',
 'accent_hover': '#bf4e1c',
 'accent_pressed': '#a84016',
 'accent_soft': '#fff0e7',
 'on_accent': '#ffffff',
 'primary': '#e0e0e0',
 'primary_hover': '#eeeeee',
 'primary_pressed': '#cecece',
 'on_primary': '#292929',
 'disabled': '#939393',
 'disabled_surface': '#e7e7e7',
 'progress': '#ed6b2e',
 'progress_track': '#e0e0e0',
 'success': '#287a57',
 'success_soft': '#edf5ee',
 'error': '#b73c32',
 'error_soft': '#fbefed'}


def light_palette():
    """Explicit colors for native controls even when Windows uses dark mode."""
    palette = QPalette()
    roles = {
        'Window': 'canvas', 'WindowText': 'text', 'Base': 'surface',
        'AlternateBase': 'canvas', 'Text': 'text', 'Button': 'surface',
        'ButtonText': 'text', 'ToolTipBase': 'surface', 'ToolTipText': 'text',
        'Highlight': 'hover', 'HighlightedText': 'text',
        'PlaceholderText': 'muted', 'Light': 'surface', 'Mid': 'border',
        'Dark': 'muted', 'Shadow': 'border',
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for role, token in roles.items():
            palette.setColor(group, getattr(QPalette.ColorRole, role), QColor(COLORS[token]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS['disabled']))
    return palette


POPUP_STYLE = Template("""
QListView, QListView::viewport { background: $surface; color: $text; }
QListView { border: 0; padding: 0; outline: 0; }
QListView::item { background: $surface; color: $text; padding: 10px 12px; border: 0; border-radius: 9px; }
QListView::item:selected, QListView::item:hover { background: $hover; color: $text; }
QListView::item:disabled { color: $disabled; }
""").substitute(COLORS)


SHELL_STYLE = """
QPushButton { background:#e9e9e9; color:#454545; border:1px solid #e3e3e3;
    border-radius:9px; padding:7px 12px; }
QPushButton:hover { background:#dedede; border-color:#d1d1d1; }
QPushButton:pressed { background:#d3d3d3; border-color:#c8c8c8; }
QPushButton:focus { border-color:#b57959; }
QPushButton:disabled { background:#eeeeee; color:#969696; border-color:#dfdfdf; }
QPushButton#primary { background:#dedede; color:#3f3f3f; border:1px solid #d9d9d9;
    border-radius:9px; font-weight:600; padding:8px 16px; }
QPushButton#primary:enabled:hover { background:#d2d2d2; border-color:#c7c7c7; }
QPushButton#primary:enabled:pressed { background:#c6c6c6; }
QPushButton#primary:enabled:focus { border-color:#b57959; }
QPushButton#primary:disabled { background:#e5e5e5; color:#9b9b9b; border-color:#dfdfdf; }
QPushButton#iconButton { background:transparent; border:1px solid transparent;
    padding:7px; border-radius:8px; }
QPushButton#iconButton:hover { background:#e8e8e8; border-color:transparent; }
QPushButton#iconButton:focus { border-color:transparent; }
QPushButton#iconButton[keyboardFocus="true"] { border-color:#a36c4e; }
QPushButton#backToTools { background:#f7f7f7; border:1px solid #d0d0d0;
    border-radius:9px; padding:7px 11px; font-weight:500; }
QPushButton#backToTools:hover { background:#ffffff; border-color:#bdbdbd; }
QPushButton#backToTools:pressed { background:#dedede; }
QPushButton#text,QPushButton#link,QPushButton#remove { background:transparent; border:0; }
QPushButton#text:hover,QPushButton#link:hover,QPushButton#remove:hover { background:#ececec; }
QComboBox,QLineEdit,QDoubleSpinBox,QSpinBox { background:#f0f0f0; color:#454545;
    border:1px solid #e4e4e4; border-radius:9px; padding:6px 10px; }
QComboBox:hover,QLineEdit:hover { border-color:#bfbfbf; }
QComboBox:focus,QLineEdit:focus { border-color:#b57959; }
QDoubleSpinBox QLineEdit,QSpinBox QLineEdit { background:transparent; border:0; padding:0; }
QComboBox:disabled { background:#efefef; color:#969696; border-color:#dfdfdf; }
QFrame#segmented { background:#e5e5e5; border:0; border-radius:9px; }
QPushButton#segment { background:transparent; border:1px solid transparent;
    border-radius:7px; padding:6px 11px; color:#606060; }
QPushButton#segment:checked { background:#cbcbcb; border-color:#c6c6c6; color:#3f3f3f; }
QPushButton#segment:hover { background:#dedede; }
QLabel#shellTitle { font-size:14px; font-weight:600; }
QLabel#toolWindowTitle { font-size:16px; font-weight:600; color:#484848; }
QPushButton#toolClose { background:#e9e9e9; border:0; border-radius:15px; padding:0; }
QPushButton#toolClose:hover { background:#dedede; }
QLabel#muted { color:#737373; font-size:12px; }
QLabel#filename { font-weight:600; }
QListWidget { background:#fafafa; border:1px solid #dddddd; border-radius:11px; }
QListWidget::item { border:0; border-bottom:1px solid #e6e6e6; }
QCheckBox { spacing:8px; font-weight:400; }
QCheckBox::indicator { width:17px; height:17px; border-radius:5px;
    border:1px solid #b6b6b6; background:#fdfdfd; }
QCheckBox::indicator:checked { background:#686868; border-color:#686868; }
QFrame#optionsPanel,QFrame#actionDock { background:transparent; border:0; }
QWidget#shellForm { background:transparent; }
QToolTip { color:#454545; background:#fcfcfc; border:1px solid #d4d4d4; padding:5px; }
"""

STYLE = Template("""
QMainWindow, QWidget#root { background: $canvas; }
QWidget { color: $text; font-family: 'Segoe UI'; font-size: 13px; }
QLabel { background: transparent; }
QWidget#navigation { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fafafa,stop:1 #eeeeee); border-bottom: 1px solid $border; }
QLabel#brand { font-size: 17px; font-weight: 600; letter-spacing: -0.4px; }
QLabel#heading { font-size: 19px; font-weight: 600; letter-spacing: -0.3px; }
QLabel#hero { font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }
QLabel#brandmark { background: $brand; border-radius: 9px; }
QLabel#uploadIcon { background: $icon_well; border: 1px solid $border; border-radius: 16px; }
QFrame#optionsPanel { background: #f6f6f6; border: 1px solid $border; border-top-color: #ffffff; border-radius: 13px; }
QFrame#actionDock { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f7f7f7,stop:1 #ededed); border: 0; border-top: 1px solid $border; }
QLabel#section { font-size: 13px; font-weight: 600; }
QLabel#muted { color: $muted; font-size: 12px; }
QLabel#filename { font-weight: 600; }
QFrame#panel { background: #f8f8f8; border: 1px solid $border; border-radius: 14px; }
QFrame#divider { background: $border; border: 0; }
QFrame#historyRow, QFrame#queueRow { background: transparent; border: 0; border-bottom: 1px solid $border; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #e9e9e9); border: 1px solid #cecece; border-top-color: #ffffff; border-bottom-color: #bdbdbd; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #f1f1f1); border-color: $border_hover; }
QPushButton:focus { border-color: $accent; }
QPushButton#pageTool:checked { background: $accent_soft; border-color: $accent; color: $accent; }
QPushButton:disabled { color: $disabled; border-color: $border; background: $canvas; }
QPushButton#nav { border: 1px solid transparent; border-radius: 7px; background: transparent; color: $muted; padding: 6px 14px; }
QPushButton#nav:checked { color: $text; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #e0e0e0); border-color: #cccccc; border-top-color:#ffffff; font-weight: 600; }
QPushButton#text, QPushButton#link, QPushButton#remove { border: 0; background: transparent; padding: 5px 7px; }
QPushButton#text { color: $muted; }
QPushButton#link { color: $accent; }
QPushButton#link:disabled, QPushButton#text:disabled { color: $disabled; }
QPushButton#remove { padding: 3px; }
QPushButton#iconButton { border: 0; background: transparent; padding: 8px; border-radius: 9px; }
QPushButton#iconButton:enabled:hover { background: $hover; }
QPushButton#iconButton:focus { border: 1px solid $accent; }
QPushButton#iconButton[danger="true"]:hover { background: $error_soft; }
QPushButton#retry { color: $accent; border-color: $accent_soft; }
QPushButton#upload { background: transparent; border: 0; padding: 0; }
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fefefe,stop:1 #d6d6d6); color: $on_primary; border: 1px solid #bcbcbc; border-top-color: #ffffff; border-radius: 9px; font-weight: 600; padding: 8px 18px; }
QPushButton#primary:enabled:hover { background: $primary_hover; }
QPushButton#primary:enabled:focus { border-color: $brand; }
QPushButton#primary:disabled { background: $disabled_surface; color: $disabled; }
QCheckBox { spacing: 10px; padding: 3px 0; font-weight: 500; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid $disabled; border-radius: 4px; background: $surface; }
QCheckBox::indicator:checked { background: #626262; border-color: #535353; }
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e8e8e8,stop:1 #f9f9f9); border: 1px solid #d4d4d4; border-top-color:#c5c5c5; border-bottom-color:#ffffff; border-radius: 8px; padding: 7px 10px; }
QDoubleSpinBox QLineEdit, QSpinBox QLineEdit { background: transparent; border: 0; padding: 0; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button { width: 0; height: 0; border: 0; }
QComboBox { min-width: 110px; padding-right: 27px; }
QComboBox::drop-down { border: 0; width: 25px; }
QComboBox::down-arrow { image: none; }
QComboBox:disabled { background: $canvas; color: $muted; }
QListWidget { background: #f9f9f9; border: 1px solid $border; border-radius: 10px; outline: 0; }
QListWidget::item { border: 0; border-bottom: 1px solid $border; }
QListWidget::item:selected { background: $surface; color: $text; }
QLabel#chip { background: $icon_well; color: $muted; border-radius: 9px; padding: 4px 8px; font-size: 10px; }
QLabel#badge { border-radius: 10px; padding: 3px 8px; font-size: 11px; }
QProgressBar { border: 0; background: transparent; height: 22px; }
QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: $canvas; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: $border_hover; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: $surface; border: 1px solid $border; border-radius: 14px; padding: 7px; }
QMenu::item { padding: 9px 18px 9px 11px; border-radius: 8px; }
QMenu::item:selected { background: $accent_soft; }
QMenu::item:disabled { color: $disabled; }
QMenu::separator { background: $border; height: 1px; margin: 4px 0; }
QDialog { background: $canvas; }
QTextBrowser { background: $surface; border: 1px solid $border; border-radius: 14px; padding: 12px; }

QPushButton:pressed { background: $disabled_surface; }
QPushButton#primary:enabled:pressed { background: $primary_pressed; }
QPushButton#nav:hover { background: $hover; color: $text; }
QPushButton#text:hover, QPushButton#link:hover, QPushButton#remove:hover { background: $hover; }
QComboBox:focus, QLineEdit:focus { border-color: $accent; }
QComboBox:hover, QLineEdit:hover { border-color: $border_hover; }
QComboBox QAbstractItemView { background: $surface; color: $text; border: 1px solid $border; padding: 5px; selection-background-color: $accent_soft; selection-color: $text; outline: 0; }
QCheckBox::indicator { border-radius: 5px; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:disabled { background: $canvas; border-color: $border; }
QSlider::groove:horizontal { height: 5px; background: $disabled_surface; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { background: $surface; border: 1px solid $border_hover; width: 17px; margin: -7px 0; border-radius: 9px; }
QFrame#segmented { background: #dddddd; border:1px solid #d1d1d1; border-bottom-color:#ffffff; border-radius:7px; }
QPushButton#segment { background:transparent; border:1px solid transparent; border-radius:5px; padding:5px 12px; color:$muted; }
QPushButton#segment:checked { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fafafa,stop:1 #e5e5e5); border-color:#c7c7c7; border-top-color:#ffffff; color:$text; }
""").substitute(COLORS)
