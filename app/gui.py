from __future__ import annotations
import sys
import os
import json
import logging
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPixmap, QImage, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QTabWidget,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QProgressBar,
    QDialog,
    QAbstractItemView,
    QScrollArea,
    QDateEdit,
    QSpinBox,
    QFrame,
    QSizePolicy,
    QStatusBar,
)

import fitz  # PyMuPDF

from .main import Pipeline
from .config import Config
from .parsers import PARSER_REGISTRY
from .pdf_reporter import PDFReporter
from .layout_preview import LayoutPreviewPanel, LayoutPreviewComboBox
from .athlete_manager import AthleteManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Theme / palette constants
# ---------------------------------------------------------------------------
RACEVAULT_QSS = """
/* ── Global ─────────────────────────────────────────────────────────────── */
QWidget {
    background-color: #16161A;
    color: #E8E8F0;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    outline: none;
}

/* ── Main window ─────────────────────────────────────────────────────────── */
QWidget#RaceVaultGUI {
    background-color: #16161A;
}

/* ── Tab Bar ─────────────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #2E2E38;
    border-radius: 6px;
    background-color: #1E1E26;
    margin-top: -1px;
}
QTabBar::tab {
    background-color: #16161A;
    color: #7878A0;
    padding: 10px 22px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.5px;
    min-width: 120px;
}
QTabBar::tab:selected {
    background-color: #1E1E26;
    color: #E87820;
    border-color: #2E2E38;
    border-bottom-color: #1E1E26;
}
QTabBar::tab:hover:!selected {
    background-color: #1E1E26;
    color: #C0C0D8;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {
    background-color: #2A2A34;
    color: #C8C8E0;
    border: 1px solid #3A3A4A;
    border-radius: 5px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 12px;
    min-height: 30px;
}
QPushButton:hover {
    background-color: #343444;
    color: #E8E8F0;
    border-color: #5A5A7A;
}
QPushButton:pressed {
    background-color: #1E1E2A;
    color: #E87820;
    border-color: #E87820;
}
QPushButton:disabled {
    background-color: #1E1E26;
    color: #484860;
    border-color: #2A2A38;
}

/* Primary accent buttons */
QPushButton#primary {
    background-color: #E87820;
    color: #0A0A0E;
    border: 1px solid #E87820;
    font-weight: 700;
}
QPushButton#primary:hover {
    background-color: #F08828;
    border-color: #F08828;
}
QPushButton#primary:pressed {
    background-color: #C06010;
    border-color: #C06010;
}

/* Danger button */
QPushButton#danger {
    background-color: #2A1A1A;
    color: #F87878;
    border-color: #5A2A2A;
}
QPushButton#danger:hover {
    background-color: #3A1E1E;
    border-color: #883030;
}

/* ── Line Edit ───────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #1E1E26;
    color: #E8E8F0;
    border: 1px solid #3A3A4A;
    border-radius: 5px;
    padding: 7px 12px;
    font-size: 13px;
    min-height: 30px;
    selection-background-color: #E87820;
    selection-color: #0A0A0E;
}
QLineEdit:focus {
    border-color: #E87820;
    background-color: #22222C;
}
QLineEdit::placeholder {
    color: #505070;
}

/* ── ComboBox ────────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #1E1E26;
    color: #E8E8F0;
    border: 1px solid #3A3A4A;
    border-radius: 5px;
    padding: 6px 12px;
    min-height: 30px;
    min-width: 120px;
}
QComboBox:hover {
    border-color: #5A5A7A;
}
QComboBox:focus {
    border-color: #E87820;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
    border-left: 2px solid #7878A0;
    border-bottom: 2px solid #7878A0;
    margin-right: 6px;
    transform: rotate(-45deg);
}
QComboBox QAbstractItemView {
    background-color: #22222C;
    color: #E8E8F0;
    border: 1px solid #3A3A4A;
    selection-background-color: #E87820;
    selection-color: #0A0A0E;
    outline: none;
}

/* ── Table ───────────────────────────────────────────────────────────────── */
QTableWidget {
    background-color: #1A1A22;
    color: #D8D8F0;
    border: 1px solid #2A2A38;
    border-radius: 6px;
    gridline-color: #242432;
    font-size: 12px;
    selection-background-color: #2E2840;
    selection-color: #E8E8F0;
    alternate-background-color: #1E1E28;
}
QTableWidget::item {
    padding: 6px 8px;
    border: none;
}
QTableWidget::item:selected {
    background-color: #2E2840;
    color: #E8E8F8;
}
QTableWidget::item:hover {
    background-color: #242434;
}
QHeaderView::section {
    background-color: #12121A;
    color: #E87820;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid #2A2A38;
    border-bottom: 1px solid #2A2A38;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}
QHeaderView::section:last {
    border-right: none;
}

/* ── Scroll Bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: #1A1A22;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #3A3A50;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #5A5A78;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar:horizontal {
    background-color: #1A1A22;
    height: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #3A3A50;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #5A5A78;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}
QScrollArea {
    border: none;
    background-color: transparent;
}

/* ── Progress Bar ────────────────────────────────────────────────────────── */
QProgressBar {
    background-color: #1A1A22;
    border: 1px solid #2A2A38;
    border-radius: 5px;
    text-align: center;
    color: #7878A0;
    font-size: 11px;
    max-height: 16px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #C06010, stop:1 #E87820);
    border-radius: 4px;
}

/* ── Text Edit ───────────────────────────────────────────────────────────── */
QTextEdit {
    background-color: #1A1A22;
    color: #C8D8C8;
    border: 1px solid #2A2A38;
    border-radius: 6px;
    padding: 8px;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    line-height: 1.5;
}
QTextEdit:focus {
    border-color: #E87820;
}

/* ── Labels ──────────────────────────────────────────────────────────────── */
QLabel {
    color: #9898B8;
    font-size: 12px;
    background: transparent;
}
QLabel#section_label {
    color: #E87820;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}
QLabel#value_label {
    color: #E8E8F8;
    font-size: 13px;
    font-weight: 600;
}
QLabel#info_label {
    color: #6868A0;
    font-size: 11px;
    padding: 2px 0;
}

/* ── Frames / Dividers ───────────────────────────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {
    color: #2A2A3A;
}

/* ── Dialog ──────────────────────────────────────────────────────────────── */
QDialog {
    background-color: #1E1E26;
}
QMessageBox {
    background-color: #1E1E26;
}
QMessageBox QLabel {
    color: #E8E8F0;
    font-size: 13px;
}
QMessageBox QPushButton {
    min-width: 80px;
}

/* ── Spin Box ────────────────────────────────────────────────────────────── */
QSpinBox {
    background-color: #1E1E26;
    color: #E8E8F0;
    border: 1px solid #3A3A4A;
    border-radius: 5px;
    padding: 6px 10px;
}
QSpinBox:focus {
    border-color: #E87820;
}

/* ── Check Box ───────────────────────────────────────────────────────────── */
QCheckBox {
    color: #C0C0D8;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background-color: #1E1E26;
    border: 2px solid #3A3A5A;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #E87820;
    border-color: #E87820;
}

/* ── Tool Tip ────────────────────────────────────────────────────────────── */
QToolTip {
    background-color: #22222C;
    color: #E8E8F0;
    border: 1px solid #E87820;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ── Input Dialog ────────────────────────────────────────────────────────── */
QInputDialog {
    background-color: #1E1E26;
}
"""


