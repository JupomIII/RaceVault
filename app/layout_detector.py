from __future__ import annotations
from typing import Dict, Any, List, Optional
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)


class LayoutDetector:
    SIGNATURES = {
        "layout_a": {
            "required": [("rank", 0.35), ("name", 0.35), ("time", 0.30)],
            "optional": [("club", 0.1), ("country", 0.1), ("lane", 0.1), ("pos", 0.05)],
        },
        "layout_b": {
            "required": [("pos", 0.35), ("athlete", 0.35), ("result", 0.30)],
            "optional": [("club", 0.1), ("country", 0.1), ("lane", 0.1)],
        },
        "layout_c": {
            "required": [("lane", 0.35), ("competitor", 0.35), ("finish", 0.30)],
            "optional": [("club", 0.1), ("country", 0.1), ("time", 0.1)],
        },
        "layout_d": {
            "required": [("place", 0.35), ("name", 0.35), ("time", 0.30)],
            "optional": [("club", 0.1), ("country", 0.1)],
        },
    }

    def __init__(self):
        self.detected_layout: Optional[str] = None
        self.confidence: float = 0.0

    def _normalize_header(self, header: str) -> str:
        if not header:
            return ""
        h = str(header).lower().strip()
        h = re.sub(r"[^\w\s]", "", h)
        h = re.sub(r"\s+", " ", h)
        return h

    def _score_table(self, df: pd.DataFrame) -> Dict[str, float]:
        if df.empty:
            return {k: 0.0 for k in self.SIGNATURES}

        normalized_cols = [self._normalize_header(str(c)) for c in df.columns]
        scores: Dict[str, float] = {}

        for layout_name, signature in self.SIGNATURES.items():
            score = 0.0
            req_matched = 0
            req_total = len(signature["required"])

            for req_keyword, req_weight in signature["required"]:
                if any(req_keyword in col for col in normalized_cols):
                    score += req_weight
                    req_matched += 1

            if req_matched < req_total:
                score *= 0.5

            for opt_keyword, opt_weight in signature["optional"]:
                if any(opt_keyword in col for col in normalized_cols):
                    score += opt_weight

            if len(df) >= 3:
                score += 0.1

            scores[layout_name] = min(score, 1.0)

        return scores

    def detect(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        tables = extracted_data.get("tables", [])
        text = extracted_data.get("text", "")

        best_layout: Optional[str] = None
        best_score = 0.0
        best_table_idx: Optional[int] = None
        all_scores: Dict[str, float] = {}

        for idx, table_info in enumerate(tables):
            df = table_info.get("dataframe")
            if df is None or df.empty:
                continue

            scores = self._score_table(df)
            for layout, score in scores.items():
                if score > best_score:
                    best_score = score
                    best_layout = layout
                    best_table_idx = idx
                all_scores[layout] = max(all_scores.get(layout, 0.0), score)

        if best_layout is None or best_score < 0.4:
            text_scores = self._score_text(text)
            for layout, score in text_scores.items():
                all_scores[layout] = max(all_scores.get(layout, 0.0), score)
                if score > best_score:
                    best_score = score
                    best_layout = layout

        self.detected_layout = best_layout
        self.confidence = best_score

        result = {
            "layout_type": best_layout,
            "confidence": best_score,
            "table_index": best_table_idx,
            "all_scores": all_scores,
            "method": "table" if best_table_idx is not None else "text",
        }

        logger.info(f"Layout detection: {best_layout} (confidence: {best_score:.2f})")
        return result

    def _score_text(self, text: str) -> Dict[str, float]:
        text_lower = text.lower()
        scores: Dict[str, float] = {}

        for layout_name, signature in self.SIGNATURES.items():
            score = 0.0
            for req_keyword, req_weight in signature["required"]:
                if re.search(r"\b" + re.escape(req_keyword) + r"\b", text_lower):
                    score += req_weight * 0.8

            for opt_keyword, opt_weight in signature["optional"]:
                if re.search(r"\b" + re.escape(opt_keyword) + r"\b", text_lower):
                    score += opt_weight * 0.5

            scores[layout_name] = min(score, 1.0)

        return scores