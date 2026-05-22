from __future__ import annotations
import re
import logging
from typing import Tuple, Optional, List, Dict, Any
from rapidfuzz import fuzz
from unidecode import unidecode

from .schema import MatchType

logger = logging.getLogger(__name__)


class NameCleaner:
    def __init__(self, known_athletes: Optional[List[str]] = None):
        self.known_athletes = known_athletes or []
        self.known_normalized = [self._basic_normalize(n) for n in self.known_athletes]

    def normalize(self, raw_name: str) -> Tuple[Optional[str], float, str, Dict[str, Any]]:
        if not raw_name or not isinstance(raw_name, str):
            return None, 0.0, MatchType.UNKNOWN.value, {"error": "invalid_input"}

        original = raw_name.strip()
        metadata: Dict[str, Any] = {"original": original}

        # Step 1: Comma reversal "Smith, John" -> "John Smith"
        if "," in original:
            parts = [p.strip() for p in original.split(",")]
            if len(parts) >= 2:
                last = parts[0]
                first = " ".join(parts[1:])
                original = f"{first} {last}"
                metadata["comma_reversed"] = True
                metadata["comma_parts"] = parts

        # Step 2: Basic cleaning
        cleaned = unidecode(original)
        cleaned = re.sub(r"[^\w\s\-\.]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        metadata["cleaned"] = cleaned

        if not cleaned:
            return None, 0.0, MatchType.UNKNOWN.value, metadata

        words = cleaned.split()
        if not words:
            return None, 0.0, MatchType.UNKNOWN.value, metadata

        # Step 3: Format detection and routing
        format_type = self._detect_format(words)
        metadata["format_detected"] = format_type

        if format_type == "uppercase":
            normalized, confidence, match_type = self._handle_uppercase(words, metadata)
        elif format_type == "title_case":
            normalized, confidence, match_type = self._handle_title_case(words, metadata)
        else:
            normalized, confidence, match_type = self._handle_mixed_case(words, metadata)

        # Step 4: Fuzzy match against known athletes
        if self.known_athletes and normalized:
            best_match, score = self._fuzzy_match_known(normalized)
            if score >= 90:
                normalized = best_match
                confidence = max(confidence, score / 100.0)
                match_type = MatchType.FUZZY_KNOWN.value
                metadata["fuzzy_matched_to"] = best_match
                metadata["fuzzy_score"] = score

        normalized = self._final_cleanup(normalized)
        return normalized, confidence, match_type, metadata

    def _detect_format(self, words: List[str]) -> str:
        alpha_words = [w for w in words if w.isalpha()]
        if alpha_words and all(w.isupper() and len(w) > 1 for w in alpha_words):
            return "uppercase"
        if all(w[0].isupper() for w in words if w and w[0].isalpha()):
            return "title_case"
        return "mixed_case"

    def _handle_uppercase(
        self, words: List[str], metadata: Dict[str, Any]
    ) -> Tuple[str, float, str]:
        categorized = []
        for w in words:
            w_clean = w.replace(".", "")
            if w_clean.isalpha() and (len(w_clean) <= 2 or w.endswith(".")):
                categorized.append(("initial", w))
            elif w.isupper() and len(w) > 1:
                categorized.append(("upper", w))
            else:
                categorized.append(("mixed", w))

        first_parts: List[str] = []
        last_parts: List[str] = []

        mixed_indices = [i for i, (cat, _) in enumerate(categorized) if cat == "mixed"]
        initial_indices = [i for i, (cat, _) in enumerate(categorized) if cat == "initial"]

        if mixed_indices:
            first_mixed = min(mixed_indices)
            last_parts = [categorized[i][1] for i in range(first_mixed)]
            first_parts = [categorized[i][1] for i in range(first_mixed, len(categorized))]
        elif initial_indices:
            if max(initial_indices) > 0 and categorized[0][0] == "upper":
                # "SMITH J" -> last=SMITH, first=J
                transition = min(initial_indices)
                last_parts = [categorized[i][1] for i in range(transition)]
                first_parts = [categorized[i][1] for i in range(transition, len(categorized))]
            else:
                # "J SMITH" -> first=J, last=SMITH
                transition = max(initial_indices) + 1
                first_parts = [categorized[i][1] for i in range(transition)]
                last_parts = [categorized[i][1] for i in range(transition, len(categorized))]
        else:
            if len(words) == 2:
                last_parts = [words[0]]
                first_parts = [words[1]]
            else:
                last_parts = words[:-1]
                first_parts = [words[-1]]

        formatted_first = []
        for w in first_parts:
            w_clean = w.replace(".", "")
            if len(w_clean) <= 2 and w_clean.isalpha():
                formatted_first.append(w_clean.title() + ".")
            else:
                formatted_first.append(w.title())

        formatted_last = [w.title() for w in last_parts]
        normalized = f"{' '.join(formatted_first)} {' '.join(formatted_last)}".strip()

        if mixed_indices:
            return normalized, 0.85, MatchType.REVERSED_UPPERCASE.value
        if len(words) == 2:
            return normalized, 0.85, MatchType.REVERSED_UPPERCASE.value
        return normalized, 0.70, MatchType.COMPLEX_UPPERCASE.value

    def _handle_title_case(
        self, words: List[str], metadata: Dict[str, Any]
    ) -> Tuple[str, float, str]:
        return " ".join(words), 0.95, MatchType.TITLE_CASE.value

    def _handle_mixed_case(
        self, words: List[str], metadata: Dict[str, Any]
    ) -> Tuple[str, float, str]:
        normalized = " ".join(w.capitalize() for w in words)
        return normalized, 0.80, MatchType.NORMALIZED_CASE.value

    def _basic_normalize(self, name: str) -> str:
        return unidecode(name).lower().strip()

    def _fuzzy_match_known(self, name: str) -> Tuple[str, float]:
        best_score = 0.0
        best_match = name
        norm_name = self._basic_normalize(name)

        for known, known_norm in zip(self.known_athletes, self.known_normalized):
            score = fuzz.token_sort_ratio(norm_name, known_norm)
            if score > best_score:
                best_score = score
                best_match = known

        return best_match, best_score

    def _final_cleanup(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        name = re.sub(r"\s*\.\s*", ". ", name)
        name = re.sub(r"\.\s*$", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def detect_duplicates(
        self, athletes: List[str], threshold: float = 85.0
    ) -> List[Tuple[str, str, float]]:
        duplicates = []
        normalized = [(a, self._basic_normalize(a)) for a in athletes]

        for i, (name1, norm1) in enumerate(normalized):
            for j, (name2, norm2) in enumerate(normalized):
                if i >= j:
                    continue
                score = fuzz.ratio(norm1, norm2)
                if score >= threshold:
                    duplicates.append((name1, name2, score))

        return duplicates