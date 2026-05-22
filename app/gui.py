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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QImage
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
)

import fitz  # PyMuPDF

from .main import Pipeline
from .config import Config
from .parsers import PARSER_REGISTRY
from .pdf_reporter import PDFReporter
from .layout_preview import LayoutPreviewPanel, LayoutPreviewComboBox
from .athlete_manager import AthleteManager

logger = logging.getLogger(__name__)


class RaceVaultGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RaceVault PDF Layout Parser")
        self.resize(880, 520)

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

        # drag and drop to main window
        self.setAcceptDrops(True)

        self.tabs = QTabWidget(self)
        self.parsing_tab = QWidget()
        self.search_tab = QWidget()
        self.config_tab = QWidget()
        self.athlete_tab = QWidget()

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.tabs)

        self._build_parsing_tab()
        self._build_search_tab()
        self._build_config_tab()
        self._build_athlete_tab()

        self.tabs.addTab(self.parsing_tab, "Parsing")
        self.tabs.addTab(self.search_tab, "Search Parsed Results")
        self.tabs.addTab(self.athlete_tab, "Athlete Analysis")
        self.tabs.addTab(self.config_tab, "Config")

        self.refresh_search_index()
        self.refresh_output_json_list()
        self.refresh_athletes_list()

    def _build_parsing_tab(self) -> None:
        layout = QVBoxLayout(self.parsing_tab)

        # --- Ligne des boutons existants ---
        top_layout = QHBoxLayout()
        self.add_pdfs_button = QPushButton("Add PDFs")
        self.add_pdfs_button.clicked.connect(self.add_pdfs)
        top_layout.addWidget(self.add_pdfs_button)

        self.parse_selected_button = QPushButton("Parse Selected")
        self.parse_selected_button.clicked.connect(self.parse_selected)
        top_layout.addWidget(self.parse_selected_button)

        self.parse_all_button = QPushButton("Parse All")
        self.parse_all_button.clicked.connect(self.parse_all)
        top_layout.addWidget(self.parse_all_button)

        self.refresh_input_button = QPushButton("Refresh")
        self.refresh_input_button.clicked.connect(self.refresh_input_list)
        top_layout.addWidget(self.refresh_input_button)
        layout.addLayout(top_layout)

        # --- Filtre année ---
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter by Year:")
        self.year_filter_combo = QComboBox()
        self.year_filter_combo.addItem("All")
        self.year_filter_combo.currentTextChanged.connect(self.filter_by_year)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.year_filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- Sélecteur de parser + preview (inchangé) ---
        parser_layout = QHBoxLayout()
        parser_label = QLabel("Parser Layout:")
        self.layout_preview_panel = LayoutPreviewPanel()
        self.parser_selector = LayoutPreviewComboBox(self.layout_preview_panel)
        self.parser_selector.addItems([
            "Auto-detect",
            *[self.layout_display_names.get(key, key) for key in PARSER_REGISTRY],
        ])
        self.parser_selector.currentTextChanged.connect(self.layout_preview_panel.update_preview)
        parser_layout.addWidget(parser_label)
        parser_layout.addWidget(self.parser_selector)
        parser_layout.addWidget(self.layout_preview_panel)
        parser_layout.addStretch()
        layout.addLayout(parser_layout)

        # --- Tableau et prévisualisation côte à côte ---
        table_preview_layout = QHBoxLayout()
        
        # Tableau à gauche
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_label = QLabel("PDFs to Process:")
        table_layout.addWidget(table_label)
        self.input_table = QTableWidget(0, 3)
        self.input_table.setHorizontalHeaderLabels(["Competition", "Year", "Status"])
        self.input_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.input_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.input_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.input_table.selectionModel().selectionChanged.connect(self.on_pdf_selection_changed)
        table_layout.addWidget(self.input_table)
        table_preview_layout.addWidget(table_container, 2)  # 2 parts for table
        
        # Prévisualisation à droite
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_label = QLabel("PDF Preview (Page 1):")
        preview_layout.addWidget(preview_label)
        
        # Scroll area pour la prévisualisation
        self.pdf_preview_scroll = QScrollArea()
        self.pdf_preview_scroll.setWidgetResizable(True)
        self.pdf_preview_label = QLabel()
        self.pdf_preview_label.setAlignment(Qt.AlignCenter)
        self.pdf_preview_label.setStyleSheet("background-color: #f0f0f0;")
        self.pdf_preview_scroll.setWidget(self.pdf_preview_label)
        preview_layout.addWidget(self.pdf_preview_scroll)
        table_preview_layout.addWidget(preview_container, 1)  # 1 part for preview
        
        layout.addLayout(table_preview_layout)

        # Barre de progression
        self.parsing_progress = QProgressBar()
        self.parsing_progress.setValue(0)
        layout.addWidget(self.parsing_progress)

        self.refresh_input_list()


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
            # Extraire l'année : les 4 derniers caractères du stem (sans .pdf)
            year = ""
            if len(stem) >= 4 and stem[-4:].isdigit():
                year = stem[-4:]
                years_set.add(year)

            # Statut
            status = "parsed" if p.stem in parsed_files else "Waiting"
            status_color = "#d4ffd4" if status == "parsed" else None

            # Competition : afficher le stem complet (sans .pdf)
            comp_item = QTableWidgetItem(stem)
            comp_item.setData(Qt.UserRole, p.name)   # stocker le vrai nom du fichier
            self.input_table.insertRow(idx)
            self.input_table.setItem(idx, 0, comp_item)
            self.input_table.setItem(idx, 1, QTableWidgetItem(year))

            status_item = QTableWidgetItem(status)
            if status_color:
                status_item.setBackground(QColor(status_color))
            self.input_table.setItem(idx, 2, status_item)

        self.input_table.setSortingEnabled(True)

        # Mettre à jour le filtre d'année
        self.year_filter_combo.blockSignals(True)
        self.year_filter_combo.clear()
        self.year_filter_combo.addItem("All")
        self.year_filter_combo.addItems(sorted(years_set))
        self.year_filter_combo.blockSignals(False)
        self.filter_by_year()   # appliquer le filtre (par défaut "All")

    def filter_by_year(self) -> None:
        selected_year = self.year_filter_combo.currentText()
        for row in range(self.input_table.rowCount()):
            year_item = self.input_table.item(row, 1)
            if year_item is None:
                continue
            year = year_item.text()
            hide = (selected_year != "All" and year != selected_year)
            self.input_table.setRowHidden(row, hide)

    def on_pdf_selection_changed(self) -> None:
        """Appelé quand la sélection du tableau change."""
        rows = sorted({item.row() for item in self.input_table.selectedItems()})
        if not rows:
            # Aucune sélection, vider la prévisualisation
            self.pdf_preview_label.setPixmap(QPixmap())
            self.pdf_preview_label.setText("No PDF selected")
            return
        
        # Si plusieurs PDFs sont sélectionnés, afficher seulement le premier
        first_row = rows[0]
        comp_item = self.input_table.item(first_row, 0)
        if comp_item:
            filename = comp_item.data(Qt.UserRole)
            pdf_path = os.path.join(self.pipeline.config.input_dir, filename)
            self.update_pdf_preview(pdf_path)

    def update_pdf_preview(self, pdf_path: str) -> None:
        """Charge et affiche la première page du PDF en haute résolution."""
        try:
            if not os.path.exists(pdf_path):
                self.pdf_preview_label.setPixmap(QPixmap())
                self.pdf_preview_label.setText("PDF file not found")
                return
            
            # Ouvrir le PDF avec PyMuPDF
            doc = fitz.open(pdf_path)
            if doc.page_count == 0:
                doc.close()
                self.pdf_preview_label.setPixmap(QPixmap())
                self.pdf_preview_label.setText("PDF has no pages")
                return
            
            # Obtenir la première page
            page = doc[0]
            
            # Rendre la page en haute résolution (300 DPI)
            # Factor 2 = ~150 DPI, Factor 4 = ~300 DPI
            mat = fitz.Matrix(4, 4)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convertir en image Qt
            img_data = pix.tobytes("ppm")
            qimage = QImage()
            qimage.loadFromData(img_data)
            
            # Redimensionner pour l'affichage si nécessaire
            max_width = 300
            max_height = 500
            if qimage.width() > max_width or qimage.height() > max_height:
                qimage = qimage.scaledToHeight(max_height, Qt.SmoothTransformation)
            
            # Afficher l'image
            pixmap = QPixmap.fromImage(qimage)
            self.pdf_preview_label.setPixmap(pixmap)
            
            doc.close()
        except Exception as exc:
            logger.exception(f"Error loading PDF preview for {pdf_path}")
            self.pdf_preview_label.setPixmap(QPixmap())
            self.pdf_preview_label.setText(f"Error loading preview:\n{str(exc)}")


    def add_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDFs to add", os.path.expanduser("~"), "PDF Files (*.pdf)")
        if not files:
            return

        added = 0
        for f in files:
            try:
                if not f.lower().endswith(".pdf"):
                    logger.info(f"Skipped non-PDF: {f}")
                    continue
                if os.path.getsize(f) == 0:
                    logger.info(f"Skipped empty file: {f}")
                    continue

                dest_dir = self.pipeline.config.input_dir
                basename = os.path.basename(f)
                dest = os.path.join(dest_dir, basename)

                # duplicate detection: ignore parsed/ so files can remain in input
                output_conflict = os.path.exists(os.path.join(self.pipeline.config.output_dir, os.path.splitext(basename)[0] + ".json"))
                if os.path.exists(dest) or output_conflict:
                    logger.info(f"Duplicate detected, skipping: {basename}")
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
                filename = comp_item.data(Qt.UserRole)   # nom complet du PDF
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
            # update status to Parsing
            for row in range(self.input_table.rowCount()):
                stored_filename = self.input_table.item(row, 0).data(Qt.UserRole)
                if stored_filename == filename:
                    parsing_item = QTableWidgetItem("Parsing")
                    parsing_item.setBackground(QColor("#fff4c2"))
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

            # update final status
            for row in range(self.input_table.rowCount()):
                stored_filename = self.input_table.item(row, 0).data(Qt.UserRole)
                if stored_filename == filename:
                    status_item = QTableWidgetItem(status)
                    if status == "Parsed":
                        status_item.setBackground(QColor("#d4ffd4"))
                    elif status == "Error":
                        status_item.setBackground(QColor("#ffd4d4"))
                    self.input_table.setItem(row, 2, status_item)
                    break

            pct = int((idx / total) * 100)
            self.parsing_progress.setValue(pct)
            QApplication.processEvents()

        self.parsing_progress.setValue(100)
        QApplication.processEvents()

        # refresh lists after processing
        self.refresh_output_json_list()
        self.refresh_input_list()  # refresh after output to detect parsed files
        self.refresh_search_index()
        
        # Rebuild athlete data from new outputs
        self.athlete_manager.rebuild_from_outputs()
        self.refresh_athletes_list()

    # ----------------------------------------------------------------------
    # Les méthodes suivantes sont inchangées par rapport à l'original
    # (search, config, drag & drop, etc.)
    # ----------------------------------------------------------------------

    def _build_search_tab(self) -> None:
        layout = QVBoxLayout(self.search_tab)

        controls_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by race/event, athlete name, file name/date...")
        self.search_input.returnPressed.connect(self.perform_search)
        controls_layout.addWidget(self.search_input)

        self.search_type_selector = QComboBox()
        self.search_type_selector.addItems([
            "All fields",
            "Race/Event",
            "Athlete Name",
            "Source file / Date",
        ])
        controls_layout.addWidget(self.search_type_selector)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        controls_layout.addWidget(self.search_button)

        self.refresh_button = QPushButton("Refresh Index")
        self.refresh_button.clicked.connect(self.refresh_search_index)
        controls_layout.addWidget(self.refresh_button)

        self.report_button = QPushButton("Generate PDF Report")
        self.report_button.clicked.connect(self.generate_pdf_report)
        self.report_button.setStyleSheet("QPushButton { background-color: #2e5c8a; color: white; font-weight: bold; }")
        controls_layout.addWidget(self.report_button)

        self.open_last_button = QPushButton("Open Last Report")
        self.open_last_button.clicked.connect(self.open_report)
        self.open_last_button.setEnabled(False)
        controls_layout.addWidget(self.open_last_button)

        self.print_last_button = QPushButton("Print Last Report")
        self.print_last_button.clicked.connect(lambda: self.open_report(do_print=True))
        self.print_last_button.setEnabled(False)
        controls_layout.addWidget(self.print_last_button)

        layout.addLayout(controls_layout)

        self.search_info_label = QLabel("Use the search filters to display results.")
        layout.addWidget(self.search_info_label)

        # Standardized columns: Competition, Distance, Boat Class, Athlete, Time, Position, Date
        self.search_table = QTableWidget(0, 7)
        self.search_table.setHorizontalHeaderLabels([
            "Competition Name",
            "Distance",
            "Boat Class",
            "Athlete Name",
            "Time",
            "Position",
            "Date",
        ])
        self.search_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.search_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.search_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.search_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.search_table.setSortingEnabled(True)
        layout.addWidget(self.search_table)

        report_controls = QHBoxLayout()
        self.add_to_report_button = QPushButton("Add Selected to Report Box")
        self.add_to_report_button.clicked.connect(self.add_selected_to_report_box)
        report_controls.addWidget(self.add_to_report_button)

        self.remove_from_report_button = QPushButton("Remove Selected from Report Box")
        self.remove_from_report_button.clicked.connect(self.remove_selected_from_report_box)
        report_controls.addWidget(self.remove_from_report_button)

        self.clear_report_button = QPushButton("Clear Report Box")
        self.clear_report_button.clicked.connect(self.clear_report_box)
        report_controls.addWidget(self.clear_report_button)

        layout.addLayout(report_controls)

        self.report_box_label = QLabel("Report Box: selected rows will be included in the PDF report.")
        layout.addWidget(self.report_box_label)

        self.report_selection_table = QTableWidget(0, 7)
        self.report_selection_table.setHorizontalHeaderLabels([
            "Competition Name",
            "Distance",
            "Boat Class",
            "Athlete Name",
            "Time",
            "Position",
            "Date",
        ])
        self.report_selection_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.report_selection_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.report_selection_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.report_selection_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.report_selection_table.setSortingEnabled(False)
        layout.addWidget(self.report_selection_table)

    def _build_config_tab(self) -> None:
        layout = QVBoxLayout(self.config_tab)

        buttons_layout = QHBoxLayout()
        self.refresh_json_button = QPushButton("Refresh JSON List")
        self.refresh_json_button.clicked.connect(self.refresh_output_json_list)
        buttons_layout.addWidget(self.refresh_json_button)

        self.view_json_button = QPushButton("View JSON")
        self.view_json_button.clicked.connect(self.view_selected_json)
        buttons_layout.addWidget(self.view_json_button)

        self.delete_json_button = QPushButton("Delete Selected JSON(s)")
        self.delete_json_button.clicked.connect(self.delete_selected_json)
        buttons_layout.addWidget(self.delete_json_button)

        layout.addLayout(buttons_layout)

        self.json_table = QTableWidget(0, 4)
        self.json_table.setHorizontalHeaderLabels(["Filename", "Size", "Modified", "Path"])
        self.json_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.json_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.json_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.json_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.json_table.itemDoubleClicked.connect(self.view_selected_json)
        layout.addWidget(self.json_table)

    def _build_athlete_tab(self) -> None:
        layout = QVBoxLayout(self.athlete_tab)

        # Top controls
        controls_layout = QHBoxLayout()
        
        self.rebuild_athletes_button = QPushButton("Rebuild Athletes Data")
        self.rebuild_athletes_button.clicked.connect(self.rebuild_athletes_from_outputs)
        controls_layout.addWidget(self.rebuild_athletes_button)
        
        self.refresh_athletes_button = QPushButton("Refresh List")
        self.refresh_athletes_button.clicked.connect(self.refresh_athletes_list)
        controls_layout.addWidget(self.refresh_athletes_button)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Athletes table
        self.athletes_table = QTableWidget(0, 3)
        self.athletes_table.setHorizontalHeaderLabels(["Athlete Name", "Birth Date", "Age"])
        self.athletes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.athletes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.athletes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.athletes_table.itemSelectionChanged.connect(self.on_athlete_selected)
        layout.addWidget(self.athletes_table)

        # Info and editing area
        info_layout = QHBoxLayout()
        
        # Left: Best times display
        times_container = QWidget()
        times_layout = QVBoxLayout(times_container)
        times_label = QLabel("Best Times:")
        times_layout.addWidget(times_label)
        self.athlete_times_text = QTextEdit()
        self.athlete_times_text.setReadOnly(True)
        times_layout.addWidget(self.athlete_times_text)
        info_layout.addWidget(times_container, 2)
        
        # Right: Birth date editor
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        
        edit_label = QLabel("Edit Birth Date:")
        editor_layout.addWidget(edit_label)
        
        birth_layout = QHBoxLayout()
        birth_label = QLabel("Birth Date (YYYY-MM-DD):")
        self.birth_date_input = QLineEdit()
        self.birth_date_input.setPlaceholderText("YYYY-MM-DD")
        birth_layout.addWidget(birth_label)
        birth_layout.addWidget(self.birth_date_input)
        editor_layout.addLayout(birth_layout)
        
        age_layout = QHBoxLayout()
        age_label = QLabel("Calculated Age:")
        self.age_display = QLabel("N/A")
        age_layout.addWidget(age_label)
        age_layout.addWidget(self.age_display)
        age_layout.addStretch()
        editor_layout.addLayout(age_layout)
        
        button_layout = QHBoxLayout()
        self.save_birth_date_button = QPushButton("Save Birth Date")
        self.save_birth_date_button.clicked.connect(self.save_athlete_birth_date)
        button_layout.addWidget(self.save_birth_date_button)
        
        self.clear_birth_date_button = QPushButton("Clear Birth Date")
        self.clear_birth_date_button.clicked.connect(self.clear_athlete_birth_date)
        button_layout.addWidget(self.clear_birth_date_button)
        
        editor_layout.addLayout(button_layout)
        editor_layout.addStretch()
        
        info_layout.addWidget(editor_container, 1)
        layout.addLayout(info_layout)

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
            self.json_table.setItem(idx, 1, QTableWidgetItem(f"{size} bytes"))
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
        dialog.setWindowTitle(f"View JSON - {os.path.basename(path)}")
        dialog.resize(800, 600)
        dlg_layout = QVBoxLayout(dialog)
        text_area = QTextEdit()
        text_area.setReadOnly(True)
        text_area.setPlainText(content)
        dlg_layout.addWidget(text_area)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        dlg_layout.addWidget(close_button)
        dialog.exec()

    def delete_selected_json(self) -> None:
        selected_paths = self._selected_json_paths()
        if not selected_paths:
            QMessageBox.information(self, "No Selection", "Select one or more JSON files to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Delete JSON Files",
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

    def open_pdf(self) -> None:
        pdf_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select RaceVault PDF",
            os.getcwd(),
            "PDF Files (*.pdf)",
        )
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
                self,
                "Select Parser Layout",
                "Choose a parser layout for this PDF:",
                layouts,
                current=default_index,
                editable=False,
            )
            if not ok:
                self.status_label.setText("Processing canceled")
                return

            layout_override = None if selected_layout == "Auto-detect" else selected_layout
            effective_move = False
            result = self.pipeline.process_file(
                pdf_path,
                layout_override=layout_override,
                extracted=extracted,
                move_parsed=effective_move,
            )
            self.display_result(pdf_path, result)
            self.refresh_search_index()
            self.refresh_output_json_list()
        except Exception as exc:
            logger.exception("Error processing PDF")
            QMessageBox.critical(self, "Processing Error", str(exc))
            self.status_label.setText("Processing failed")

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
                    logger.info(f"Duplicate on drop, skipping: {f}")
                    continue
                shutil.copy2(f, dest)
                added += 1
            except Exception:
                logger.exception(f"Failed to copy dropped file: {f}")

        if added:
            QMessageBox.information(self, "Files Added", f"Added {added} PDF(s) to input folder via drag-and-drop.")
        self.refresh_input_list()

    def run_pipeline(self) -> None:
        # fallback: run full pipeline without per-file status updates
        reparse_existing = self.reparse_checkbox.isChecked()
        mode_text = "including already parsed PDFs" if reparse_existing else "skipping already parsed PDFs"
        self.status_label.setText(f"Running pipeline on input folder ({mode_text})")
        QApplication.processEvents()

        try:
            exported_files = self.pipeline.run(reparse_existing=reparse_existing, move_parsed=False)
            total_input = len(self.pipeline._scan_input(reparse_existing=True))
            reprocessed = len(exported_files)
            self.results_area.setPlainText(
                f"Pipeline completed. Processed {reprocessed} PDF(s) from input folder.\n"
                f"Output saved to '{self.pipeline.config.output_dir}'.\n"
                f"Reparse enabled: {reparse_existing}."
            )
            self.status_label.setText("Pipeline complete")
            # refresh both lists
            self.refresh_input_list()
            self.refresh_search_index()
            self.refresh_output_json_list()
            
            # Rebuild athlete data from new outputs
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
            message = [f"Processed: {os.path.basename(pdf_path)}"]
            detected_name = layout_info.get('layout_type')
            if detected_name in self.layout_display_names:
                detected_name = self.layout_display_names[detected_name]

            message.append(
                f"Detected layout: {detected_name}"
                f" (confidence: {layout_info.get('confidence', 0):.2f})"
            )
            message.append(f"Parsed events: {len(parse_result.events) if parse_result else 0}")
            message.append(f"Output saved to: {output_path}")
            self.results_area.setPlainText("\n".join(message))
            self.status_label.setText("Processing complete")
        else:
            reason = "Could not detect a supported layout or parser failed."
            if layout_info:
                detected_name = layout_info.get('layout_type')
            if detected_name in self.layout_display_names:
                detected_name = self.layout_display_names[detected_name]
            reason += f" Detected layout: {detected_name}"
            self.results_area.setPlainText(reason)
            self.status_label.setText("Processing failed")

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

            # prefer explicit source path stored in export metadata to remain linked after moving files
            source_file = data.get("source_file")
            if not source_file:
                source_file = (
                    Path(data.get("_export_metadata", {}).get("original_path", "")).name
                    or path.stem
                )
            # derive a sensible date from the JSON file modification time
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

                    # attempt to extract distance and boat class from event name or raw_data
                    distance = ""
                    boat_class = ""
                    # check event_name for patterns like '2000m' and 'K1', 'C1', 'K2', etc.
                    en = (event_name or "").replace("\u00a0", " ")
                    tokens = en.split()
                    for t in tokens:
                        tclean = t.replace(" ", "").upper()
                        if tclean.endswith("M") and any(ch.isdigit() for ch in tclean):
                            distance = t
                        if any(tclean.startswith(prefix) for prefix in ("K1", "K2", "K4", "C1", "C2", "C4")) or tclean in ("K1", "K2", "K4", "C1", "C2", "C4"):
                            boat_class = tclean

                    # fallback: look into raw_data 'line' for boat class or distance
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

                    self.search_index.append(
                        {
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
                        }
                    )

        # do not auto-populate results table; wait for user search action
        self.search_info_label.setText(
            f"Indexed {len(json_files)} JSON file(s); use the search filters to display results."
        )
        # clear table until user searches
        self._populate_search_table([])

    def perform_search(self) -> None:
        # populate results only when user explicitly performs a search
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
                    haystack = " ".join(
                        [
                            row["source_file"],
                            row["event_name"],
                            row["athlete_name"],
                            row["normalized_name"],
                            row["club"],
                            row["time"],
                        ]
                    ).lower()

                if query in haystack:
                    filtered.append(row)

        self._populate_search_table(filtered)
        self.search_info_label.setText(
            f"Indexed {len(self.search_index)} row(s); showing {len(filtered)} match(es)."
        )

    def _populate_search_table(self, rows: List[Dict[str, Any]]) -> None:
        # Populate table efficiently; disable sorting while updating
        self.search_table.setSortingEnabled(False)
        self.search_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            # Competition name cell stores the full row dict in UserRole for later retrieval
            comp_item = QTableWidgetItem(row.get("source_file", ""))
            comp_item.setData(Qt.UserRole, row)
            self.search_table.setItem(row_index, 0, comp_item)

            self.search_table.setItem(row_index, 1, QTableWidgetItem(row.get("distance", "")))
            self.search_table.setItem(row_index, 2, QTableWidgetItem(row.get("boat_class", "")))
            self.search_table.setItem(row_index, 3, QTableWidgetItem(row.get("athlete_name", "")))
            self.search_table.setItem(row_index, 4, QTableWidgetItem(row.get("time", "")))
            pos = row.get("position", "")
            self.search_table.setItem(row_index, 5, QTableWidgetItem(str(pos) if pos is not None else ""))
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
        selected_rows = self.search_table.selectionModel().selectedRows()
        for model_index in selected_rows:
            row_index = model_index.row()
            comp_item = self.search_table.item(row_index, 0)
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
            QMessageBox.information(self, "No Selection", "Select one or more rows in the report box to remove.")
            return

        for row_index in reversed(rows):
            self.report_selection_table.removeRow(row_index)

    def clear_report_box(self) -> None:
        self.report_selection_table.setRowCount(0)

    def generate_pdf_report(self) -> None:
        """Generate PDF report from the selected report box rows."""
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
            QMessageBox.warning(self, "No Report Rows", "The report box is empty. Add search results to the report box before generating a PDF.")
            return

        try:
            reporter = PDFReporter(self.pipeline.config.output_dir)
            query = self.search_input.text().strip()
            title = f"RaceVault Results Report - {query}" if query else "RaceVault Results Report"
            report_path = reporter.generate_report(filtered_rows, title=title, include_charts=True)

            # store last report path and enable open/print buttons
            self.last_report_path = report_path
            try:
                self.open_last_button.setEnabled(True)
                self.print_last_button.setEnabled(True)
            except Exception:
                pass

            # attempt to auto-open the PDF
            try:
                self.open_report()
            except Exception:
                logger.exception("Auto-open failed")

            QMessageBox.information(self, "PDF Generated", f"Report successfully generated:\n{report_path}")
            logger.info(f"PDF report generated: {report_path}")
        except Exception as exc:
            logger.exception("Error generating PDF report")
            QMessageBox.critical(self, "Report Generation Error", f"Failed to generate PDF:\n{str(exc)}")

    def open_report(self, do_print: bool = False, path: Optional[str] = None) -> None:
        """Open or print a PDF report using the OS default application."""
        report_path = path or self.last_report_path
        if not report_path:
            QMessageBox.warning(self, "No Report", "No report is available to open.")
            return

        try:
            if do_print:
                # Windows: use os.startfile with print
                if os.name == "nt":
                    os.startfile(report_path, "print")
                else:
                    # try lpr on POSIX
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
        """Rebuild athlete database from all parsed JSON files."""
        self.athlete_manager.rebuild_from_outputs()
        self.refresh_athletes_list()
        QMessageBox.information(self, "Success", "Athlete database rebuilt from all output files.")

    def refresh_athletes_list(self) -> None:
        """Refresh the athletes table."""
        self.athletes_table.setSortingEnabled(False)
        self.athletes_table.setRowCount(0)
        
        athletes = self.athlete_manager.get_all_athletes()
        for idx, athlete in enumerate(athletes):
            self.athletes_table.insertRow(idx)
            
            name_item = QTableWidgetItem(athlete.get("name", ""))
            name_item.setData(Qt.UserRole, athlete.get("name", ""))
            self.athletes_table.setItem(idx, 0, name_item)
            
            birth_date = athlete.get("birth_date", "")
            self.athletes_table.setItem(idx, 1, QTableWidgetItem(birth_date or "-"))
            
            age = athlete.get("age")
            age_str = str(age) if age is not None else "-"
            self.athletes_table.setItem(idx, 2, QTableWidgetItem(age_str))
        
        self.athletes_table.setSortingEnabled(True)
        self.clear_athlete_selection()

    def on_athlete_selected(self) -> None:
        """Handle athlete selection in table."""
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
        
        # Display best times
        card = self.athlete_manager.get_athlete_card(athlete_name)
        self.athlete_times_text.setPlainText(card)
        
        # Show birth date in editor
        birth_date = athlete.get("birth_date") or ""
        self.birth_date_input.setText(birth_date)
        
        # Calculate and display age
        if athlete.get("age") is not None:
            self.age_display.setText(f"{athlete['age']} years old")
        else:
            self.age_display.setText("N/A")

    def clear_athlete_selection(self) -> None:
        """Clear athlete selection and displays."""
        self.athlete_times_text.setPlainText("")
        self.birth_date_input.setText("")
        self.age_display.setText("N/A")

    def save_athlete_birth_date(self) -> None:
        """Save birth date for selected athlete."""
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
        
        # Validate date format
        if birth_date:
            try:
                from datetime import datetime
                datetime.strptime(birth_date, "%Y-%m-%d")
            except ValueError:
                QMessageBox.warning(self, "Invalid Date", "Please use YYYY-MM-DD format.")
                return
        
        if self.athlete_manager.update_athlete_birth_date(athlete_name, birth_date or None):
            # Update display
            athlete = self.athlete_manager.get_athlete(athlete_name)
            self.athletes_table.setItem(row, 1, QTableWidgetItem(birth_date or "-"))
            if athlete and athlete.get("age") is not None:
                self.athletes_table.setItem(row, 2, QTableWidgetItem(str(athlete['age'])))
                self.age_display.setText(f"{athlete['age']} years old")
            QMessageBox.information(self, "Success", "Birth date saved successfully.")
        else:
            QMessageBox.critical(self, "Error", "Failed to save birth date.")

    def clear_athlete_birth_date(self) -> None:
        """Clear birth date for selected athlete."""
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
            self.athletes_table.setItem(row, 1, QTableWidgetItem("-"))
            self.athletes_table.setItem(row, 2, QTableWidgetItem("-"))
            self.birth_date_input.setText("")
            self.age_display.setText("N/A")
            QMessageBox.information(self, "Success", "Birth date cleared successfully.")
        else:
            QMessageBox.critical(self, "Error", "Failed to clear birth date.")


def main():
    app = QApplication(sys.argv)
    window = RaceVaultGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()