def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section_label")
    return lbl


def _make_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Plain)
    return sep


def _make_primary_button(text: str, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("primary")
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def _make_danger_button(text: str, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("danger")
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


class RaceVaultGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("RaceVaultGUI")
        self.setWindowTitle("RaceVault  ·  Race Results Vault")
        self.resize(1060, 680)
        self.setMinimumSize(820, 520)

        self.pipeline = Pipeline(Config())
        self.layout_display_names = {
            "layout_a": "layout_a",
            "layout_b": "layout_b",
            "layout_c": "layout_c",
            "layout_d": "layout_d",
        }
        self.layout_display_to_internal = {v: k for k, v in self.layout_display_names.items()}
        self.search_index: List[Dict[str, Any]] = []
        self.last_report_path: Optional[str] = None

        # Initialize athlete manager
        athletes_db_path = os.path.join(self.pipeline.config.output_dir, "athletes.json")
        self.athlete_manager = AthleteManager(self.pipeline.config.output_dir, athletes_db_path)

        self.setAcceptDrops(True)

        # ── Root layout ──────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────────────────
        header = self._build_header()
        root.addWidget(header)

        # ── Tabs ─────────────────────────────────────────────────────────────
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(False)
        root.addWidget(self.tabs)

        self.parsing_tab = QWidget()
        self.search_tab = QWidget()
        self.config_tab = QWidget()
        self.athlete_tab = QWidget()

        self._build_parsing_tab()
        self._build_search_tab()
        self._build_config_tab()
        self._build_athlete_tab()

        self.tabs.addTab(self.parsing_tab, "⬡  Parsing")
        self.tabs.addTab(self.search_tab, "◎  Search")
        self.tabs.addTab(self.athlete_tab, "⚑  Athletes")
        self.tabs.addTab(self.config_tab, "⚙  Data Files")

        # ── Status bar ───────────────────────────────────────────────────────
        self.status_bar_label = QLabel("Ready")
        self.status_bar_label.setObjectName("info_label")
        status_bar_widget = QWidget()
        status_bar_widget.setFixedHeight(28)
        status_bar_widget.setStyleSheet(
            "background-color:#111118; border-top:1px solid #252530;"
        )
        sb_layout = QHBoxLayout(status_bar_widget)
        sb_layout.setContentsMargins(12, 0, 12, 0)
        sb_layout.addWidget(self.status_bar_label)
        sb_layout.addStretch()
        self.status_bar_index_label = QLabel("")
        self.status_bar_index_label.setObjectName("info_label")
        sb_layout.addWidget(self.status_bar_index_label)
        root.addWidget(status_bar_widget)

        # ── Stub references needed by legacy methods ──────────────────────
        self.status_label = self.status_bar_label
        self.results_area = QTextEdit()          # hidden – kept for compat
        self.reparse_checkbox = QCheckBox()      # hidden – kept for compat

        self.refresh_search_index()
        self.refresh_output_json_list()
        self.refresh_athletes_list()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(
            "background-color: #0E0E14;"
            "border-bottom: 2px solid #E87820;"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 0, 18, 0)

        logo = QLabel("🏁  RACEVAULT")
        logo.setStyleSheet(
            "color:#E87820; font-size:17px; font-weight:800;"
            "letter-spacing:2.5px; background:transparent;"
        )
        layout.addWidget(logo)

        subtitle = QLabel("PDF Race Results Parser")
        subtitle.setStyleSheet(
            "color:#454568; font-size:12px; font-weight:500;"
            "background:transparent; margin-left:12px;"
        )
        layout.addWidget(subtitle)
        layout.addStretch()

        version = QLabel("v1.0")
        version.setStyleSheet(
            "color:#303050; font-size:11px; background:transparent;"
        )
        layout.addWidget(version)
        return header

    # ── Parsing Tab ───────────────────────────────────────────────────────────
    def _build_parsing_tab(self) -> None:
        layout = QVBoxLayout(self.parsing_tab)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        # Row 1: action buttons
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self.add_pdfs_button = _make_primary_button("＋  Add PDFs", "Import PDF files into the input folder")
        self.add_pdfs_button.clicked.connect(self.add_pdfs)
        top_layout.addWidget(self.add_pdfs_button)

        self.parse_selected_button = QPushButton("▶  Parse Selected")
        self.parse_selected_button.setToolTip("Parse highlighted PDFs")
        self.parse_selected_button.clicked.connect(self.parse_selected)
        top_layout.addWidget(self.parse_selected_button)

        self.parse_all_button = QPushButton("▶▶  Parse All")
        self.parse_all_button.setToolTip("Parse every PDF in the input folder")
        self.parse_all_button.clicked.connect(self.parse_all)
        top_layout.addWidget(self.parse_all_button)

        self.refresh_input_button = QPushButton("↺  Refresh")
        self.refresh_input_button.setToolTip("Reload input file list")
        self.refresh_input_button.clicked.connect(self.refresh_input_list)
        top_layout.addWidget(self.refresh_input_button)

        top_layout.addSpacing(16)

        # Year filter
        year_label = _make_section_label("Year:")
        year_label.setFixedWidth(38)
        top_layout.addWidget(year_label)
        self.year_filter_combo = QComboBox()
        self.year_filter_combo.setFixedWidth(100)
        self.year_filter_combo.addItem("All")
        self.year_filter_combo.setToolTip("Filter PDF list by year")
        self.year_filter_combo.currentTextChanged.connect(self.filter_by_year)
        top_layout.addWidget(self.year_filter_combo)

        top_layout.addSpacing(16)

        # Parser selector
        parser_label = _make_section_label("Layout:")
        parser_label.setFixedWidth(50)
        top_layout.addWidget(parser_label)
        self.layout_preview_panel = LayoutPreviewPanel()
        self.parser_selector = LayoutPreviewComboBox(self.layout_preview_panel)
        self.parser_selector.addItems([
            "Auto-detect",
            *[self.layout_display_names.get(key, key) for key in PARSER_REGISTRY],
        ])
        self.parser_selector.setFixedWidth(130)
        self.parser_selector.setToolTip("Force a parser layout or auto-detect")
        self.parser_selector.currentTextChanged.connect(self.layout_preview_panel.update_preview)
        top_layout.addWidget(self.parser_selector)
        top_layout.addWidget(self.layout_preview_panel)
        top_layout.addStretch()

        layout.addLayout(top_layout)

        # Row 2: table + PDF preview
        table_preview_layout = QHBoxLayout()
        table_preview_layout.setSpacing(12)

        # Left: PDF table
        table_container = QWidget()
        table_v = QVBoxLayout(table_container)
        table_v.setContentsMargins(0, 0, 0, 0)
        table_v.setSpacing(6)

        pdfs_lbl = _make_section_label("PDFs to Process")
        table_v.addWidget(pdfs_lbl)

        self.input_table = QTableWidget(0, 3)
        self.input_table.setHorizontalHeaderLabels(["Competition", "Year", "Status"])
        self.input_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.input_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.input_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.input_table.setAlternatingRowColors(True)
        self.input_table.verticalHeader().setVisible(False)
        self.input_table.verticalHeader().setDefaultSectionSize(32)
        self.input_table.selectionModel().selectionChanged.connect(self.on_pdf_selection_changed)
        table_v.addWidget(self.input_table)
        table_preview_layout.addWidget(table_container, 3)

        # Right: PDF preview
        preview_container = QWidget()
        preview_container.setStyleSheet(
            "background-color:#12121A; border:1px solid #252534; border-radius:6px;"
        )
        preview_v = QVBoxLayout(preview_container)
        preview_v.setContentsMargins(8, 8, 8, 8)
        preview_v.setSpacing(6)

        preview_lbl = _make_section_label("PDF Preview")
        preview_v.addWidget(preview_lbl)

        self.pdf_preview_scroll = QScrollArea()
        self.pdf_preview_scroll.setWidgetResizable(True)
        self.pdf_preview_scroll.setStyleSheet("border:none; background-color:transparent;")
        self.pdf_preview_label = QLabel("No PDF selected")
        self.pdf_preview_label.setAlignment(Qt.AlignCenter)
        self.pdf_preview_label.setStyleSheet(
            "color:#303050; font-size:11px; background:transparent;"
        )
        self.pdf_preview_scroll.setWidget(self.pdf_preview_label)
        preview_v.addWidget(self.pdf_preview_scroll)
        table_preview_layout.addWidget(preview_container, 1)

        layout.addLayout(table_preview_layout)

        # Progress bar
        progress_row = QHBoxLayout()
        prog_label = QLabel("Progress:")
        prog_label.setFixedWidth(60)
        progress_row.addWidget(prog_label)
        self.parsing_progress = QProgressBar()
        self.parsing_progress.setValue(0)
        self.parsing_progress.setTextVisible(True)
        self.parsing_progress.setFormat("%p%")
        progress_row.addWidget(self.parsing_progress)
        layout.addLayout(progress_row)

        self.refresh_input_list()

    # ── Search Tab ────────────────────────────────────────────────────────────
    def _build_search_tab(self) -> None:
        layout = QVBoxLayout(self.search_tab)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        # Control row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search race, athlete, file, date…")
        self.search_input.returnPressed.connect(self.perform_search)
        controls_layout.addWidget(self.search_input, 3)

        self.search_type_selector = QComboBox()
        self.search_type_selector.addItems([
            "All fields",
            "Race/Event",
            "Athlete Name",
            "Source file / Date",
        ])
        self.search_type_selector.setFixedWidth(160)
        controls_layout.addWidget(self.search_type_selector)

        self.search_button = _make_primary_button("⌕  Search")
        self.search_button.setFixedWidth(100)
        self.search_button.clicked.connect(self.perform_search)
        controls_layout.addWidget(self.search_button)

        self.refresh_button = QPushButton("↺  Refresh")
        self.refresh_button.setToolTip("Re-scan JSON output files")
        self.refresh_button.clicked.connect(self.refresh_search_index)
        controls_layout.addWidget(self.refresh_button)

        controls_layout.addSpacing(12)

        self.report_button = _make_primary_button("⬇  Generate PDF Report")
        self.report_button.setToolTip("Create a PDF report from the report box")
        self.report_button.clicked.connect(self.generate_pdf_report)
        controls_layout.addWidget(self.report_button)

        self.open_last_button = QPushButton("↗  Open Report")
        self.open_last_button.clicked.connect(self.open_report)
        self.open_last_button.setEnabled(False)
        controls_layout.addWidget(self.open_last_button)

        self.print_last_button = QPushButton("⎙  Print Report")
        self.print_last_button.clicked.connect(lambda: self.open_report(do_print=True))
        self.print_last_button.setEnabled(False)
        controls_layout.addWidget(self.print_last_button)

        layout.addLayout(controls_layout)

        self.search_info_label = QLabel("Use the search filters above to display results.")
        self.search_info_label.setObjectName("info_label")
        layout.addWidget(self.search_info_label)

        # Results table
        results_lbl = _make_section_label("Results")
        layout.addWidget(results_lbl)

        self.search_table = QTableWidget(0, 7)
        self.search_table.setHorizontalHeaderLabels([
            "Competition", "Distance", "Boat Class", "Athlete", "Time", "Pos.", "Date",
        ])
        self.search_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.search_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.search_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.search_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.search_table.setSortingEnabled(True)
        self.search_table.setAlternatingRowColors(True)
        self.search_table.verticalHeader().setVisible(False)
        self.search_table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.search_table)

        # Report box controls
        report_controls = QHBoxLayout()
        report_controls.setSpacing(8)
        self.add_to_report_button = QPushButton("＋  Add to Report Box")
        self.add_to_report_button.clicked.connect(self.add_selected_to_report_box)
        report_controls.addWidget(self.add_to_report_button)

        self.remove_from_report_button = _make_danger_button("－  Remove Selected")
        self.remove_from_report_button.clicked.connect(self.remove_selected_from_report_box)
        report_controls.addWidget(self.remove_from_report_button)

        self.clear_report_button = _make_danger_button("✕  Clear Box")
        self.clear_report_button.clicked.connect(self.clear_report_box)
        report_controls.addWidget(self.clear_report_button)

        report_controls.addStretch()
        layout.addLayout(report_controls)

        report_box_lbl = _make_section_label("Report Box")
        layout.addWidget(report_box_lbl)

        self.report_selection_table = QTableWidget(0, 7)
        self.report_selection_table.setHorizontalHeaderLabels([
            "Competition", "Distance", "Boat Class", "Athlete", "Time", "Pos.", "Date",
        ])
        self.report_selection_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.report_selection_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.report_selection_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.report_selection_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.report_selection_table.setSortingEnabled(False)
        self.report_selection_table.setAlternatingRowColors(True)
        self.report_selection_table.verticalHeader().setVisible(False)
        self.report_selection_table.verticalHeader().setDefaultSectionSize(30)
        self.report_selection_table.setMaximumHeight(180)
        layout.addWidget(self.report_selection_table)

    # ── Config Tab ────────────────────────────────────────────────────────────
    def _build_config_tab(self) -> None:
        layout = QVBoxLayout(self.config_tab)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.refresh_json_button = QPushButton("↺  Refresh")
        self.refresh_json_button.clicked.connect(self.refresh_output_json_list)
        buttons_layout.addWidget(self.refresh_json_button)

        self.view_json_button = QPushButton("⊞  View JSON")
        self.view_json_button.clicked.connect(self.view_selected_json)
        buttons_layout.addWidget(self.view_json_button)

        self.delete_json_button = _make_danger_button("✕  Delete Selected")
        self.delete_json_button.clicked.connect(self.delete_selected_json)
        buttons_layout.addWidget(self.delete_json_button)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        files_lbl = _make_section_label("Parsed JSON Files")
        layout.addWidget(files_lbl)

        self.json_table = QTableWidget(0, 4)
        self.json_table.setHorizontalHeaderLabels(["Filename", "Size", "Modified", "Path"])
        self.json_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.json_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.json_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.json_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.json_table.setAlternatingRowColors(True)
        self.json_table.verticalHeader().setVisible(False)
        self.json_table.verticalHeader().setDefaultSectionSize(30)
        self.json_table.itemDoubleClicked.connect(self.view_selected_json)
        layout.addWidget(self.json_table)

    # ── Athlete Tab ───────────────────────────────────────────────────────────
    def _build_athlete_tab(self) -> None:
        layout = QVBoxLayout(self.athlete_tab)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.rebuild_athletes_button = _make_primary_button("⟳  Rebuild Athletes Data")
        self.rebuild_athletes_button.setToolTip("Rebuild from all parsed JSON outputs")
        self.rebuild_athletes_button.clicked.connect(self.rebuild_athletes_from_outputs)
        controls_layout.addWidget(self.rebuild_athletes_button)

        self.refresh_athletes_button = QPushButton("↺  Refresh List")
        self.refresh_athletes_button.clicked.connect(self.refresh_athletes_list)
        controls_layout.addWidget(self.refresh_athletes_button)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        athletes_lbl = _make_section_label("Athletes")
        layout.addWidget(athletes_lbl)

        self.athletes_table = QTableWidget(0, 3)
        self.athletes_table.setHorizontalHeaderLabels(["Athlete Name", "Birth Date", "Age"])
        self.athletes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.athletes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.athletes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.athletes_table.setAlternatingRowColors(True)
        self.athletes_table.verticalHeader().setVisible(False)
        self.athletes_table.verticalHeader().setDefaultSectionSize(30)
        self.athletes_table.itemSelectionChanged.connect(self.on_athlete_selected)
        layout.addWidget(self.athletes_table)

        # Detail panel
        info_layout = QHBoxLayout()
        info_layout.setSpacing(14)

        # Best times
        times_container = QWidget()
        times_container.setStyleSheet(
            "background-color:#12121A; border:1px solid #252534; border-radius:6px;"
        )
        times_v = QVBoxLayout(times_container)
        times_v.setContentsMargins(10, 10, 10, 10)
        times_v.setSpacing(6)
        times_lbl = _make_section_label("Best Times")
        times_v.addWidget(times_lbl)
        self.athlete_times_text = QTextEdit()
        self.athlete_times_text.setReadOnly(True)
        self.athlete_times_text.setPlaceholderText("Select an athlete to see their times…")
        times_v.addWidget(self.athlete_times_text)
        info_layout.addWidget(times_container, 2)

        # Birth date editor
        editor_container = QWidget()
        editor_container.setStyleSheet(
            "background-color:#12121A; border:1px solid #252534; border-radius:6px;"
        )
        editor_v = QVBoxLayout(editor_container)
        editor_v.setContentsMargins(10, 10, 10, 10)
        editor_v.setSpacing(8)

        edit_lbl = _make_section_label("Edit Birth Date")
        editor_v.addWidget(edit_lbl)

        birth_row = QHBoxLayout()
        birth_label = QLabel("Date (YYYY-MM-DD):")
        birth_row.addWidget(birth_label)
        self.birth_date_input = QLineEdit()
        self.birth_date_input.setPlaceholderText("YYYY-MM-DD")
        birth_row.addWidget(self.birth_date_input)
        editor_v.addLayout(birth_row)

        age_row = QHBoxLayout()
        age_row.addWidget(QLabel("Calculated Age:"))
        self.age_display = QLabel("N/A")
        self.age_display.setObjectName("value_label")
        age_row.addWidget(self.age_display)
        age_row.addStretch()
        editor_v.addLayout(age_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.save_birth_date_button = _make_primary_button("✓  Save Date")
        self.save_birth_date_button.clicked.connect(self.save_athlete_birth_date)
        btn_row.addWidget(self.save_birth_date_button)
        self.clear_birth_date_button = _make_danger_button("✕  Clear Date")
        self.clear_birth_date_button.clicked.connect(self.clear_athlete_birth_date)
        btn_row.addWidget(self.clear_birth_date_button)
        editor_v.addLayout(btn_row)
        editor_v.addStretch()

        info_layout.addWidget(editor_container, 1)
        layout.addLayout(info_layout)

    # =========================================================================
    # All original logic methods below (unchanged)
    # =========================================================================

    def refresh_input_list(self) -> None:
        self.input_table.setSortingEnabled(False)
        self.input_table.setRowCount(0)

        input_path = Path(self.pipeline.config.input_dir)
        input_path.mkdir(parents=True, exist_ok=True)

        output_path = Path(self.pipeline.config.output_dir)
        parsed_files = {p.stem for p in output_path.glob("*.json")} if output_path.exists() else set()

        pdfs = sorted(input_path.glob("*.pdf"))
        years_set = set()

        for idx, p in enumerate(pdfs):
            stem = p.stem
            year = ""
            if len(stem) >= 4 and stem[-4:].isdigit():
                year = stem[-4:]
                years_set.add(year)

            status = "Parsed" if p.stem in parsed_files else "Waiting"

            comp_item = QTableWidgetItem(stem)
            comp_item.setData(Qt.UserRole, p.name)
            self.input_table.insertRow(idx)
            self.input_table.setItem(idx, 0, comp_item)
            self.input_table.setItem(idx, 1, QTableWidgetItem(year))

            status_item = QTableWidgetItem(status)
            if status == "Parsed":
                status_item.setForeground(QColor("#4ADE80"))
            elif status == "Waiting":
                status_item.setForeground(QColor("#7878A0"))
            self.input_table.setItem(idx, 2, status_item)

        self.input_table.setSortingEnabled(True)

        self.year_filter_combo.blockSignals(True)
        self.year_filter_combo.clear()
        self.year_filter_combo.addItem("All")
        self.year_filter_combo.addItems(sorted(years_set))
        self.year_filter_combo.blockSignals(False)
        self.filter_by_year()

    def filter_by_year(self) -> None:
        selected_year = self.year_filter_combo.currentText()
        for row in range(self.input_table.rowCount()):
            year_item = self.input_table.item(row, 1)
            if year_item is None:
                continue
            hide = (selected_year != "All" and year_item.text() != selected_year)
            self.input_table.setRowHidden(row, hide)

    def on_pdf_selection_changed(self) -> None:
        rows = sorted({item.row() for item in self.input_table.selectedItems()})
        if not rows:
            self.pdf_preview_label.setPixmap(QPixmap())
            self.pdf_preview_label.setText("No PDF selected")
            return
        first_row = rows[0]
        comp_item = self.input_table.item(first_row, 0)
        if comp_item:
            filename = comp_item.data(Qt.UserRole)
            pdf_path = os.path.join(self.pipeline.config.input_dir, filename)
            self.update_pdf_preview(pdf_path)

    def update_pdf_preview(self, pdf_path: str) -> None:
        try:
            if not os.path.exists(pdf_path):
                self.pdf_preview_label.setPixmap(QPixmap())
                self.pdf_preview_label.setText("PDF file not found")
                return
            doc = fitz.open(pdf_path)
            if doc.page_count == 0:
                doc.close()
                self.pdf_preview_label.setPixmap(QPixmap())
                self.pdf_preview_label.setText("PDF has no pages")
                return
            page = doc[0]
            mat = fitz.Matrix(4, 4)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("ppm")
            qimage = QImage()
            qimage.loadFromData(img_data)
            max_height = 500
            if qimage.height() > max_height:
                qimage = qimage.scaledToHeight(max_height, Qt.SmoothTransformation)
            pixmap = QPixmap.fromImage(qimage)
            self.pdf_preview_label.setPixmap(pixmap)
            doc.close()
        except Exception as exc:
            logger.exception(f"Error loading PDF preview for {pdf_path}")
            self.pdf_preview_label.setPixmap(QPixmap())
            self.pdf_preview_label.setText(f"Preview error:\n{str(exc)}")

    def add_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDFs to add", os.path.expanduser("~"), "PDF Files (*.pdf)")
        if not files:
            return
        added = 0
        for f in files:
            try:
                if not f.lower().endswith(".pdf"):
                    continue
                if os.path.getsize(f) == 0:
                    continue
                dest_dir = self.pipeline.config.input_dir
                basename = os.path.basename(f)
                dest = os.path.join(dest_dir, basename)
                output_conflict = os.path.exists(os.path.join(self.pipeline.config.output_dir, os.path.splitext(basename)[0] + ".json"))
                if os.path.exists(dest) or output_conflict:
                    continue
                shutil.copy2(f, dest)
                added += 1
            except Exception:
                logger.exception(f"Failed to add PDF: {f}")
        if added:
            QMessageBox.information(self, "Files Added", f"Added {added} PDF(s) to input folder.")
        self.refresh_input_list()

    def parse_selected(self) -> None:
        rows = sorted({item.row() for item in self.input_table.selectedItems()})
        if not rows:
            QMessageBox.information(self, "No Selection", "Select one or more PDFs to parse.")
            return
        file_paths = []
        for r in rows:
            comp_item = self.input_table.item(r, 0)
            if comp_item:
                filename = comp_item.data(Qt.UserRole)
                file_paths.append(os.path.join(self.pipeline.config.input_dir, filename))
        layout_override = self._selected_parser_override()
        self._process_file_list(file_paths, layout_override=layout_override)

    def parse_all(self) -> None:
        input_path = Path(self.pipeline.config.input_dir)
        pdfs = sorted([str(p) for p in input_path.glob("*.pdf")])
        if not pdfs:
            QMessageBox.information(self, "No PDFs", "No PDFs found in the input folder.")
            return
        layout_override = self._selected_parser_override()
        self._process_file_list(pdfs, layout_override=layout_override)

    def _selected_parser_override(self) -> Optional[str]:
        selection = self.parser_selector.currentText()
        if selection == "Auto-detect":
            return None
        return self.layout_display_to_internal.get(selection, selection)

    def _process_file_list(self, file_paths: List[str], layout_override: Optional[str] = None, move_parsed: Optional[bool] = False) -> None:
        total = len(file_paths)
        self.parsing_progress.setValue(0)
        for idx, pdf in enumerate(file_paths, start=1):
            filename = os.path.basename(pdf)
            for row in range(self.input_table.rowCount()):
                stored_filename = self.input_table.item(row, 0).data(Qt.UserRole)
                if stored_filename == filename:
                    parsing_item = QTableWidgetItem("Parsing…")
                    parsing_item.setForeground(QColor("#E8C040"))
                    self.input_table.setItem(row, 2, parsing_item)
                    break
            QApplication.processEvents()

            try:
                effective_move = move_parsed if move_parsed is not None else False
                result = self.pipeline.process_file(pdf, layout_override=layout_override, move_parsed=effective_move)
                status = "Parsed" if result.get("output_path") else "Error"
            except Exception as exc:
                logger.exception(f"Error parsing {pdf}")
                status = "Error"

            for row in range(self.input_table.rowCount()):
                stored_filename = self.input_table.item(row, 0).data(Qt.UserRole)
                if stored_filename == filename:
                    status_item = QTableWidgetItem(status)
                    if status == "Parsed":
                        status_item.setForeground(QColor("#4ADE80"))
                    elif status == "Error":
                        status_item.setForeground(QColor("#F87171"))
                    self.input_table.setItem(row, 2, status_item)
                    break

            pct = int((idx / total) * 100)
            self.parsing_progress.setValue(pct)
            QApplication.processEvents()

        self.parsing_progress.setValue(100)
        QApplication.processEvents()

        self.refresh_output_json_list()
        self.refresh_input_list()
        self.refresh_search_index()
        self.athlete_manager.rebuild_from_outputs()
        self.refresh_athletes_list()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        pdfs = [p for p in paths if p.lower().endswith('.pdf')]
        if not pdfs:
            return
        added = 0
        for f in pdfs:
            try:
                dest = os.path.join(self.pipeline.config.input_dir, os.path.basename(f))
                if os.path.exists(dest):
                    continue
                shutil.copy2(f, dest)
                added += 1
            except Exception:
                logger.exception(f"Failed to copy dropped file: {f}")
        if added:
            QMessageBox.information(self, "Files Added", f"Added {added} PDF(s) via drag-and-drop.")
        self.refresh_input_list()

    def run_pipeline(self) -> None:
        reparse_existing = self.reparse_checkbox.isChecked()
        mode_text = "including already parsed PDFs" if reparse_existing else "skipping already parsed PDFs"
        self.status_label.setText(f"Running pipeline ({mode_text})")
        QApplication.processEvents()
        try:
            exported_files = self.pipeline.run(reparse_existing=reparse_existing, move_parsed=False)
            reprocessed = len(exported_files)
            self.results_area.setPlainText(
                f"Pipeline completed. Processed {reprocessed} PDF(s).\n"
                f"Output saved to '{self.pipeline.config.output_dir}'.\n"
                f"Reparse enabled: {reparse_existing}."
            )
            self.status_label.setText("Pipeline complete")
            self.refresh_input_list()
            self.refresh_search_index()
            self.refresh_output_json_list()
            self.athlete_manager.rebuild_from_outputs()
            self.refresh_athletes_list()
        except Exception as exc:
            logger.exception("Pipeline error")
            QMessageBox.critical(self, "Pipeline Error", str(exc))
            self.status_label.setText("Pipeline failed")

    def display_result(self, pdf_path: str, result: dict) -> None:
        output_path = result.get("output_path")
        layout_info = result.get("layout_info") or {}
        parse_result = result.get("parse_result")
        if output_path:
            detected_name = layout_info.get('layout_type')
            if detected_name in self.layout_display_names:
                detected_name = self.layout_display_names[detected_name]
            message = [
                f"Processed: {os.path.basename(pdf_path)}",
                f"Detected layout: {detected_name} (confidence: {layout_info.get('confidence', 0):.2f})",
                f"Parsed events: {len(parse_result.events) if parse_result else 0}",
                f"Output saved to: {output_path}",
            ]
            self.results_area.setPlainText("\n".join(message))
            self.status_label.setText("Processing complete")
        else:
            detected_name = layout_info.get('layout_type', "unknown")
            if detected_name in self.layout_display_names:
                detected_name = self.layout_display_names[detected_name]
            reason = f"Could not detect a supported layout or parser failed. Detected: {detected_name}"
            self.results_area.setPlainText(reason)
            self.status_label.setText("Processing failed")

    def open_pdf(self) -> None:
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Select RaceVault PDF", os.getcwd(), "PDF Files (*.pdf)")
        if not pdf_path:
            return
        self.status_label.setText(f"Processing: {os.path.basename(pdf_path)}")
        QApplication.processEvents()
        try:
            extracted = self.pipeline.extractor.extract(pdf_path)
            detected_layout = self.pipeline.layout_detector.detect(extracted)
            layouts = ["Auto-detect", *[self.layout_display_names.get(key, key) for key in PARSER_REGISTRY]]
            default_index = 0
            if detected_layout["layout_type"] in self.layout_display_names:
                default_display = self.layout_display_names[detected_layout["layout_type"]]
                if default_display in layouts:
                    default_index = layouts.index(default_display)
            selected_layout, ok = QInputDialog.getItem(
                self, "Select Parser Layout", "Choose a parser layout for this PDF:",
                layouts, current=default_index, editable=False,
            )
            if not ok:
                self.status_label.setText("Processing canceled")
                return
            layout_override = None if selected_layout == "Auto-detect" else selected_layout
            result = self.pipeline.process_file(pdf_path, layout_override=layout_override, extracted=extracted, move_parsed=False)
            self.display_result(pdf_path, result)
            self.refresh_search_index()
            self.refresh_output_json_list()
        except Exception as exc:
            logger.exception("Error processing PDF")
            QMessageBox.critical(self, "Processing Error", str(exc))
            self.status_label.setText("Processing failed")

    def refresh_output_json_list(self) -> None:
        self.json_table.setSortingEnabled(False)
        self.json_table.setRowCount(0)
        output_path = Path(self.pipeline.config.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_files = sorted(output_path.glob("*.json"))
        for idx, path in enumerate(json_files):
            try:
                size = path.stat().st_size
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                continue
            self.json_table.insertRow(idx)
            filename_item = QTableWidgetItem(path.name)
            filename_item.setData(Qt.UserRole, str(path))
            self.json_table.setItem(idx, 0, filename_item)
            self.json_table.setItem(idx, 1, QTableWidgetItem(f"{size:,} bytes"))
            self.json_table.setItem(idx, 2, QTableWidgetItem(mtime))
            self.json_table.setItem(idx, 3, QTableWidgetItem(str(path)))
        self.json_table.setSortingEnabled(True)

    def _selected_json_paths(self) -> list[str]:
        paths = []
        for item in self.json_table.selectedItems():
            if item.column() == 0:
                stored = item.data(Qt.UserRole)
                if isinstance(stored, str):
                    paths.append(stored)
        return sorted(set(paths))

    def view_selected_json(self) -> None:
        selected_paths = self._selected_json_paths()
        if not selected_paths:
            QMessageBox.information(self, "No Selection", "Select a JSON file to view.")
            return
        path = selected_paths[0]
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            logger.exception("Failed to open JSON file")
            QMessageBox.critical(self, "Open Error", f"Could not open JSON file:\n{exc}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"JSON — {os.path.basename(path)}")
        dialog.resize(820, 620)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(12, 12, 12, 12)
        text_area = QTextEdit()
        text_area.setReadOnly(True)
        text_area.setPlainText(content)
        dlg_layout.addWidget(text_area)
        close_button = _make_primary_button("Close")
        close_button.setFixedWidth(100)
        close_button.clicked.connect(dialog.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_button)
        dlg_layout.addLayout(row)
        dialog.exec()

    def delete_selected_json(self) -> None:
        selected_paths = self._selected_json_paths()
        if not selected_paths:
            QMessageBox.information(self, "No Selection", "Select one or more JSON files to delete.")
            return
        reply = QMessageBox.question(
            self, "Delete JSON Files",
            f"Delete {len(selected_paths)} selected JSON file(s)? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        deleted = 0
        for path in selected_paths:
            try:
                os.remove(path)
                deleted += 1
            except Exception:
                logger.exception(f"Failed to delete JSON file: {path}")
        self.refresh_output_json_list()
        self.refresh_search_index()
        QMessageBox.information(self, "Deleted", f"Deleted {deleted} JSON file(s).")

    def refresh_search_index(self) -> None:
        self.search_index = []
        output_path = Path(self.pipeline.config.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_files = sorted(output_path.glob("*.json"))
        for path in json_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            source_file = data.get("source_file")
            if not source_file:
                source_file = (
                    Path(data.get("_export_metadata", {}).get("original_path", "")).name
                    or path.stem
                )
            try:
                mtime = Path(path).stat().st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except Exception:
                date_str = ""
            for event in data.get("events", []):
                event_name = event.get("event_name") or ""
                for result in event.get("results", []):
                    athlete = result.get("athlete") or {}
                    raw_name = athlete.get("raw_name", "") or ""
                    normalized_name = athlete.get("normalized_name", "") or ""
                    position = result.get("position") if result.get("position") is not None else ""
                    distance = ""
                    boat_class = ""
                    en = (event_name or "").replace("\u00a0", " ")
                    tokens = en.split()
                    for t in tokens:
                        tclean = t.replace(" ", "").upper()
                        if tclean.endswith("M") and any(ch.isdigit() for ch in tclean):
                            distance = t
                        if any(tclean.startswith(prefix) for prefix in ("K1", "K2", "K4", "C1", "C2", "C4")) or tclean in ("K1", "K2", "K4", "C1", "C2", "C4"):
                            boat_class = tclean
                    raw_line = result.get("raw_data", {}).get("line", "")
                    if not distance and raw_line:
                        for part in raw_line.split():
                            if part.lower().endswith("m") and any(ch.isdigit() for ch in part):
                                distance = part
                                break
                    if not boat_class and raw_line:
                        for prefix in ("K1", "K2", "K4", "C1", "C2", "C4"):
                            if prefix in raw_line:
                                boat_class = prefix
                                break
                    self.search_index.append({
                        "source_file": source_file,
                        "event_name": event_name,
                        "distance": distance,
                        "boat_class": boat_class,
                        "athlete_name": raw_name,
                        "normalized_name": normalized_name,
                        "club": result.get("club", "") or "",
                        "time": result.get("time", "") or "",
                        "position": position,
                        "output_path": str(path),
                        "date": date_str,
                    })
        n = len(json_files)
        self.search_info_label.setText(
            f"Indexed {n} JSON file(s) — use the search above to display results."
        )
        self.status_bar_index_label.setText(f"{n} files indexed")
        self._populate_search_table([])

    def perform_search(self) -> None:
        query = self.search_input.text().strip().lower()
        search_type = self.search_type_selector.currentText()
        if not query:
            filtered = self.search_index
        else:
            filtered = []
            for row in self.search_index:
                if search_type == "Race/Event":
                    haystack = row["event_name"].lower()
                elif search_type == "Athlete Name":
                    haystack = f"{row['athlete_name']} {row['normalized_name']}".lower()
                elif search_type == "Source file / Date":
                    haystack = row["source_file"].lower()
                else:
                    haystack = " ".join([
                        row["source_file"], row["event_name"],
                        row["athlete_name"], row["normalized_name"],
                        row["club"], row["time"],
                    ]).lower()
                if query in haystack:
                    filtered.append(row)
        self._populate_search_table(filtered)
        self.search_info_label.setText(
            f"Indexed {len(self.search_index)} row(s) — showing {len(filtered)} match(es)."
        )

    def _populate_search_table(self, rows: List[Dict[str, Any]]) -> None:
        self.search_table.setSortingEnabled(False)
        self.search_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            comp_item = QTableWidgetItem(row.get("source_file", ""))
            comp_item.setData(Qt.UserRole, row)
            self.search_table.setItem(row_index, 0, comp_item)
            self.search_table.setItem(row_index, 1, QTableWidgetItem(row.get("distance", "")))
            self.search_table.setItem(row_index, 2, QTableWidgetItem(row.get("boat_class", "")))
            self.search_table.setItem(row_index, 3, QTableWidgetItem(row.get("athlete_name", "")))

            time_item = QTableWidgetItem(row.get("time", ""))
            time_item.setFont(QFont("JetBrains Mono, Cascadia Code, Consolas, Courier New", 11))
            self.search_table.setItem(row_index, 4, time_item)

            pos = row.get("position", "")
            pos_item = QTableWidgetItem(str(pos) if pos is not None else "")
            if str(pos) == "1":
                pos_item.setForeground(QColor("#E87820"))
            elif str(pos) in ("2", "3"):
                pos_item.setForeground(QColor("#A8A8D8"))
            self.search_table.setItem(row_index, 5, pos_item)
            self.search_table.setItem(row_index, 6, QTableWidgetItem(row.get("date", "")))
        self.search_table.setSortingEnabled(True)

    def _build_report_row(self, row: dict) -> list[QTableWidgetItem]:
        return [
            QTableWidgetItem(row.get("source_file", "")),
            QTableWidgetItem(row.get("distance", "")),
            QTableWidgetItem(row.get("boat_class", "")),
            QTableWidgetItem(row.get("athlete_name", "")),
            QTableWidgetItem(row.get("time", "")),
            QTableWidgetItem(str(row.get("position", "")) if row.get("position") is not None else ""),
            QTableWidgetItem(row.get("date", "")),
        ]

    def _selected_search_rows(self) -> list[dict]:
        rows = []
        for model_index in self.search_table.selectionModel().selectedRows():
            comp_item = self.search_table.item(model_index.row(), 0)
            if comp_item:
                data = comp_item.data(Qt.UserRole)
                if isinstance(data, dict):
                    rows.append(data)
        return rows

    def _selected_report_rows(self) -> list[int]:
        return sorted({item.row() for item in self.report_selection_table.selectedItems()})

    def add_selected_to_report_box(self) -> None:
        rows = self._selected_search_rows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Select one or more search results to add to the report box.")
            return
        existing = set()
        for row_index in range(self.report_selection_table.rowCount()):
            source_item = self.report_selection_table.item(row_index, 0)
            athlete_item = self.report_selection_table.item(row_index, 3)
            if source_item and athlete_item:
                existing.add((source_item.text(), athlete_item.text()))
        self.report_selection_table.setSortingEnabled(False)
        insert_index = self.report_selection_table.rowCount()
        for row in rows:
            key = (row.get("source_file", ""), row.get("athlete_name", ""))
            if key in existing:
                continue
            self.report_selection_table.insertRow(insert_index)
            items = self._build_report_row(row)
            for col, item in enumerate(items):
                if col == 0:
                    item.setData(Qt.UserRole, row)
                self.report_selection_table.setItem(insert_index, col, item)
            insert_index += 1
        self.report_selection_table.setSortingEnabled(False)

    def remove_selected_from_report_box(self) -> None:
        rows = self._selected_report_rows()
        if not rows:
            QMessageBox.information(self, "No Selection", "Select rows in the report box to remove.")
            return
        for row_index in reversed(rows):
            self.report_selection_table.removeRow(row_index)

    def clear_report_box(self) -> None:
        self.report_selection_table.setRowCount(0)

    def generate_pdf_report(self) -> None:
        filtered_rows = []
        for row_index in range(self.report_selection_table.rowCount()):
            comp_item = self.report_selection_table.item(row_index, 0)
            if not comp_item:
                continue
            stored = comp_item.data(Qt.UserRole)
            if isinstance(stored, dict):
                filtered_rows.append(stored)
            else:
                row_data = {
                    "source_file": comp_item.text(),
                    "distance": (self.report_selection_table.item(row_index, 1) or QTableWidgetItem()).text(),
                    "boat_class": (self.report_selection_table.item(row_index, 2) or QTableWidgetItem()).text(),
                    "athlete_name": (self.report_selection_table.item(row_index, 3) or QTableWidgetItem()).text(),
                    "time": (self.report_selection_table.item(row_index, 4) or QTableWidgetItem()).text(),
                    "position": (self.report_selection_table.item(row_index, 5) or QTableWidgetItem()).text(),
                    "date": (self.report_selection_table.item(row_index, 6) or QTableWidgetItem()).text(),
                    "output_path": None,
                }
                filtered_rows.append(row_data)
        if not filtered_rows:
            QMessageBox.warning(self, "No Report Rows", "The report box is empty. Add search results before generating a PDF.")
            return
        try:
            reporter = PDFReporter(self.pipeline.config.output_dir)
            query = self.search_input.text().strip()
            title = f"RaceVault Results Report — {query}" if query else "RaceVault Results Report"
            report_path = reporter.generate_report(filtered_rows, title=title, include_charts=True)
            self.last_report_path = report_path
            try:
                self.open_last_button.setEnabled(True)
                self.print_last_button.setEnabled(True)
            except Exception:
                pass
            try:
                self.open_report()
            except Exception:
                logger.exception("Auto-open failed")
            QMessageBox.information(self, "PDF Generated", f"Report generated:\n{report_path}")
            logger.info(f"PDF report generated: {report_path}")
        except Exception as exc:
            logger.exception("Error generating PDF report")
            QMessageBox.critical(self, "Report Generation Error", f"Failed to generate PDF:\n{str(exc)}")

    def open_report(self, do_print: bool = False, path: Optional[str] = None) -> None:
        report_path = path or self.last_report_path
        if not report_path:
            QMessageBox.warning(self, "No Report", "No report is available to open.")
            return
        try:
            if do_print:
                if os.name == "nt":
                    os.startfile(report_path, "print")
                else:
                    if shutil.which("lpr"):
                        subprocess.run(["lpr", report_path], check=False)
                    else:
                        opener = shutil.which("xdg-open") or shutil.which("open")
                        if opener:
                            subprocess.run([opener, report_path], check=False)
                        else:
                            import webbrowser
                            webbrowser.open(report_path)
            else:
                if os.name == "nt":
                    os.startfile(report_path)
                else:
                    opener = shutil.which("xdg-open") or shutil.which("open")
                    if opener:
                        subprocess.run([opener, report_path], check=False)
                    else:
                        import webbrowser
                        webbrowser.open(report_path)
        except Exception as exc:
            logger.exception("Failed to open/print report")
            QMessageBox.critical(self, "Open Error", f"Could not open/print report:\n{exc}")

    def rebuild_athletes_from_outputs(self) -> None:
        self.athlete_manager.rebuild_from_outputs()
        self.refresh_athletes_list()
        QMessageBox.information(self, "Success", "Athlete database rebuilt from all output files.")

    def refresh_athletes_list(self) -> None:
        self.athletes_table.setSortingEnabled(False)
        self.athletes_table.setRowCount(0)
        athletes = self.athlete_manager.get_all_athletes()
        for idx, athlete in enumerate(athletes):
            self.athletes_table.insertRow(idx)
            name_item = QTableWidgetItem(athlete.get("name", ""))
            name_item.setData(Qt.UserRole, athlete.get("name", ""))
            self.athletes_table.setItem(idx, 0, name_item)
            birth_date = athlete.get("birth_date", "")
            self.athletes_table.setItem(idx, 1, QTableWidgetItem(birth_date or "—"))
            age = athlete.get("age")
            self.athletes_table.setItem(idx, 2, QTableWidgetItem(str(age) if age is not None else "—"))
        self.athletes_table.setSortingEnabled(True)
        self.clear_athlete_selection()

    def on_athlete_selected(self) -> None:
        selected_rows = self.athletes_table.selectionModel().selectedRows()
        if not selected_rows:
            self.clear_athlete_selection()
            return
        row = selected_rows[0].row()
        athlete_name_item = self.athletes_table.item(row, 0)
        if not athlete_name_item:
            self.clear_athlete_selection()
            return
        athlete_name = athlete_name_item.data(Qt.UserRole)
        athlete = self.athlete_manager.get_athlete(athlete_name)
        if not athlete:
            self.clear_athlete_selection()
            return
        card = self.athlete_manager.get_athlete_card(athlete_name)
        self.athlete_times_text.setPlainText(card)
        birth_date = athlete.get("birth_date") or ""
        self.birth_date_input.setText(birth_date)
        if athlete.get("age") is not None:
            self.age_display.setText(f"{athlete['age']} years old")
        else:
            self.age_display.setText("N/A")

    def clear_athlete_selection(self) -> None:
        self.athlete_times_text.setPlainText("")
        self.birth_date_input.setText("")
        self.age_display.setText("N/A")

    def save_athlete_birth_date(self) -> None:
        selected_rows = self.athletes_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Select an athlete first.")
            return
        row = selected_rows[0].row()
        athlete_name_item = self.athletes_table.item(row, 0)
        if not athlete_name_item:
            return
        athlete_name = athlete_name_item.data(Qt.UserRole)
        birth_date = self.birth_date_input.text().strip()
        if birth_date:
            try:
                datetime.strptime(birth_date, "%Y-%m-%d")
            except ValueError:
                QMessageBox.warning(self, "Invalid Date", "Please use YYYY-MM-DD format.")
                return
        if self.athlete_manager.update_athlete_birth_date(athlete_name, birth_date or None):
            athlete = self.athlete_manager.get_athlete(athlete_name)
            self.athletes_table.setItem(row, 1, QTableWidgetItem(birth_date or "—"))
            if athlete and athlete.get("age") is not None:
                self.athletes_table.setItem(row, 2, QTableWidgetItem(str(athlete['age'])))
                self.age_display.setText(f"{athlete['age']} years old")
            QMessageBox.information(self, "Saved", "Birth date saved successfully.")
        else:
            QMessageBox.critical(self, "Error", "Failed to save birth date.")

    def clear_athlete_birth_date(self) -> None:
        selected_rows = self.athletes_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Select an athlete first.")
            return
        row = selected_rows[0].row()
        athlete_name_item = self.athletes_table.item(row, 0)
        if not athlete_name_item:
            return
        athlete_name = athlete_name_item.data(Qt.UserRole)
        if self.athlete_manager.update_athlete_birth_date(athlete_name, None):
            self.athletes_table.setItem(row, 1, QTableWidgetItem("—"))
            self.athletes_table.setItem(row, 2, QTableWidgetItem("—"))
            self.birth_date_input.setText("")
            self.age_display.setText("N/A")
            QMessageBox.information(self, "Cleared", "Birth date cleared.")
        else:
            QMessageBox.critical(self, "Error", "Failed to clear birth date.")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(RACEVAULT_QSS)

    # Dark palette as fallback
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#16161A"))
    palette.setColor(QPalette.WindowText, QColor("#E8E8F0"))
    palette.setColor(QPalette.Base, QColor("#1A1A22"))
    palette.setColor(QPalette.AlternateBase, QColor("#1E1E28"))
    palette.setColor(QPalette.ToolTipBase, QColor("#22222C"))
    palette.setColor(QPalette.ToolTipText, QColor("#E8E8F0"))
    palette.setColor(QPalette.Text, QColor("#E8E8F0"))
    palette.setColor(QPalette.Button, QColor("#2A2A34"))
    palette.setColor(QPalette.ButtonText, QColor("#C8C8E0"))
    palette.setColor(QPalette.BrightText, QColor("#E87820"))
    palette.setColor(QPalette.Highlight, QColor("#2E2840"))
    palette.setColor(QPalette.HighlightedText, QColor("#E8E8F8"))
    app.setPalette(palette)

    window = RaceVaultGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
