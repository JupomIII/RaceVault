from __future__ import annotations

from typing import Dict, Any, List, Optional
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)


# ============================================================
# LIGHTWEIGHT SCHEMA
# ============================================================

class Athlete:
    def __init__(self, raw_name: str):
        self.raw_name = raw_name.strip()

    def __repr__(self):
        return f"Athlete({self.raw_name!r})"


class Result:
    def __init__(
        self,
        position: Optional[int],
        lane: Optional[int],
        athlete: Athlete,
        club: str,
        time: Optional[str],
        delta: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ):
        self.position = position
        self.lane = lane
        self.athlete = athlete
        self.club = club
        self.time = time
        self.delta = delta
        self.raw_data = raw_data or {}

    def __repr__(self):
        return (
            f"Result(pos={self.position}, lane={self.lane}, "
            f"athlete={self.athlete}, club={self.club!r}, time={self.time!r})"
        )


class Event:
    def __init__(self, event_name: str):
        self.event_name = event_name.strip()
        self.round: Optional[str] = None
        self.results: List[Result] = []
        self.raw_data: dict = {}

    def __repr__(self):
        return (
            f"Event({self.event_name!r}, round={self.round!r}, "
            f"results={len(self.results)})"
        )


class ParseResult:
    def __init__(self, source_file: str, layout_type: str):
        self.source_file = source_file
        self.layout_type = layout_type
        self.events: List[Event] = []
        self.parsing_warnings: List[str] = []
        self.failed_rows: List[str] = []

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "layout_type": self.layout_type,
            "events": [
                {
                    "event_name": event.event_name,
                    "round": event.round,
                    "raw_data": event.raw_data,
                    "results": [
                        {
                            "position": result.position,
                            "lane": result.lane,
                            "athlete": result.athlete.raw_name,
                            "club": result.club,
                            "time": result.time,
                            "delta": result.delta,
                            "raw_data": result.raw_data,
                        }
                        for result in event.results
                    ],
                }
                for event in self.events
            ],
            "parsing_warnings": self.parsing_warnings,
            "failed_rows": self.failed_rows,
        }


# ============================================================
# BASE PARSER
# ============================================================

class BaseParser:
    def __init__(self, layout_type: str):
        self.layout_type = layout_type
        self.warnings: List[str] = []
        self.failed_rows: List[str] = []

    def _add_warning(self, msg: str):
        logger.warning(msg)
        self.warnings.append(msg)

    def parse(self, extracted_data: Dict[str, Any], layout_info: Dict[str, Any]) -> ParseResult:
        raise NotImplementedError


# ============================================================
# LAYOUT A PARSER
# ============================================================

