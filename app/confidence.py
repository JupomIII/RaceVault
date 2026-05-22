from __future__ import annotations
import re
from typing import Dict, Any, List
import logging

from .schema import Athlete, Result, Event, ParseResult, MatchType

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    def __init__(self):
        self.time_pattern = re.compile(r"^\d{1,2}:\d{2}\.\d{2,3}$")

    def score_name(self, athlete: Athlete) -> float:
        base = athlete.confidence
        match_type = athlete.match_type or MatchType.UNKNOWN.value

        multipliers = {
            MatchType.EXACT.value: 1.0,
            MatchType.FUZZY_KNOWN.value: 0.95,
            MatchType.TITLE_CASE.value: 0.95,
            MatchType.REVERSED_UPPERCASE.value: 0.85,
            MatchType.INITIAL_UPPERCASE.value: 0.75,
            MatchType.COMPLEX_UPPERCASE.value: 0.70,
            MatchType.NORMALIZED_CASE.value: 0.80,
            MatchType.UNKNOWN.value: 0.50,
        }

        multiplier = multipliers.get(match_type, 0.5)

        if athlete.normalized_name:
            words = athlete.normalized_name.split()
            if len(words) < 2:
                multiplier *= 0.7

        final = base * multiplier
        return round(min(max(final, 0.0), 1.0), 3)

    def score_result(self, result: Result) -> float:
        scores: List[float] = []

        if result.athlete:
            scores.append(self.score_name(result.athlete))
        else:
            scores.append(0.0)

        if result.position is not None and result.position > 0:
            scores.append(1.0)
        else:
            scores.append(0.3)

        if result.time and self._valid_time_format(result.time):
            scores.append(1.0)
        elif result.time:
            scores.append(0.5)
        else:
            scores.append(0.0)

        if result.club:
            scores.append(0.8)
        else:
            scores.append(0.5)

        return round(sum(scores) / len(scores), 3)

    def _valid_time_format(self, time_str: str) -> bool:
        if not time_str:
            return False
        return bool(self.time_pattern.match(str(time_str).strip()))

    def score_event(self, event: Event) -> float:
        if not event.results:
            return 0.0

        scores = [self.score_result(r) for r in event.results]
        avg = sum(scores) / len(scores)

        if not event.event_name:
            avg *= 0.8
        if not event.round:
            avg *= 0.9

        return round(avg, 3)

    def score_parse(self, parse_result: ParseResult) -> float:
        if not parse_result.events:
            return 0.0

        scores = [self.score_event(e) for e in parse_result.events]
        avg = sum(scores) / len(scores)

        warning_penalty = min(len(parse_result.parsing_warnings) * 0.02, 0.2)
        failed_penalty = min(len(parse_result.failed_rows) * 0.01, 0.2)

        avg = max(0.0, avg - warning_penalty - failed_penalty)
        return round(avg, 3)