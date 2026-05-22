from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import json


class MatchType(Enum):
    EXACT = "exact"
    FUZZY_KNOWN = "fuzzy_known"
    TITLE_CASE = "title_case"
    REVERSED_UPPERCASE = "reversed_uppercase"
    INITIAL_UPPERCASE = "initial_uppercase"
    COMPLEX_UPPERCASE = "complex_uppercase"
    NORMALIZED_CASE = "normalized_case"
    UNKNOWN = "unknown"


@dataclass
class Athlete:
    raw_name: str
    normalized_name: Optional[str] = None
    confidence: float = 0.0
    match_type: str = MatchType.UNKNOWN.value
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    position: Optional[int] = None
    athlete: Optional[Athlete] = None
    club: Optional[str] = None
    time: Optional[str] = None
    lane: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class Event:
    event_name: Optional[str] = None
    round: Optional[str] = None
    results: List[Result] = field(default_factory=list)
    confidence: float = 0.0
    raw_headers: List[str] = field(default_factory=list)


@dataclass
class ParseResult:
    source_file: Optional[str] = None
    layout_type: Optional[str] = None
    layout_info: Dict[str, Any] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)
    failed_rows: List[Dict[str, Any]] = field(default_factory=list)
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "layout_type": self.layout_type,
            "confidence": self.confidence,
            "extraction_metadata": self.extraction_metadata,
            "layout_info": self.layout_info,
            "parsing_warnings": self.parsing_warnings,
            "failed_rows": self.failed_rows,
            "events": [self._event_to_dict(event) for event in self.events],
        }

    def _event_to_dict(self, event: Event) -> Dict[str, Any]:
        return {
            "event_name": event.event_name,
            "round": event.round,
            "confidence": event.confidence,
            "raw_headers": event.raw_headers,
            "results": [self._result_to_dict(result) for result in event.results],
        }

    def _result_to_dict(self, result: Result) -> Dict[str, Any]:
        return {
            "position": result.position,
            "athlete": self._athlete_to_dict(result.athlete),
            "club": result.club,
            "time": result.time,
            "lane": result.lane,
            "confidence": result.confidence,
            "warnings": result.warnings,
            "raw_data": result.raw_data,
        }

    @staticmethod
    def _athlete_to_dict(athlete: Optional[Athlete]) -> Optional[Dict[str, Any]]:
        if athlete is None:
            return None
        return {
            "raw_name": athlete.raw_name,
            "normalized_name": athlete.normalized_name,
            "confidence": athlete.confidence,
            "match_type": athlete.match_type,
            "metadata": athlete.metadata,
        }


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return json.JSONEncoder.default(self, obj)