class LayoutAParser(BaseParser):

    KNOWN_CLUBS = sorted([
        "Lac-Beauport",
        "Trois-Rivières",
        "Pointe-Claire",
        "Carleton Place",
        "False Creek",
        "Richmond Hill",
        "North Bay",
        "Balmy Beach",
        "Mississauga",
        "Peterborough",
        "Shawinigan",
        "Sherbrooke",
        "Otterburn",
        "Lachine",
        "Cascade",
        "Cascades",
        "Burloak",
        "Cheema",
        "Banook",
        "Rideau",
        "Mic Mac",
        "Pisiquid",
        "Calgary",
        "Wascana",
        "Kamloops",
        "Senobe",
        "Toba",
    ], key=len, reverse=True)

    SKIP_PATTERNS = [
        r"^Essais",
        r"^Bassin olympique",
        r"^Résultats$",
        r"^Couloir",
        r"^Jour\s+\d+",
        r"^Les\s+\d+",
        r"^\d+$",
    ]

    EVENT_RE = re.compile(
        r"""
        ^
        (Femmes|Hommes)
        \s+
        (K|C)-1
        \s+
        \d{3,4}m
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    RACE_RE = re.compile(
        r"""
        ^
        (?P<time>\d{1,2}:\d{2})
        \s+
        Course\s+n[°o]
        \s*
        (?P<number>\d+)
        .*
        (?P<round>Éliminatoire\s+\d+|Finale)
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    RESULT_RE = re.compile(
        r"""
        ^
        (?P<lane>\d+)
        \s+
        (?P<club>.+?)
        \s+
        (?P<seed>\d+)
        \s+
        (?P<athlete>.+?)
        \s+
        (?P<position>\d+)
        \s+
        (?P<time>\d+:\d{2},\d{2})
        $
        """,
        re.VERBOSE,
    )

    def __init__(self):
        super().__init__("layout_a")

    # ========================================================
    # MAIN PARSE
    # ========================================================

    def parse(
        self,
        extracted_data: Dict[str, Any],
        layout_info: Dict[str, Any],
    ) -> ParseResult:

        result = ParseResult(
            source_file=extracted_data.get("metadata", {}).get("file", "unknown"),
            layout_type=self.layout_type,
        )

        try:

            raw_text = extracted_data.get("text", "")

            result.events = self._parse_text(raw_text)

        except Exception as e:

            logger.exception("Layout A parse failed")
            self._add_warning(str(e))

        result.parsing_warnings = self.warnings
        result.failed_rows = self.failed_rows

        return result

    # ========================================================
    # TEXT PARSER
    # ========================================================

    def _parse_text(self, text: str) -> List[Event]:

        events: List[Event] = []

        current_event: Optional[Event] = None
        current_event_name: Optional[str] = None

        skip_res = [
            re.compile(p, re.IGNORECASE)
            for p in self.SKIP_PATTERNS
        ]

        for raw_line in text.splitlines():

            line = self._clean_line(raw_line)

            if not line:
                continue

            # ------------------------------------------------
            # SKIP USELESS LINES
            # ------------------------------------------------

            if any(rx.search(line) for rx in skip_res):
                continue

            # ------------------------------------------------
            # EVENT
            # ------------------------------------------------

            if self.EVENT_RE.match(line):

                if current_event and current_event.results:
                    events.append(current_event)

                current_event_name = line
                current_event = Event(line)

                continue

            # ------------------------------------------------
            # RACE INFO
            # ------------------------------------------------

            race_match = self.RACE_RE.match(line)

            if race_match and current_event:

                round_label = race_match.group("round")

                if current_event.results:

                    events.append(current_event)

                    current_event = Event(
                        current_event_name or current_event.event_name
                    )

                current_event.round = self._normalise_round(
                    round_label
                )

                current_event.raw_data.update({
                    "race_number": race_match.group("number"),
                    "race_time": race_match.group("time"),
                    "round_raw": round_label,
                })

                continue

            # ------------------------------------------------
            # NO EVENT
            # ------------------------------------------------

            if current_event is None:
                continue

            # ------------------------------------------------
            # RESULT LINE
            # ------------------------------------------------

            parsed = self._parse_result_line(line)

            if parsed:
                current_event.results.append(parsed)
            else:
                self.failed_rows.append(line)

        if current_event and current_event.results:
            events.append(current_event)

        return events

    # ========================================================
    # RESULT PARSER
    # ========================================================

    def _parse_result_line(self, line: str) -> Optional[Result]:

        match = self.RESULT_RE.match(line)

        if not match:
            return None

        lane = int(match.group("lane"))

        club = match.group("club").strip()

        athlete = match.group("athlete").strip()

        position = int(match.group("position"))

        race_time = match.group("time").replace(",", ".")

        # validate club
        matched_club = None

        for known in self.KNOWN_CLUBS:

            if known.lower() in club.lower():
                matched_club = known
                break

        if not matched_club:
            matched_club = club

        return Result(
            position=position,
            lane=lane,
            athlete=Athlete(athlete),
            club=matched_club,
            time=race_time,
            delta=None,
            raw_data={
                "raw_line": line,
            },
        )

    # ========================================================
    # UTILITIES
    # ========================================================

    @staticmethod
    def _clean_line(line: str) -> str:

        line = line.replace("\xa0", " ")
        line = re.sub(r"\s+", " ", line)

        return line.strip()

    @staticmethod
    def _normalise_round(label: str) -> str:

        lower = label.lower()

        if "finale" in lower:
            return "Final"

        if "éliminatoire" in lower:
            return "Heat"

        return label.strip()


# ============================================================
# PDF EXTRACTION
# ============================================================

def _extract_text_from_pdf(pdf_path: str) -> str:

    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pip install pdfplumber")

    pages_text: List[str] = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            text = page.extract_text() or ""

            text = text.strip()

            if not text:
                continue

            pages_text.append(text)

    return "\n".join(pages_text)


# ============================================================
# PUBLIC ENTRYPOINT
# ============================================================

def parse_pdf(pdf_path: str) -> ParseResult:

    raw_text = _extract_text_from_pdf(pdf_path)

    extracted_data = {
        "metadata": {
            "file": pdf_path
        },
        "text": raw_text,
        "tables": [],
    }

    parser = LayoutAParser()

    return parser.parse(extracted_data, {})


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    import sys

    pdf_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "results.pdf"
    )

    result = parse_pdf(pdf_path)

    print("\n" + "=" * 80)
    print("FILE:", result.source_file)
    print("EVENTS:", len(result.events))
    print("=" * 80)

    for ev in result.events:

        print(f"\n[{ev.round}] {ev.event_name}")

        if ev.raw_data.get("race_number"):
            print(
                f"Race #{ev.raw_data['race_number']} "
                f"({ev.raw_data.get('race_time', '')})"
            )

        for r in ev.results:

            print(
                f"{r.position:>2} | "
                f"Lane {r.lane:<2} | "
                f"{r.athlete.raw_name:<40} | "
                f"{r.club:<18} | "
                f"{r.time}"
            )

    if result.parsing_warnings:

        print("\nWARNINGS:")

        for w in result.parsing_warnings:
            print("-", w)

    if result.failed_rows:

        print(f"\nFAILED ROWS ({len(result.failed_rows)}):")

        for row in result.failed_rows[:50]:
            print("|", row)