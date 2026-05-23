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
# LAYOUT B PARSER
# ============================================================

class LayoutNationalTrialsParser(BaseParser):

    KNOWN_CLUBS = sorted([
        "Carleton Place",
        "False Creek",
        "Lac-Beauport",
        "Lac-Sergent",
        "Trois Rivieres",
        "Trois-Rivières",
        "Pointe-Claire",
        "Balmy Beach",
        "North Bay",
        "Richmond Hill",
        "Sack-a-Wa",
        "Mississauga",
        "Peterborough",
        "Sherbrooke",
        "Shawinigan",
        "Otterburn",
        "Kamloops",
        "Sydenham",
        "Cascades",
        "Wascana",
        "Calgary",
        "Burloak",
        "Cheema",
        "Banook",
        "Lachine",
        "Maskwa",
        "Mic Mac",
        "Pisiquid",
        "Rideau",
        "Ottawa",
        "Senobe",
        "Toba",
        "Ridge",
        "Fort",
    ], key=len, reverse=True)

    STATUS_CODES = [
        "DNF",
        "DNS",
        "DSQ",
        "DQ",
        "SCR",
        "EXC",
        "AB",
    ]

    SKIP_PATTERNS = [
        r"^Place\s+Ln",
        r"^Crew\s*/\s*équipage",
        r"^Time/temps",
        r"^Regatta Results",
        r"^file://",
        r"^\d+\s+of\s+\d+",
        r"^\d{4}-\d{2}-\d{2}",
        r"^Page\s+\d+",
        r"^202\d",
        r"^Printed",
        r"^Generated",
    ]

    EVENT_RE = re.compile(
        r"""
        (
            \b(?:K|C)-?[124]\b
            |
            \b(?:Kayak|Canoe)\b
            |
            \b(?:Single|Double|Four)\b
        )
        .*
        \b\d{3,5}\s*[mM]\b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    RACE_INFO_RE = re.compile(
        r"(?P<time>\d{1,2}:\d{2}\s*[AP]M)"
        r"\s*-\s*Race\s*#(?P<number>\d+)"
        r"\s*-\s*(?P<round>.+)",
        re.IGNORECASE,
    )

    TIME_RE = re.compile(
        r"\b\d{1,2}:\d{2}\.\d{3}\b"
    )

    RESULT_LINE_RE = re.compile(
        r"^\s*(?:\d+|DNF|DNS|DSQ|DQ|SCR|EXC|AB)\s+\d+",
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__("layout_b")

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

        events: List[Event] = []

        try:
            raw_text = extracted_data.get("text", "")
            events = self._parse_text(raw_text)

        except Exception as e:
            logger.exception("Text parse failed")
            self._add_warning(f"Text parsing failed: {e}")

        result.events = events
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
            # SKIP METADATA
            # ------------------------------------------------

            if any(rx.search(line) for rx in skip_res):
                continue

            # ------------------------------------------------
            # EVENT DETECTION
            # ------------------------------------------------

            if (
                self.EVENT_RE.search(line)
                and "Race #" not in line
                and len(line) < 140
            ):

                if current_event and current_event.results:
                    events.append(current_event)

                current_event_name = line
                current_event = Event(line)

                continue

            # ------------------------------------------------
            # RACE INFO
            # ------------------------------------------------

            race_match = self.RACE_INFO_RE.match(line)

            if race_match and current_event:

                round_label = self._normalise_round(
                    race_match.group("round")
                )

                if current_event.results:

                    events.append(current_event)

                    current_event = Event(
                        current_event_name or current_event.event_name
                    )

                current_event.round = round_label

                current_event.raw_data.update({
                    "race_number": race_match.group("number"),
                    "race_time": race_match.group("time"),
                    "round_raw": race_match.group("round"),
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

        # remove duplicates
        deduped = []
        seen = set()

        for ev in events:

            key = (
                ev.event_name,
                ev.round,
                ev.raw_data.get("race_number"),
            )

            if key in seen:
                continue

            seen.add(key)
            deduped.append(ev)

        return deduped

    # ========================================================
    # RESULT PARSER
    # ========================================================

    def _parse_result_line(self, line: str) -> Optional[Result]:

        original = line

        times = self.TIME_RE.findall(line)

        if len(times) < 2:
            return None

        result_time = times[0]
        delta_time = times[1]

        line = self.TIME_RE.sub("", line, count=2).strip()

        # ----------------------------------------------------
        # POSITION / STATUS
        # ----------------------------------------------------

        position = None
        status = None

        status_re = re.compile(
            r"^(%s)\b" % "|".join(self.STATUS_CODES),
            re.IGNORECASE,
        )

        sm = status_re.match(line)

        if sm:

            status = sm.group(1).upper()
            line = line[sm.end():].strip()

        else:

            pm = re.match(r"^(\d+)\s+", line)

            if not pm:
                return None

            position = int(pm.group(1))
            line = line[pm.end():].strip()

        # ----------------------------------------------------
        # LANE
        # ----------------------------------------------------

        lane = None

        lm = re.match(r"^(\d+)\s+", line)

        if lm:
            lane = int(lm.group(1))
            line = line[lm.end():].strip()

        # ----------------------------------------------------
        # CLUB
        # ----------------------------------------------------

        club_found = None

        for club in self.KNOWN_CLUBS:

            if re.search(re.escape(club), line, re.IGNORECASE):

                club_found = club

                line = re.sub(
                    re.escape(club),
                    "",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                ).strip()

                break

        if not club_found:
            return None

        # ----------------------------------------------------
        # ATHLETE NAME
        # ----------------------------------------------------

        athlete_name = re.sub(r"\s+", " ", line)
        athlete_name = athlete_name.strip(" ,")

        if not athlete_name:
            return None

        return Result(
            position=position,
            lane=lane,
            athlete=Athlete(athlete_name),
            club=club_found,
            time=result_time,
            delta=delta_time,
            raw_data={
                "line": original,
                "status": status,
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

        if "c-final" in lower:
            return "C-Final"

        if "b-final" in lower:
            return "B-Final"

        if "final" in lower:
            return "Final"

        if "semi" in lower:
            return "Semi-final"

        if "heat" in lower:
            return "Heat"

        return label.strip()


# ============================================================
# ALIAS
# ============================================================

LayoutBParser = LayoutNationalTrialsParser


# ============================================================
# PDF EXTRACTION
# ============================================================

def _extract_text_from_pdf(pdf_path: str) -> str:

    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pip install pdfplumber")

    pages_text: List[str] = []

    result_row_re = re.compile(
        r"^\s*(?:\d+|DNF|DNS|DSQ|DQ|SCR|EXC|AB)\s+\d+\s+.+\d{1,2}:\d{2}\.\d{3}",
        re.IGNORECASE,
    )

    started_results = False

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            text = page.extract_text() or ""

            text = text.strip()

            if not text:
                continue

            lines = text.splitlines()

            # ------------------------------------------------
            # SKIP TABLE OF CONTENTS / RACE SCHEDULE
            # ------------------------------------------------

            if not started_results:

                found_result = any(
                    result_row_re.search(line)
                    or "Place Ln" in line
                    or "Time Delta" in line
                    for line in lines
                )

                if not found_result:
                    continue

                started_results = True

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

    parser = LayoutNationalTrialsParser()

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

            status = r.raw_data.get("status")

            status_txt = (
                f" [{status}]"
                if status else ""
            )

            pos_txt = (
                str(r.position)
                if r.position is not None
                else "-"
            )

            print(
                f"{pos_txt:>3} | "
                f"Lane {r.lane:<2} | "
                f"{r.athlete.raw_name:<45} | "
                f"{r.club:<18} | "
                f"{r.time}{status_txt}"
            )

    if result.parsing_warnings:

        print("\nWARNINGS:")

        for w in result.parsing_warnings:
            print("-", w)

    if result.failed_rows:

        print(f"\nFAILED ROWS ({len(result.failed_rows)}):")

        for row in result.failed_rows[:50]:
            print("|", row)