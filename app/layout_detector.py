from __future__ import annotations
from typing import Dict, Any, List, Optional
import pandas as pd
import re
import logging

from app.parsers import PARSER_REGISTRY, get_parser

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

        signature_scores: Dict[str, float] = {}
        signature_table_indices: Dict[str, Optional[int]] = {}
        all_scores: Dict[str, Dict[str, float]] = {}

        for layout_name in self.SIGNATURES:
            signature_scores[layout_name] = 0.0
            signature_table_indices[layout_name] = None
            all_scores[layout_name] = {"signature": 0.0, "parse": 0.0}

        for idx, table_info in enumerate(tables):
            df = table_info.get("dataframe")
            if df is None or df.empty:
                continue

            scores = self._score_table(df)
            for layout_name, score in scores.items():
                if score > signature_scores[layout_name]:
                    signature_scores[layout_name] = score
                    signature_table_indices[layout_name] = idx
                all_scores[layout_name]["signature"] = max(
                    all_scores[layout_name]["signature"], score
                )

        if not tables or max(signature_scores.values(), default=0.0) < 0.4:
            text_scores = self._score_text(text)
            for layout_name, score in text_scores.items():
                signature_scores[layout_name] = max(signature_scores[layout_name], score)
                all_scores[layout_name]["signature"] = max(
                    all_scores[layout_name]["signature"], score
                )

        best_signature_layout = max(signature_scores, key=signature_scores.get)
        best_signature_score = signature_scores[best_signature_layout]

        best_parse_layout: Optional[str] = None
        best_parse_score = 0.0

        for layout_name in PARSER_REGISTRY:
            parser = get_parser(layout_name)
            layout_info = {
                "layout_type": layout_name,
                "table_index": signature_table_indices.get(layout_name),
            }
            try:
                parse_result = parser.parse(extracted_data, layout_info)
                parse_score = self._score_parse_result(parse_result)
            except Exception:
                parse_score = 0.0

            all_scores[layout_name]["parse"] = parse_score

            if parse_score > best_parse_score:
                best_parse_score = parse_score
                best_parse_layout = layout_name

        if best_parse_layout is None:
            best_layout = best_signature_layout
            best_score = best_signature_score
            selection_method = "signature"
        elif best_parse_score >= best_signature_score or best_signature_score < 0.5:
            best_layout = best_parse_layout
            best_score = best_parse_score
            selection_method = "parse"
        else:
            best_layout = best_signature_layout
            best_score = best_signature_score
            selection_method = "signature"

        self.detected_layout = best_layout
        self.confidence = best_score

        result = {
            "layout_type": best_layout,
            "confidence": best_score,
            "table_index": signature_table_indices.get(best_layout),
            "all_scores": all_scores,
            "method": selection_method,
        }

        logger.info(
            f"Layout detection: {best_layout} (confidence: {best_score:.2f}, method: {selection_method})"
        )
        return result

    def _score_parse_result(self, parse_result: Any) -> float:
        if not getattr(parse_result, "events", None):
            return 0.0

        total_results = 0
        event_scores: List[float] = []

        for event in parse_result.events:
            results = getattr(event, "results", [])
            if not results:
                continue

            total_results += len(results)
            row_scores: List[float] = []
            for result in results:
                score = 0.0
                score += 1.0 if result.athlete and getattr(result.athlete, "raw_name", None) else 0.0
                score += 1.0 if result.position is not None and result.position > 0 else 0.0
                score += 1.0 if result.time else 0.0
                score += 0.8 if result.club else 0.4
                row_scores.append(score / 4.0)

            avg_row_score = sum(row_scores) / len(row_scores)
            event_bonus = 0.0
            event_bonus += 0.1 if getattr(event, "event_name", None) else 0.0
            event_bonus += 0.05 if getattr(event, "round", None) else 0.0
            event_scores.append(min(1.0, avg_row_score + event_bonus))

        if not event_scores:
            return 0.0

        base_score = sum(event_scores) / len(event_scores)
        warning_penalty = min(len(getattr(parse_result, "parsing_warnings", [])) * 0.03, 0.2)
        failed_penalty = min(len(getattr(parse_result, "failed_rows", [])) * 0.02, 0.2)
        result_bonus = min(total_results / 20.0, 1.0) * 0.25

        score = base_score * 0.8 + result_bonus - warning_penalty - failed_penalty
        return round(max(0.0, min(score, 1.0)), 3)

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