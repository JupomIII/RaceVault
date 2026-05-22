from __future__ import annotations
from typing import Dict, Any, List, Optional
import pandas as pd
import re
import logging

from .base_parser import BaseParser
from ..schema import Event, Result, Athlete, ParseResult

logger = logging.getLogger(__name__)


class LayoutCParser(BaseParser):
    """
    Parser spécialisé pour les résultats sprint CKQ/CQ.

    Compatible avec :
    - PDFs résultats provinciaux
    - K1 / K2 / K4
    - C1 / C2 / C4
    - Élim. / Finale / Semi
    - DNF / DQ / SCR / EXC / AB

    Remplacement direct du LayoutCParser existant.
    """

    KNOWN_CLUBS = [
        "Lac-Beauport",
        "Lac-Sergent",
        "Trois Rivieres",
        "Trois-Rivieres",
        "Trois-Rivières",
        "Pointe-Claire",
        "Shawinigan",
        "Otterburn",
        "Sherbrooke",
        "Lachine",
        "Onake",
        "Drummondville",
        "Cascades",
        "Cartierville",
    ]

    STATUS_CODES = ["DNF", "DQ", "SCR", "EXC", "AB"]

    def __init__(self):
        super().__init__("layout_c")

    # ============================================================
    # MAIN PARSE
    # ============================================================

    def parse(
        self,
        extracted_data: Dict[str, Any],
        layout_info: Dict[str, Any],
    ) -> ParseResult:

        result = ParseResult(
            source_file=extracted_data["metadata"]["file"],
            layout_type=self.layout_type,
        )

        tables = extracted_data.get("tables", [])
        table_idx = layout_info.get("table_index")

        parsed_events: List[Event] = []

        # ========================================================
        # PRIORITÉ TABLES
        # ========================================================

        if (
            table_idx is not None
            and 0 <= table_idx < len(tables)
        ):

            try:
                df = tables[table_idx]["dataframe"]

                if df is not None and not df.empty:
                    parsed_events = self._parse_dataframe(df)

            except Exception as e:
                logger.exception("Table parsing failed")
                self._add_warning(f"Table parsing failed: {str(e)}")

        # ========================================================
        # FALLBACK TEXT
        # ========================================================

        if not parsed_events:

            try:
                parsed_events = self._parse_text(
                    extracted_data.get("text", "")
                )

            except Exception as e:
                logger.exception("Text parsing failed")
                self._add_warning(f"Text parsing failed: {str(e)}")

        result.events = parsed_events
        result.parsing_warnings = self.warnings
        result.failed_rows = self.failed_rows

        return result

    # ============================================================
    # DATAFRAME PARSER
    # ============================================================

    def _parse_dataframe(self, df: pd.DataFrame) -> List[Event]:

        events: List[Event] = []

        # Convertit tout le dataframe en texte brut
        text_lines = []

        for _, row in df.iterrows():

            row_values = []

            for val in row.tolist():

                if pd.notna(val):

                    clean = str(val).strip()

                    if clean:
                        row_values.append(clean)

            if row_values:
                text_lines.append(" ".join(row_values))

        text = "\n".join(text_lines)

        return self._parse_text(text)

    # ============================================================
    # TEXT PARSER
    # ============================================================

    def _parse_text(self, text: str) -> List[Event]:

        events: List[Event] = []

        current_event: Optional[Event] = None

        lines = text.splitlines()

        course_pattern = re.compile(
            r"^Course\s+#(?P<number>\d+)\s+(?P<name>.+?)\s+\((?P<datetime>[\d\-: ]+)\)$",
            re.IGNORECASE,
        )

        for raw_line in lines:

            line = raw_line.strip()

            if not line:
                continue

            # ====================================================
            # IGNORE HEADERS / FOOTERS
            # ====================================================

            if any(
                x in line
                for x in [
                    "Jour n°",
                    "Championnats",
                    "Club de Canoë",
                    "<PARSED TEXT",
                    "M14, M12 et M10",
                ]
            ):
                continue

            # ====================================================
            # EVENT HEADER
            # ====================================================

            course_match = course_pattern.match(line)

            if course_match:

                if current_event and current_event.results:
                    events.append(current_event)

                event_name = course_match.group("name").strip()

                current_event = Event(
                    event_name=event_name
                )

                current_event.raw_data = {
                    "course_number": course_match.group("number"),
                    "datetime": course_match.group("datetime"),
                }

                lower = event_name.lower()

                if "finale" in lower or "final" in lower:
                    current_event.round = "Final"

                elif "semi" in lower:
                    current_event.round = "Semi-final"

                elif "élim" in lower or "heat" in lower:
                    current_event.round = "Heat"

                else:
                    current_event.round = "Unknown"

                continue

            # ====================================================
            # NO EVENT YET
            # ====================================================

            if current_event is None:
                continue

            # ====================================================
            # RESULT LINE
            # ====================================================

            parsed_result = self._parse_result_line(line)

            if parsed_result:
                current_event.results.append(parsed_result)

        if current_event and current_event.results:
            events.append(current_event)

        if not events:
            self._add_warning("No events extracted")

        return events

    # ============================================================
    # RESULT PARSER
    # ============================================================

    def _parse_result_line(self, line: str) -> Optional[Result]:

        """
        Exemple :

        5 Lac-Beauport Emma Lussier/Cassandre Bellavance 1 02:19.18
        """

        original_line = line

        # ========================================================
        # LANE
        # ========================================================

        lane = None

        lane_match = re.match(r"^(\d+)\s+", line)

        if lane_match:
            lane = int(lane_match.group(1))

        # ========================================================
        # STATUS
        # ========================================================

        status = None

        for s in self.STATUS_CODES:

            if re.search(rf"\b{s}\b", line):

                status = s
                break

        # ========================================================
        # TIME
        # ========================================================

        time_match = re.search(
            r"(\d{2}:\d{2}\.\d{2})",
            line
        )

        result_time = None

        if time_match:
            result_time = time_match.group(1)

        # ========================================================
        # POSITION
        # ========================================================

        position = None

        pos_match = re.search(
            r"\s(\d{1,2})\s+\d{2}:\d{2}\.\d{2}$",
            line
        )

        if pos_match:
            position = int(pos_match.group(1))

        # ========================================================
        # CLUB
        # ========================================================

        club_found = None

        for club in sorted(self.KNOWN_CLUBS, key=len, reverse=True):

            if club.lower() in line.lower():

                club_found = club

                line = re.sub(
                    re.escape(club),
                    "",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                )

                break

        if not club_found:
            return None

        # ========================================================
        # CLEANUP
        # ========================================================

        line = re.sub(r"^\d+\s+", "", line)

        if result_time:
            line = line.replace(result_time, "")

        if position is not None:
            line = re.sub(
                rf"\b{position}\b",
                "",
                line
            )

        if status:
            line = line.replace(status, "")

        athlete_name = re.sub(
            r"\s+",
            " ",
            line
        ).strip()

        athlete_name = athlete_name.replace("Æ", "'")

        # ========================================================
        # VALIDATION
        # ========================================================

        if not athlete_name:
            return None

        # ========================================================
        # RESULT
        # ========================================================

        return Result(
            position=position,
            lane=lane,
            athlete=Athlete(
                raw_name=athlete_name
            ),
            club=club_found,
            time=result_time,
            raw_data={
                "line": original_line,
                "status": status,
            },
        )