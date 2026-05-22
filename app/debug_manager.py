from __future__ import annotations
import json
import os
import logging
from typing import Dict, Any
from datetime import datetime

from .schema import ParseResult
from .utils import sanitize_filename

logger = logging.getLogger(__name__)


class DebugManager:
    def __init__(self, debug_dir: str = "debug"):
        self.debug_dir = debug_dir
        os.makedirs(debug_dir, exist_ok=True)

    def save_artifacts(
        self,
        source_file: str,
        extracted_data: Dict[str, Any],
        layout_info: Dict[str, Any],
        parse_result: ParseResult,
    ) -> Dict[str, str]:
        basename = os.path.splitext(source_file)[0]
        safe_name = sanitize_filename(basename)
        run_dir = os.path.join(
            self.debug_dir, f"{safe_name}_{datetime.now().strftime('%H%M%S')}"
        )
        os.makedirs(run_dir, exist_ok=True)

        artifacts: Dict[str, str] = {}

        # Raw text
        text_path = os.path.join(run_dir, "raw_text.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(extracted_data.get("text", ""))
        artifacts["raw_text"] = text_path

        # Raw tables
        tables = extracted_data.get("tables", [])
        for i, table in enumerate(tables):
            table_path = os.path.join(
                run_dir, f"raw_table_{i + 1}_page{table.get('page', '?')}.csv"
            )
            df = table.get("dataframe")
            if df is not None:
                df.to_csv(table_path, index=False, encoding="utf-8")
                artifacts[f"table_{i + 1}"] = table_path

        # Layout detection
        layout_path = os.path.join(run_dir, "layout_detection.json")
        with open(layout_path, "w", encoding="utf-8") as f:
            json.dump(layout_info, f, indent=2)
        artifacts["layout_detection"] = layout_path

        # Normalization logs
        norm_logs = []
        for event in parse_result.events:
            for result in event.results:
                if result.athlete:
                    norm_logs.append(
                        {
                            "raw": result.athlete.raw_name,
                            "normalized": result.athlete.normalized_name,
                            "confidence": result.athlete.confidence,
                            "match_type": result.athlete.match_type,
                            "metadata": result.athlete.metadata,
                        }
                    )

        norm_path = os.path.join(run_dir, "normalization_logs.json")
        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(norm_logs, f, indent=2)
        artifacts["normalization_logs"] = norm_path

        # Warnings and failed rows
        warnings_path = os.path.join(run_dir, "parsing_warnings.json")
        with open(warnings_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "parse_warnings": parse_result.parsing_warnings,
                    "failed_rows": parse_result.failed_rows,
                },
                f,
                indent=2,
            )
        artifacts["warnings"] = warnings_path

        logger.info(f"Debug artifacts saved to {run_dir}")
        return artifacts