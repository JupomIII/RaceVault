from __future__ import annotations
import pdfplumber
import fitz  # pymupdf
import pandas as pd
from typing import Dict, Any, List
import os
import logging

logger = logging.getLogger(__name__)


class PDFExtractor:
    def __init__(self):
        self.raw_text: str = ""
        self.raw_tables: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}

    def extract(self, pdf_path: str) -> Dict[str, Any]:
        self.raw_text = ""
        self.raw_tables = []
        self.metadata = {
            "file": os.path.basename(pdf_path),
            "pages": 0,
            "tables_found": 0,
            "extraction_method": "pdfplumber_primary",
        }

        try:
            with pdfplumber.open(pdf_path) as pdf:
                self.metadata["pages"] = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        self.raw_text += f"\n--- Page {i + 1} ---\n{text}"

                    tables = page.extract_tables()
                    for table in tables:
                        if table and len(table) > 1:
                            try:
                                headers = [
                                    str(h).strip() if h else f"col_{j}"
                                    for j, h in enumerate(table[0])
                                ]
                                df = pd.DataFrame(table[1:], columns=headers)
                                self.raw_tables.append(
                                    {
                                        "page": i + 1,
                                        "dataframe": df,
                                        "raw": table,
                                        "shape": df.shape,
                                    }
                                )
                                self.metadata["tables_found"] += 1
                            except Exception as e:
                                logger.warning(f"Table extraction error on page {i + 1}: {e}")
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            self.metadata["extraction_method"] = "pymupdf_fallback"

        # Fallback / supplement with PyMuPDF
        if len(self.raw_text.strip()) < 200 or self.metadata["tables_found"] == 0:
            try:
                doc = fitz.open(pdf_path)
                if self.metadata["extraction_method"] == "pymupdf_fallback":
                    self.raw_text = ""

                for page in doc:
                    page_num = page.number + 1
                    text = page.get_text()
                    if self.metadata["extraction_method"] == "pymupdf_fallback":
                        self.raw_text += f"\n--- Page {page_num} ---\n{text}"

                    tabs = page.find_tables()
                    if tabs.tables:
                        for tab in tabs.tables:
                            df = tab.to_pandas()
                            if not df.empty:
                                self.raw_tables.append(
                                    {
                                        "page": page_num,
                                        "dataframe": df,
                                        "raw": tab.extract(),
                                        "shape": df.shape,
                                        "source": "pymupdf",
                                    }
                                )
                                self.metadata["tables_found"] += 1
                doc.close()
            except Exception as e:
                logger.error(f"PyMuPDF fallback failed: {e}")

        return {
            "text": self.raw_text,
            "tables": self.raw_tables,
            "metadata": self.metadata,
        }