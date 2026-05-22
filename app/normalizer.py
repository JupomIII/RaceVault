from __future__ import annotations
from typing import List, Optional
import logging

from .schema import ParseResult, Event, Result, Athlete
from .name_cleaner import NameCleaner
from .confidence import ConfidenceScorer

logger = logging.getLogger(__name__)


class Normalizer:
    def __init__(self, known_athletes: Optional[List[str]] = None):
        self.name_cleaner = NameCleaner(known_athletes)
        self.confidence = ConfidenceScorer()

    def normalize(self, parse_result: ParseResult) -> ParseResult:
        logger.info(
            f"Normalizing {parse_result.source_file} with {len(parse_result.events)} events"
        )

        all_raw_names: List[str] = []
        for event in parse_result.events:
            for result in event.results:
                if result.athlete:
                    all_raw_names.append(result.athlete.raw_name)

        duplicates = self.name_cleaner.detect_duplicates(all_raw_names)
        if duplicates:
            logger.warning(f"Detected {len(duplicates)} potential duplicate athletes")
            parse_result.parsing_warnings.append(
                f"Potential duplicates detected: {len(duplicates)} pairs"
            )

        for event in parse_result.events:
            for result in event.results:
                if result.athlete:
                    raw = result.athlete.raw_name
                    norm_name, conf, match_type, metadata = self.name_cleaner.normalize(raw)

                    result.athlete.normalized_name = norm_name
                    result.athlete.confidence = conf
                    result.athlete.match_type = match_type
                    result.athlete.metadata = metadata

                    result.athlete.confidence = self.confidence.score_name(result.athlete)

                    if result.athlete.confidence < 0.6:
                        result.warnings.append(
                            f"Low name confidence ({result.athlete.confidence}) for '{raw}'"
                        )

                result.confidence = self.confidence.score_result(result)

            event.confidence = self.confidence.score_event(event)

        parse_result.confidence = self.confidence.score_parse(parse_result)
        return parse_result