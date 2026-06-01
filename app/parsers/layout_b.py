from __future__ import annotations

from typing import Dict, Any, List, Optional
import pandas as pd
import re
import logging

from ..name_cleaner import NameCleaner

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
        athletes: List[Athlete],          # now a list for crew boats
        club: str,
        time: Optional[str],
        delta: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ):
        self.position = position
        self.lane = lane
        self.athletes = athletes
        self.club = club
        self.time = time
        self.delta = delta
        self.raw_data = raw_data or {}

    # Backward‑compatible property for single‑athlete results
    @property
    def athlete(self) -> Athlete:
        return self.athletes[0]

    def __repr__(self):
        names = ", ".join(a.raw_name for a in self.athletes)
        return (
            f"Result(pos={self.position}, lane={self.lane}, "
            f"athletes=[{names}], club={self.club!r}, time={self.time!r})"
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
                            "athletes": [a.raw_name for a in result.athletes],
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
        # Limit warnings to avoid memory bloat on large files
        if len(self.warnings) < 1000:
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
        # Additional clubs for 2025 nationals
        "Burnaby",
        "Flatwater North",
        "Greater Edmonton",
        "Brudenell",
        "Saskatoon",
        "Cartierville",
        "Collingwood",
        "Gananoque",
        "Niagara",
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
    STATUS_CODES_PATTERN = "|".join(STATUS_CODES)  # Pre-compile for efficiency

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
        r"^---\s*Page",
        r"^First\s+\d+\s+each\s+heat",
        r"Advancement/Progression",
        r"^Course\s+Break",
        r"^Championnats nationaux de vitesse",
        r"^Heat$",
        r"^\d+$",
        r"^\d+\s+\d{2,4}m$",
        r"^\d+\s*m\s+\d+$",
        r"^best times to Final [AB]",
        r"^\d+\s+\d{1,2}:\d{2}\s+.*\d{1,2}:\d{2}\b",
    ]
    # Pre-compile skip patterns for efficiency
    _SKIP_PATTERNS_COMPILED = None

    EVENT_RE = re.compile(
        r"""
        (
            \b(?:K|C|IC|CC|Vaa)-?\d+(?:[A-Za-z]*)
            |
            \b(?:Kayak|Canoe|Vaa|Single|Double|Four)\b
        )
        (?:.*\b\d{3,5}\s*[mM]\b)?
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
        # Pre-compile regexes for better performance
        if not LayoutNationalTrialsParser._SKIP_PATTERNS_COMPILED:
            LayoutNationalTrialsParser._SKIP_PATTERNS_COMPILED = [
                re.compile(p, re.IGNORECASE) for p in self.SKIP_PATTERNS
            ]
        # Pre-compile club patterns for faster lookup
        self._club_pattern = "|".join(re.escape(club) for club in self.KNOWN_CLUBS)
        # Name cleaner for consistent athlete name normalization
        self.name_cleaner = NameCleaner()

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
        name_fragments: List[str] = []

        # Use pre-compiled skip patterns
        skip_res = LayoutNationalTrialsParser._SKIP_PATTERNS_COMPILED

        lines = text.splitlines()
        idx = 0
        while idx < len(lines):

            raw_line = lines[idx]
            line = self._clean_line(raw_line)

            if not line:
                idx += 1
                continue

            # ------------------------------------------------
            # SKIP METADATA
            # ------------------------------------------------

            if any(rx.search(line) for rx in skip_res):
                name_fragments = []
                idx += 1
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
                name_fragments = []
                idx += 1
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

                name_fragments = []
                idx += 1
                continue

            # ------------------------------------------------
            # NO EVENT
            # ------------------------------------------------

            if current_event is None:
                idx += 1
                continue

            # ------------------------------------------------
            # NAME FRAGMENT
            # ------------------------------------------------

            if self._is_name_fragment_line(line):
                name_fragments.append(line)
                idx += 1
                continue

            # ------------------------------------------------
            # RESULT LINE
            # ------------------------------------------------

            parsed, consumed = self._parse_result_line_with_fragments(
                line,
                name_fragments,
                lines[idx + 1 : idx + 4],
                current_event_name,
            )

            if parsed:
                current_event.results.append(parsed)
                name_fragments = []
                idx += consumed + 1
                continue

            # Limit failed rows to avoid memory bloat on large files
            if len(self.failed_rows) < 5000:
                self.failed_rows.append(line)
            name_fragments = []
            idx += 1

        if current_event and current_event.results:
            events.append(current_event)

        # remove duplicates efficiently
        seen = set()
        deduped = []

        for ev in events:
            # Use frozenset for hashability and efficiency
            key = (ev.event_name, ev.round, ev.raw_data.get("race_number"))
            if key not in seen:
                seen.add(key)
                deduped.append(ev)

        return deduped

    def _is_name_fragment_line(self, line: str) -> bool:

        if self.TIME_RE.search(line):
            return False

        if self.RESULT_LINE_RE.match(line):
            return False

        if any(rx.search(line) for rx in LayoutNationalTrialsParser._SKIP_PATTERNS_COMPILED):
            return False

        if "," in line:
            return True

        words = line.split()
        if len(words) >= 2 and all(
            re.match(r"^[A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\-]+$", w)
            for w in words
        ):
            return True

        if len(words) == 1 and re.match(r"^[A-ZÀ-ÖØ-öø-ÿ'\-]+$", words[0]):
            return True

        return False

    def _merge_name_fragments(self, fragments: List[str]) -> List[str]:

        merged: List[str] = []
        for fragment in fragments:
            if len(fragment.split()) == 1 and merged:
                merged[-1] = f"{merged[-1].rstrip()} {fragment}"
            else:
                merged.append(fragment)
        return merged

    def _expected_crew_size(self, event_name: Optional[str]) -> Optional[int]:

        if not event_name:
            return None

        lower = event_name.lower()
        if re.search(r"\b(k|c|ic)-?4\b", lower) or "four" in lower or "quad" in lower:
            return 4
        if re.search(r"\b(k|c|ic)-?2\b", lower) or "double" in lower:
            return 2
        if re.search(r"\b(k|c|ic)-?1\b", lower) or "single" in lower:
            return 1
        return None

    def _parse_result_line_with_fragments(
        self,
        line: str,
        preceding_fragments: List[str],
        following_lines: List[str],
        event_name: Optional[str],
    ) -> tuple[Optional[Result], int]:

        parsed = self._parse_result_line(line)
        expected_size = self._expected_crew_size(event_name)

        if parsed and expected_size and len(parsed.athletes) < expected_size:
            preceding = self._merge_name_fragments(preceding_fragments)
            if preceding:
                candidate = " ".join(preceding + [line])
                candidate_parsed = self._parse_result_line(candidate)
                if candidate_parsed and len(candidate_parsed.athletes) >= len(parsed.athletes):
                    parsed = candidate_parsed

        elif not parsed:
            preceding = self._merge_name_fragments(preceding_fragments)
            if preceding:
                candidate = " ".join(preceding + [line])
                parsed = self._parse_result_line(candidate)

        consumed = 0
        if parsed and expected_size and len(parsed.athletes) < expected_size:
            candidate = " ".join(self._merge_name_fragments(preceding_fragments) + [line])
            for i, next_line in enumerate(following_lines):
                if not self._is_name_fragment_line(next_line):
                    break
                candidate = f"{candidate} {next_line}"
                next_parsed = self._parse_result_line(candidate)
                if next_parsed and len(next_parsed.athletes) >= len(parsed.athletes):
                    parsed = next_parsed
                    consumed = i + 1
                    if expected_size and len(parsed.athletes) >= expected_size:
                        break

        if not parsed:
            # Try a minimal following fragment if no preceding names were found.
            for i, next_line in enumerate(following_lines):
                if not self._is_name_fragment_line(next_line):
                    break
                candidate = f"{line} {next_line}"
                next_parsed = self._parse_result_line(candidate)
                if next_parsed:
                    return next_parsed, i + 1

        return parsed, consumed

    # ========================================================
    # RESULT PARSER
    # ========================================================

    def _parse_result_line(self, line: str) -> Optional[Result]:

        original = line

        # Use a single regex to extract and remove times efficiently
        times = self.TIME_RE.findall(line)

        if len(times) < 2:
            return None

        result_time = times[0]
        delta_time = times[1]

        # Remove both times in one pass
        line_without_times = self.TIME_RE.sub("", line, count=2).strip()
        
        line = line_without_times

        # ----------------------------------------------------
        # POSITION / STATUS
        # ----------------------------------------------------

        position = None
        status = None

        # Pre-compile status regex for efficiency
        status_re = re.compile(
            r"^(%s)\b" % self.STATUS_CODES_PATTERN,
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

        # Use optimized club search - check longer clubs first (already sorted)
        for club in self.KNOWN_CLUBS:
            if club.lower() in line.lower():
                club_found = club
                # Remove club from line
                idx = line.lower().find(club.lower())
                if idx != -1:
                    line = (line[:idx] + line[idx + len(club):]).strip()
                break

        if not club_found:
            return None

        # ----------------------------------------------------
        # ATHLETE NAMES – split into list for crew boats
        # ----------------------------------------------------

        athlete_names = self._split_crew_names(line)
        if not athlete_names:
            return None

        # Normalize athlete names (e.g. FULL CAPS -> Title Case)
        athletes = []
        for name in athlete_names:
            try:
                normalized, _, _, _ = self.name_cleaner.normalize(name)
            except Exception:
                normalized = None

            final_name = normalized if normalized else name

            # If any name part remains in ALL CAPS, title-case that part
            parts = final_name.split()
            fixed_parts = []
            for p in parts:
                if re.search(r"[A-ZÀ-ÖØ-Þ]{2,}", p):
                    fixed_parts.append(p.title())
                else:
                    fixed_parts.append(p)
            final_name = " ".join(fixed_parts)

            athletes.append(Athlete(final_name))

        return Result(
            position=position,
            lane=lane,
            athletes=athletes,           # now a list
            club=club_found,
            time=result_time,
            delta=delta_time,
            raw_data={
                "line": original,
                "status": status,
            },
        )

    # ========================================================
    # CREW NAME SPLITTER
    # ========================================================

    def _split_crew_names(self, text: str) -> List[str]:
        """Split a string containing one or more athlete names."""
        # Normalize common separators in one pass
        # First normalize whitespace around separators
        text = re.sub(r'\s*/\s*', '/', text)  # normalize slashes
        text = re.sub(r'\s*,\s*', ',', text)   # normalize commas

        # Try slashes first (most common for crew boats)
        if "/" in text:
            parts = text.split("/")
        elif "," in text:
            parts = text.split(",")
        else:
            parts = [text]

        # Clean and filter in one pass
        cleaned = []
        for part in parts:
            part = re.sub(r'\s+', ' ', part.strip()).strip(' ,')
            if part:
                cleaned.append(part)

        return cleaned if cleaned else []

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

        # Extract heat/final number if present
        # Patterns: "Heat 1", "Heat 2", "Final A", "Final B", "Semi-final", "C-Final", etc.
        
        if "c-final" in lower:
            return "C-Final"

        if "b-final" in lower:
            return "B-Final"

        # Handle "Final A", "Final B", "Final", etc.
        if "final" in lower:
            # Try to extract letter or number after "Final"
            match = re.search(r"final\s+([a-z0-9])", lower)
            if match:
                return f"Final {match.group(1).upper()}"
            return "Final"

        # Handle "Heat 1", "Heat 2", etc.
        if "heat" in lower:
            # Try to extract number after "Heat"
            match = re.search(r"heat\s+(\d+)", lower)
            if match:
                return f"Heat {match.group(1)}"
            return "Heat"

        if "semi" in lower:
            return "Semi-final"

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

def parse_pdf(pdf_path: str, pages_per_chunk: int = 2) -> ParseResult:
    """
    Parse a PDF by extracting and parsing small chunks of pages to limit
    memory usage. `pages_per_chunk` controls how many pages are processed
    in each parsing pass (1 or 2 recommended).
    This function is robust: on error it returns a ParseResult with warnings
    instead of raising, so callers (e.g. the GUI) won't crash the process.
    """

    parser = LayoutNationalTrialsParser()
    result = ParseResult(source_file=pdf_path, layout_type=parser.layout_type)

    try:
        import pdfplumber
    except ImportError:
        parser._add_warning("pdfplumber not installed: pip install pdfplumber")
        result.parsing_warnings = parser.warnings
        return result

    result_row_re = re.compile(
        r"^\s*(?:\d+|DNF|DNS|DSQ|DQ|SCR|EXC|AB)\s+\d+\s+.+\d{1,2}:\d{2}\.\d{3}",
        re.IGNORECASE,
    )

    started_results = False

    try:
        with pdfplumber.open(pdf_path) as pdf:

            total_pages = len(pdf.pages)

            i = 0
            while i < total_pages:

                chunk_texts: List[str] = []

                for j in range(i, min(i + pages_per_chunk, total_pages)):
                    page = pdf.pages[j]
                    text = (page.extract_text() or "").strip()
                    if not text:
                        continue

                    lines = text.splitlines()

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

                    chunk_texts.append(text)

                i += pages_per_chunk

                if not chunk_texts:
                    continue

                chunk = "\n".join(chunk_texts)

                try:
                    events = parser._parse_text(chunk)
                    if events:
                        result.events.extend(events)
                except Exception as e:
                    logger.exception("Chunk parse failed")
                    parser._add_warning(f"Chunk parsing failed: {e}")

    except Exception as e:
        logger.exception("PDF open/iterate failed")
        parser._add_warning(f"PDF processing failed: {e}")
        result.parsing_warnings = parser.warnings
        result.failed_rows = parser.failed_rows
        return result

    # Attach warnings and failed rows from the parser (they were collected incrementally)
    result.parsing_warnings = parser.warnings
    result.failed_rows = parser.failed_rows

    # Deduplicate events across chunks
    seen = set()
    deduped = []
    for ev in result.events:
        key = (ev.event_name, ev.round, ev.raw_data.get("race_number"))
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    result.events = deduped

    return result


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

            # Display all athletes, joined by " / "
            athlete_display = " / ".join(a.raw_name for a in r.athletes)

            print(
                f"{pos_txt:>3} | "
                f"Lane {r.lane:<2} | "
                f"{athlete_display:<45} | "
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