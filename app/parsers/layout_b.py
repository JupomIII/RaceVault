from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)


# ================================================================
# LIGHTWEIGHT SCHEMA  (mirrors your existing schema module)
# ================================================================

class Athlete:
    def __init__(self, raw_name: str):
        self.raw_name = raw_name

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
        self.event_name = event_name
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


# ================================================================
# BASE PARSER
# ================================================================

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


# ================================================================
# LAYOUT – NATIONAL TRIALS PARSER
# ================================================================

class LayoutNationalTrialsParser(BaseParser):
    """
    Parser pour les résultats des Championnats nationaux (format HTML/PDF).

    Compatible avec :
    - PDFs / HTMLs résultats nationaux (ex : National Team Trials)
    - K1 / K2 / C1 / C2 — toutes distances
    - Finales / B-Finales / C-Finales
    - DNF / DSQ / DNS / SCR / EXC / AB

    Structure attendue (par page / bloc de texte) :
        Hommes SENIOR Men C-2 500M          ← nom d'épreuve
        8:30 AM - Race #188 - Final         ← infos course
        Place Ln/co  Crew  Club  Time Delta ← en-tête (ignoré)
        1  5  Andrew BILLARD, Alix PLOMTEUX  Maskwa  1:43.288  0:00.000
        DNF  5  Madeleine BEAUREGARD, ...   Carleton Place  0:00.000  0:00.000
    """

    # Clubs connus – triés du plus long au plus court pour éviter
    # les faux-positifs lors du matching.
    KNOWN_CLUBS = [
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
    ]

    STATUS_CODES = ["DNF", "DSQ", "DNS", "SCR", "EXC", "DQ", "AB"]

    # En-têtes de colonnes et lignes de métadonnées à ignorer
    SKIP_PATTERNS = [
        r"^Place\s+Ln",
        r"^Regatta Results",
        r"^file://",
        r"^\d+\s+of\s+\d+",
        r"^\d{4}-\d{2}-\d{2}",          # date imprimée
        r"^2025 National Team Trials",
        r"^-\s*6/\d{2}/\d{4}",
        r"Crew\s*/\s*équipage",
        r"Time/temps",
    ]

    def __init__(self):
        super().__init__("layout_national_trials")

    # ============================================================
    # MAIN PARSE
    # ============================================================

    def parse(
        self,
        extracted_data: Dict[str, Any],
        layout_info: Dict[str, Any],
    ) -> ParseResult:

        result = ParseResult(
            source_file=extracted_data.get("metadata", {}).get("file", "unknown"),
            layout_type=self.layout_type,
        )

        tables = extracted_data.get("tables", [])
        table_idx = layout_info.get("table_index")
        parsed_events: List[Event] = []

        # --------------------------------------------------------
        # PRIORITÉ : tables (si disponibles)
        # --------------------------------------------------------
        if table_idx is not None and 0 <= table_idx < len(tables):
            try:
                df = tables[table_idx]["dataframe"]
                if df is not None and not df.empty:
                    parsed_events = self._parse_dataframe(df)
            except Exception as e:
                logger.exception("Table parsing failed")
                self._add_warning(f"Table parsing failed: {str(e)}")

        # --------------------------------------------------------
        # FALLBACK : texte brut (chemin principal pour ce PDF)
        # --------------------------------------------------------
        if not parsed_events:
            try:
                raw_text = extracted_data.get("text", "")
                parsed_events = self._parse_text(raw_text)
            except Exception as e:
                logger.exception("Text parsing failed")
                self._add_warning(f"Text parsing failed: {str(e)}")

        result.events = parsed_events
        result.parsing_warnings = self.warnings
        result.failed_rows = self.failed_rows
        return result

    # ============================================================
    # DATAFRAME → TEXTE  (même stratégie que LayoutCParser)
    # ============================================================

    def _parse_dataframe(self, df: pd.DataFrame) -> List[Event]:
        text_lines: List[str] = []

        for _, row in df.iterrows():
            row_values = [
                str(v).strip()
                for v in row.tolist()
                if pd.notna(v) and str(v).strip()
            ]
            if row_values:
                text_lines.append(" ".join(row_values))

        return self._parse_text("\n".join(text_lines))

    # ============================================================
    # TEXT PARSER  — machine à états
    # ============================================================

    # Nom d'épreuve : ligne contenant un bateau (K/C ± tiret, chiffre)
    # et une distance (ex: 500M, 1000m, 5000m, 200m)
    _EVENT_NAME_RE = re.compile(
        r"\b(C-?[124]|K-?[124])\b.+\b(\d{3,5}\s*[mM])\b",
        re.IGNORECASE,
    )

    # Infos de course : "8:30 AM - Race #188 - Final"
    # NOTE: 'round' est un builtin Python — certaines versions de re le rejettent
    #       comme nom de groupe nommé → on utilise 'round_label'.
    _RACE_INFO_RE = re.compile(
        r"(?P<time>\d{1,2}:\d{2}\s*[AP]M)"
        r"\s*-\s*Race\s*#(?P<number>\d+)"
        r"\s*-\s*(?P<round_label>.+)",
        re.IGNORECASE,
    )

    # Temps de course : 1:43.288  ou  25:01.903  ou  0:47.970
    _TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}\.\d{3})\b")

    def _parse_text(self, text: str) -> List[Event]:
        events: List[Event] = []
        current_event: Optional[Event] = None
        pending_event_name: Optional[str] = None   # nom sans infos de course

        skip_re = [re.compile(p, re.IGNORECASE) for p in self.SKIP_PATTERNS]

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # ------------------------------------------------
            # Lignes à ignorer (en-têtes, pieds de page…)
            # ------------------------------------------------
            if any(rx.search(line) for rx in skip_re):
                continue

            # ------------------------------------------------
            # Nom d'épreuve ?
            # ------------------------------------------------
            if self._EVENT_NAME_RE.search(line):
                # Sauvegarde l'événement en cours s'il a des résultats
                if current_event and current_event.results:
                    events.append(current_event)

                pending_event_name = line
                current_event = Event(event_name=line)
                continue

            # ------------------------------------------------
            # Infos de course (Race # + round) ?
            # ------------------------------------------------
            race_match = self._RACE_INFO_RE.match(line)
            if race_match and current_event is not None:
                round_label = race_match.group("round_label").strip()
                current_event.round = self._normalise_round(round_label)
                current_event.raw_data.update({
                    "race_number": race_match.group("number"),
                    "race_time":   race_match.group("time"),
                    "round_raw":   round_label,
                })
                # Si plusieurs races pour la même épreuve (B-Final, C-Final…),
                # on crée un nouvel événement distinct.
                if current_event.results:
                    events.append(current_event)
                    current_event = Event(
                        event_name=pending_event_name or current_event.event_name
                    )
                    current_event.round = self._normalise_round(round_label)
                    current_event.raw_data = {
                        "race_number": race_match.group("number"),
                        "race_time":   race_match.group("time"),
                        "round_raw":   round_label,
                    }
                continue

            # ------------------------------------------------
            # Pas encore d'événement ouvert
            # ------------------------------------------------
            if current_event is None:
                continue

            # ------------------------------------------------
            # Ligne de résultat
            # ------------------------------------------------
            parsed = self._parse_result_line(line)
            if parsed:
                current_event.results.append(parsed)
            else:
                # Conserver les lignes non reconnues pour débogage
                self.failed_rows.append(line)

        # Dernier événement
        if current_event and current_event.results:
            events.append(current_event)

        if not events:
            self._add_warning("No events extracted from text")

        return events

    # ============================================================
    # PARSER D'UNE LIGNE DE RÉSULTAT
    # ============================================================

    def _parse_result_line(self, line: str) -> Optional[Result]:
        """
        Formes attendues :
            1  5  Andrew BILLARD, Alix PLOMTEUX  Maskwa  1:43.288  0:00.000
            DNF  5  Madeleine BEAUREGARD, Isabel LOWRY  Carleton Place  0:00.000  0:00.000
            SCR  8  Luke ENNS  Toba  0:00.000  0:00.000
        """
        original = line

        # --------------------------------------------------------
        # TEMPS & DELTA  — deux durées en fin de ligne
        # --------------------------------------------------------
        times = self._TIME_RE.findall(line)
        if len(times) < 2:
            return None                 # pas une ligne de résultat

        result_time = times[0]
        delta_time  = times[1]

        # Supprimer temps + delta du texte pour faciliter le reste
        line = self._TIME_RE.sub("", line, count=2).strip()

        # --------------------------------------------------------
        # STATUT  (DNF, DNS, SCR, DSQ…) ou POSITION numérique
        # --------------------------------------------------------
        status: Optional[str] = None
        position: Optional[int] = None

        status_match = re.match(
            r"^(?P<status>" + "|".join(self.STATUS_CODES) + r")\b",
            line,
            re.IGNORECASE,
        )
        if status_match:
            status = status_match.group("status").upper()
            line = line[status_match.end():].strip()
        else:
            pos_match = re.match(r"^(\d{1,3})\s+", line)
            if pos_match:
                position = int(pos_match.group(1))
                line = line[pos_match.end():].strip()
            else:
                return None             # ni statut ni position → non reconnu

        # --------------------------------------------------------
        # COULOIR  (premier token numérique restant)
        # --------------------------------------------------------
        lane: Optional[int] = None
        lane_match = re.match(r"^(\d{1,2})\s+", line)
        if lane_match:
            lane = int(lane_match.group(1))
            line = line[lane_match.end():].strip()

        # --------------------------------------------------------
        # CLUB  — matching du plus long au plus court
        # --------------------------------------------------------
        club_found: Optional[str] = None
        for club in sorted(self.KNOWN_CLUBS, key=len, reverse=True):
            if re.search(re.escape(club), line, re.IGNORECASE):
                club_found = club
                line = re.sub(
                    re.escape(club), "", line, count=1, flags=re.IGNORECASE
                ).strip()
                break

        if not club_found:
            return None                 # club introuvable

        # --------------------------------------------------------
        # NOM(S) D'ATHLÈTE  — ce qui reste
        # --------------------------------------------------------
        athlete_name = re.sub(r"\s+", " ", line).strip()
        # Nettoyage des virgules/espaces résiduels
        athlete_name = re.sub(r"^[\s,]+|[\s,]+$", "", athlete_name)

        if not athlete_name:
            return None

        return Result(
            position=position,
            lane=lane,
            athlete=Athlete(raw_name=athlete_name),
            club=club_found,
            time=result_time,
            delta=delta_time,
            raw_data={
                "line":   original,
                "status": status,
            },
        )

    # ============================================================
    # UTILITAIRES
    # ============================================================

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
        if "heat" in lower or "élim" in lower:
            return "Heat"
        return label.strip()


