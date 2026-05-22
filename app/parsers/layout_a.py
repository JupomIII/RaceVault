from __future__ import annotations
from typing import Dict, Any, List, Optional
import pandas as pd
import re
import logging

from .base_parser import BaseParser
from ..schema import Event, Result, Athlete, ParseResult

logger = logging.getLogger(__name__)


class LayoutAParser(BaseParser):
    def __init__(self):
        super().__init__("layout_a")

    def parse(self, extracted_data: Dict[str, Any], layout_info: Dict[str, Any]) -> ParseResult:
        result = ParseResult(
            source_file=extracted_data["metadata"]["file"],
            layout_type=self.layout_type,
        )

        tables = extracted_data.get("tables", [])
        table_idx = layout_info.get("table_index")

        if table_idx is not None and 0 <= table_idx < len(tables):
            df = tables[table_idx]["dataframe"]
            result.events = self._parse_dataframe(df)
        else:
            result.events = self._parse_text(extracted_data.get("text", ""))

        result.parsing_warnings = self.warnings
        result.failed_rows = self.failed_rows
        return result

    def _parse_dataframe(self, df: pd.DataFrame) -> List[Event]:
        events: List[Event] = []
        current_event = Event()

        for _, row in df.iterrows():
            row_dict = row.to_dict()

            if self._is_likely_event_header(row_dict):
                if current_event.results:
                    events.append(current_event)
                current_event = self._extract_event_info(row_dict)
                continue

            result = self._create_result_from_row(
                row_dict,
                name_candidates=["name", "athlete", "competitor", "paddler"],
                pos_candidates=["rank", "pos", "position", "place", "no"],
                time_candidates=["time", "result", "finish", "net"],
                club_candidates=["club", "team", "country", "nation"],
                lane_candidates=["lane", "boat", "ship"],
            )

            if result:
                current_event.results.append(result)
            else:
                self._add_failed_row(row_dict, "Could not extract result from row")

        if current_event.results:
            events.append(current_event)

        return events

    def _parse_text(self, text: str) -> List[Event]:
        events: List[Event] = []
        lines = text.split("\n")
        current_event = Event()

        result_pattern = re.compile(
            r"^\s*(\d{1,3})[\s\.]+([A-Za-z\s\-\.]+?)[\s\.]+(\d{1,2}:\d{2}\.\d{2,3})"
        )

        for line in lines:
            line = line.strip()
            if not line or line.startswith("---"):
                continue

            lower = line.lower()
            if any(k in lower for k in ["k1", "k2", "c1", "c2", "final", "heat", "semi"]) and not result_pattern.match(line):
                if current_event.results:
                    events.append(current_event)
                current_event = Event(event_name=line)
                if "final" in lower:
                    current_event.round = "Final"
                elif "semi" in lower:
                    current_event.round = "Semi-final"
                elif "heat" in lower:
                    current_event.round = "Heat"
                continue

            match = result_pattern.match(line)
            if match:
                pos, name, time = match.groups()
                result = Result(
                    position=int(pos.strip()),
                    athlete=Athlete(raw_name=name.strip()),
                    time=time.strip(),
                    raw_data={"line": line},
                )
                current_event.results.append(result)

        if current_event.results:
            events.append(current_event)

        if not events:
            self._add_warning("Text fallback produced no events")

        return events