from __future__ import annotations
import os
import sys
import traceback
import re
from typing import List, Optional
from pathlib import Path

if __package__ is None:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

from app.config import Config
from app.utils import setup_logger, sanitize_filename
from app.extractor import PDFExtractor
from app.layout_detector import LayoutDetector
from app.parsers import get_parser
from app.normalizer import Normalizer
from app.exporter import JSONExporter
from app.schema import ParseResult as SchemaParseResult, Event as SchemaEvent, Result as SchemaResult, Athlete as SchemaAthlete

logger = setup_logger("main", log_file="racevault.log")


class Pipeline:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.config.ensure_dirs()

        self.extractor = PDFExtractor()
        self.layout_detector = LayoutDetector()
        self.normalizer = Normalizer()
        self.exporter = JSONExporter(self.config.output_dir)

    def run(self, reparse_existing: bool = False, move_parsed: bool = False) -> List[str]:
        pdf_files = self._scan_input(reparse_existing=reparse_existing)
        exported_files: List[str] = []

        logger.info(f"Found {len(pdf_files)} PDF(s) to process")

        for pdf_path in pdf_files:
            try:
                result = self.process_file(pdf_path, move_parsed=move_parsed)
                if result["output_path"]:
                    exported_files.append(result["output_path"])
            except Exception as e:
                logger.error(f"Unhandled error processing {pdf_path}: {e}")
                logger.debug(traceback.format_exc())

        logger.info(f"Pipeline complete. Exported {len(exported_files)} file(s).")
        return exported_files

    def process_file(
        self,
        pdf_path: str,
        layout_override: Optional[str] = None,
        extracted: Optional[Dict[str, Any]] = None,
        move_parsed: bool = False,
        pages_per_chunk: Optional[int] = None,
    ) -> Dict[str, Any]:
        filename = os.path.basename(pdf_path)
        logger.info(f"Processing: {filename}")

        if extracted is None:
            extracted = self.extractor.extract(pdf_path)
        logger.debug(
            f"Extracted {extracted['metadata']['pages']} pages, "
            f"{extracted['metadata']['tables_found']} tables"
        )

        layout_info = self.layout_detector.detect(extracted)
        if layout_override is not None:
            layout_info["layout_type"] = layout_override
            layout_info["method"] = "manual"

        if layout_info["layout_type"] is None:
            msg = "Could not detect layout"
            logger.error(msg)
            return {"output_path": None, "layout_info": layout_info, "parse_result": None}

        try:
            parser = get_parser(layout_info["layout_type"])

            # If requested, parse layout_b in page chunks to reduce memory.
            if pages_per_chunk and layout_info.get("layout_type") == "layout_b" and extracted and isinstance(extracted.get("text"), str):
                text = extracted.get("text", "")
                # Split per-page using the extractor marker
                pages = []
                # The extractor inserts markers like "\n--- Page {n} ---\n"
                parts = re.split(r"\n--- Page \d+ ---\n", text)
                if parts and parts[0].strip() == "":
                    parts = parts[1:]

                for p in parts:
                    pages.append(p)

                events_accum = []
                # parse pages in chunks
                for i in range(0, len(pages), pages_per_chunk):
                    chunk_pages = pages[i : i + pages_per_chunk]
                    chunk_text = "\n".join(chunk_pages)
                    try:
                        evs = parser._parse_text(chunk_text)
                        if evs:
                            events_accum.extend(evs)
                    except Exception as e:
                        logger.exception("Chunk parse failed in pipeline")
                        # preserve warning on parser
                        parser._add_warning(f"Chunk parsing failed: {e}")

                # attach accumulated events into a SchemaParseResult directly
                schema_pr = SchemaParseResult()
                schema_pr.source_file = os.path.basename(pdf_path)
                schema_pr.layout_type = layout_info.get("layout_type")
                schema_pr.layout_info = layout_info
                schema_pr.extraction_metadata = extracted.get("metadata", {})
                schema_pr.parsing_warnings = parser.warnings or []
                schema_pr.failed_rows = parser.failed_rows or []

                for ev in events_accum:
                    sev = SchemaEvent()
                    sev.event_name = getattr(ev, "event_name", None)
                    sev.round = getattr(ev, "round", None)
                    sev.raw_headers = getattr(ev, "raw_data", {}) or {}
                    for r in getattr(ev, "results", []):
                        athlete_name = None
                        if hasattr(r, "athletes"):
                            athletes = getattr(r, "athletes") or []
                            if athletes:
                                athlete_name = getattr(athletes[0], "raw_name", str(athletes[0]))
                        elif hasattr(r, "athlete") and getattr(r, "athlete"):
                            athlete_name = getattr(r, "athlete").raw_name

                        sachlete = SchemaAthlete(raw_name=athlete_name) if athlete_name else None

                        sres = SchemaResult()
                        sres.position = getattr(r, "position", None)
                        sres.athlete = sachlete
                        sres.club = getattr(r, "club", None)
                        sres.time = getattr(r, "time", None)
                        sres.lane = getattr(r, "lane", None)
                        sres.raw_data = getattr(r, "raw_data", {}) or {}
                        sres.warnings = getattr(r, "warnings", []) or []

                        sev.results.append(sres)

                    schema_pr.events.append(sev)

                parse_result = schema_pr

            else:
                parse_result = parser.parse(extracted, layout_info)

            # Convert parser-specific lightweight ParseResult into Schema ParseResult
            if not isinstance(parse_result, SchemaParseResult):
                schema_pr = SchemaParseResult()
                schema_pr.source_file = os.path.basename(pdf_path)
                schema_pr.layout_type = layout_info.get("layout_type")
                schema_pr.layout_info = layout_info
                schema_pr.extraction_metadata = extracted.get("metadata", {})

                # copy warnings/failed rows if available
                schema_pr.parsing_warnings = getattr(parse_result, "parsing_warnings", []) or []
                schema_pr.failed_rows = getattr(parse_result, "failed_rows", []) or []

                for ev in getattr(parse_result, "events", []):
                    sev = SchemaEvent()
                    sev.event_name = getattr(ev, "event_name", None)
                    sev.round = getattr(ev, "round", None)
                    sev.raw_headers = getattr(ev, "raw_data", {}) or {}
                    for r in getattr(ev, "results", []):
                        # handle crew boats (list) or single athlete
                        athlete_name = None
                        if hasattr(r, "athletes"):
                            athletes = getattr(r, "athletes") or []
                            if athletes:
                                athlete_name = getattr(athletes[0], "raw_name", str(athletes[0]))
                        elif hasattr(r, "athlete") and getattr(r, "athlete"):
                            athlete_name = getattr(r, "athlete").raw_name

                        sachlete = SchemaAthlete(raw_name=athlete_name) if athlete_name else None

                        sres = SchemaResult()
                        sres.position = getattr(r, "position", None)
                        sres.athlete = sachlete
                        sres.club = getattr(r, "club", None)
                        sres.time = getattr(r, "time", None)
                        sres.lane = getattr(r, "lane", None)
                        sres.raw_data = getattr(r, "raw_data", {}) or {}
                        # ensure warnings list exists
                        sres.warnings = getattr(r, "warnings", []) or []

                        sev.results.append(sres)

                    schema_pr.events.append(sev)

                parse_result = schema_pr
        except Exception as e:
            msg = f"Parser error: {e}"
            logger.error(msg)
            return {"output_path": None, "layout_info": layout_info, "parse_result": None}

        parse_result.source_file = filename
        parse_result.extraction_metadata = extracted["metadata"]
        parse_result.layout_info = layout_info

        parse_result = self.normalizer.normalize(parse_result)

        output_path = self.exporter.export(parse_result, original_path=pdf_path)

        logger.info(
            f"Successfully processed {filename} -> {output_path} "
            f"(confidence: {parse_result.confidence:.2f})"
        )

        return {"output_path": output_path, "layout_info": layout_info, "parse_result": parse_result}

    def _scan_input(self, reparse_existing: bool = False) -> List[str]:
        pdf_files = []
        for ext in self.config.supported_extensions:
            pdf_files.extend(Path(self.config.input_dir).glob(f"*{ext}"))

        input_paths = sorted([str(f) for f in pdf_files])
        if reparse_existing:
            return input_paths

        filtered_paths: List[str] = []
        output_dir = Path(self.config.output_dir)
        for pdf_path in input_paths:
            basename = sanitize_filename(Path(pdf_path).stem)
            existing_outputs = list(output_dir.glob(f"{basename}*.json"))
            if not existing_outputs:
                filtered_paths.append(pdf_path)

        return filtered_paths

    def _process_single(self, pdf_path: str) -> Optional[str]:
        filename = os.path.basename(pdf_path)
        logger.info(f"Processing: {filename}")

        # 1. Extraction
        extracted = self.extractor.extract(pdf_path)
        logger.debug(
            f"Extracted {extracted['metadata']['pages']} pages, "
            f"{extracted['metadata']['tables_found']} tables"
        )

        # 2. Layout Detection
        layout_info = self.layout_detector.detect(extracted)

        if layout_info["layout_type"] is None:
            msg = "Could not detect layout"
            logger.error(msg)
            return None

        # 3. Parsing
        try:
            parser = get_parser(layout_info["layout_type"])
            parse_result = parser.parse(extracted, layout_info)
        except Exception as e:
            msg = f"Parser error: {e}"
            logger.error(msg)
            return None

        parse_result.source_file = filename
        parse_result.extraction_metadata = extracted["metadata"]

        # 4. Normalization
        parse_result = self.normalizer.normalize(parse_result)

        # 5. Export
        output_path = self.exporter.export(parse_result, original_path=pdf_path)

        logger.info(
            f"Successfully processed {filename} -> {output_path} "
            f"(confidence: {parse_result.confidence:.2f})"
        )

        return output_path


def main():
    config = Config()
    pipeline = Pipeline(config)
    exported = pipeline.run()
    print(f"\nDone. Exported {len(exported)} result file(s) to '{config.output_dir}/'")


if __name__ == "__main__":
    main()