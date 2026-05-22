from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import re
import pandas as pd
import logging

from ..schema import Event, Result, Athlete, ParseResult

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    def __init__(self, layout_type: str):
        self.layout_type = layout_type
        self.warnings: List[str] = []
        self.failed_rows: List[Dict[str, Any]] = []

    @abstractmethod
    def parse(self, extracted_data: Dict[str, Any], layout_info: Dict[str, Any]) -> ParseResult:
        pass

    def _clean_value(self, val: Any) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        return s if s and s.lower() != "none" else None

    def _safe_int(self, val: Any) -> Optional[int]:
        if val is None:
            return None
        try:
            cleaned = re.sub(r"[^\d]", "", str(val))
            return int(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    def _find_column(self, row: Dict[str, Any], candidates: List[str]) -> Any:
        for key, val in row.items():
            norm = self._normalize_header(str(key))
            for cand in candidates:
                if cand in norm:
                    return val
        return None

    def _normalize_header(self, header: str) -> str:
        if not header:
            return ""
        h = str(header).lower().strip()
        h = re.sub(r"[^\w\s]", "", h)
        h = re.sub(r"\s+", " ", h)
        return h

    def _is_likely_event_header(self, row: Dict[str, Any]) -> bool:
        vals = [str(v).strip() for v in row.values() if v is not None]
        combined = " ".join(vals).lower()

        has_event_keywords = any(
            k in combined
            for k in [
                "k1", "k2", "c1", "c2", "men", "women", "junior", "senior",
                "final", "semi", "heat", "quarter", "race", "m ", "500", "1000", "200",
            ]
        )
        has_numbers = any(
            re.match(r"^\d+$", str(v).strip()) for v in row.values() if v
        )
        return has_event_keywords and not has_numbers

    def _extract_event_info(self, row: Dict[str, Any]) -> Event:
        vals = [str(v).strip() for v in row.values() if v is not None]
        text = " ".join(vals)

        event = Event(event_name=text, raw_headers=list(row.keys()))

        lower = text.lower()
        if "final" in lower:
            event.round = "Final"
        elif "semi" in lower:
            event.round = "Semi-final"
        elif "quarter" in lower:
            event.round = "Quarter-final"
        elif "heat" in lower:
            event.round = "Heat"

        if "men" in lower and "women" not in lower:
            event.category = "Men"
        elif "women" in lower and "men" not in lower:
            event.category = "Women"

        return event

    def _create_result_from_row(
        self,
        row: Dict[str, Any],
        name_candidates: List[str],
        pos_candidates: List[str],
        time_candidates: List[str],
        club_candidates: List[str],
        lane_candidates: List[str],
    ) -> Optional[Result]:
        name_val = self._find_column(row, name_candidates)
        if not name_val:
            return None

        result = Result(
            position=self._safe_int(self._find_column(row, pos_candidates)),
            athlete=Athlete(raw_name=str(name_val)),
            club=self._clean_value(self._find_column(row, club_candidates)),
            time=self._clean_value(self._find_column(row, time_candidates)),
            lane=self._safe_int(self._find_column(row, lane_candidates)),
            raw_data=dict(row),
        )
        return result

    def _add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning(msg)

    def _add_failed_row(self, row: Dict[str, Any], reason: str) -> None:
        self.failed_rows.append(
            {"row": dict(row), "reason": reason, "layout": self.layout_type}
        )