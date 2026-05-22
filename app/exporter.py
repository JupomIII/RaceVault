from __future__ import annotations
import json
import os
import logging
from typing import Dict, Any
from datetime import datetime

from .schema import ParseResult, CustomJSONEncoder
from .utils import sanitize_filename

logger = logging.getLogger(__name__)


class JSONExporter:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export(self, parse_result: ParseResult, original_path: str | None = None) -> str:
        basename = os.path.splitext(parse_result.source_file)[0]
        safe_name = sanitize_filename(basename)
        filename = f"{safe_name}.json"
        filepath = os.path.join(self.output_dir, filename)

        counter = 1
        original_filepath = filepath
        while os.path.exists(filepath):
            filename = f"{safe_name}_{counter}.json"
            filepath = os.path.join(self.output_dir, filename)
            counter += 1

        data = parse_result.to_dict()
        data["_export_metadata"] = {
            "exported_at": datetime.now().isoformat(),
            "exporter_version": "1.0.0",
            "schema_version": "1.0.0",
            "original_path": original_path,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)

        logger.info(f"Exported JSON to {filepath}")
        return filepath