# Alias pour la compatibilité avec app/parsers/__init__.py
# qui fait : from .layout_b import LayoutBParser
LayoutBParser = LayoutNationalTrialsParser


# ================================================================
# ENTRÉE AUTONOME — teste le parser directement sur le PDF fourni
# ================================================================

def _extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extraction minimale via pdfplumber.
    Ignore la première page (programme / horaire).
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pip install pdfplumber")

    pages_text: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i == 0:          # ← exclut la première page
                continue
            text = page.extract_text() or ""
            pages_text.append(text)

    return "\n".join(pages_text)


def parse_pdf(pdf_path: str) -> ParseResult:
    """Point d'entrée public — extrait + parse le PDF."""
    raw_text = _extract_text_from_pdf(pdf_path)

    extracted_data: Dict[str, Any] = {
        "metadata": {"file": pdf_path},
        "text":     raw_text,
        "tables":   [],
    }
    layout_info: Dict[str, Any] = {}

    parser = LayoutNationalTrialsParser()
    return parser.parse(extracted_data, layout_info)


# ================================================================
# DÉMO  (python layout_national_parser.py <chemin_pdf>)
# ================================================================

if __name__ == "__main__":
    import sys
    import json

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "Day-3-Results.pdf"

    result = parse_pdf(pdf_path)

    print(f"\n{'='*60}")
    print(f"  Fichier : {result.source_file}")
    print(f"  Épreuves trouvées : {len(result.events)}")
    print(f"{'='*60}\n")

    for ev in result.events:
        print(f"  [{ev.round}]  {ev.event_name}")
        if ev.raw_data.get("race_number"):
            print(f"    Race #{ev.raw_data['race_number']}  "
                  f"({ev.raw_data.get('race_time', '')})")
        for r in ev.results:
            status_tag = f" [{r.raw_data.get('status')}]" if r.raw_data.get("status") else ""
            pos_tag = r.position if r.position is not None else "—"
            print(
                f"    {pos_tag:>3}  ln={r.lane}  "
                f"{r.athlete.raw_name:<45}  "
                f"{r.club:<18}  {r.time}{status_tag}"
            )
        print()

    if result.parsing_warnings:
        print("⚠  Avertissements :")
        for w in result.parsing_warnings:
            print(f"   • {w}")

    if result.failed_rows:
        print(f"\n↩  Lignes non reconnues ({len(result.failed_rows)}) :")
        for row in result.failed_rows[:20]:
            print(f"   | {row}")
