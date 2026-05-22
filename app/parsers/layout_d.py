from __future__ import annotations
from typing import Dict, Any, List, Optional
import re
import logging
import pandas as pd

from .base_parser import BaseParser
from ..schema import Event, Result, Athlete, ParseResult

logger = logging.getLogger(__name__)


class LayoutDParser(BaseParser):
    """
    Parser pour le layout D (Championnats provinciaux longues distances).
    Format adapté aux anomalies d'extraction OCR (lignes fusionnées, inversions).
    """

    def __init__(self):
        super().__init__("layout_d")

    def parse(self, extracted_data: Dict[str, Any], layout_info: Dict[str, Any]) -> ParseResult:
        result = ParseResult(
            source_file=extracted_data["metadata"]["file"],
            layout_type=self.layout_type,
        )

        text = extracted_data.get("text", "")
        if text:
            result.events = self._parse_text(text)
        else:
            tables = extracted_data.get("tables", [])
            for table in tables:
                df = table.get("dataframe")
                if df is not None and not df.empty:
                    result.events = self._parse_dataframe(df)
                    break

        result.parsing_warnings = self.warnings
        result.failed_rows = self.failed_rows
        return result

    def _parse_text(self, text: str) -> List[Event]:
        events: List[Event] = []
        lines = text.splitlines()
        current_event: Optional[Event] = None

        # Pattern pour détecter le début d'une catégorie (ex: M16 Homme K1 2000m)
        event_header_pattern = re.compile(
            r"^(M\d+|Senior|Sennior|Maître)\s+(Homme|Femme)\s+([KC]\d+)?\s*(\d+m)?",
            re.IGNORECASE,
        )

        # Liste des clubs connus pour faciliter le découpage sémantique dans le bruit OCR
        known_clubs = [
            "Lac-Beauport", "Trois-Rivières", "Otterburn", "Cascades", 
            "Shawinigan", "Lachine", "Sherbrooke", "Poine-Claire", 
            "Pointe-Claire", "Cartierville", "Lac-Sergent", "Onake"
        ]
        clubs_regex = "|".join([re.escape(c) for c in known_clubs])

        # Statuts spéciaux de course
        special_status_pattern = re.compile(r"(Disqualifi[ée]|Retrait|Inachev[ée])", re.IGNORECASE)

        for line in lines:
            line = line.strip().replace('"', '')  # Nettoyage des résidus de guillemets de table
            if not line or "CANOE KAYAK" in line or "Championnats" in line or "Bassin olympique" in line:
                continue

            # 1. Détection des en-têtes de catégorie
            header_match = event_header_pattern.match(line)
            if header_match and ("m" in line.lower() or "K1" in line or "C1" in line):
                if current_event and current_event.results:
                    events.append(current_event)
                
                # Normalisation des petites coquilles de l'OCR (ex: "Sennior")
                category = line.replace("Sennior", "Senior").strip()
                current_event = Event(event_name=category)
                current_event.round = "Final"
                continue

            if current_event is None:
                continue

            # 2. Détection des lignes de statut spécial (Retrait, DNF, DSQ)
            status_match = special_status_pattern.search(line)
            if status_match:
                status = status_match.group(1).capitalize()
                
                # Extraction du club si présent dans la ligne de abandon
                club_found = None
                for c in known_clubs:
                    if c.lower() in line.lower():
                        club_found = c
                        line = re.sub(re.escape(c), "", line, flags=re.IGNORECASE)
                        break
                
                # Nettoyage du reste pour obtenir le nom de l'athlète
                clean_name = special_status_pattern.sub("", line)
                clean_name = re.sub(r"\d{2}:\d{2}:\d{2}|\b\d{1,3}\b", "", clean_name).strip()
                
                if clean_name:
                    result = Result(
                        position=len(current_event.results) + 1,
                        athlete=Athlete(raw_name=clean_name),
                        club=club_found,
                        time=None,
                        raw_data={"line": line, "status": status},
                    )
                    current_event.results.append(result)
                continue

            # 3. Extraction des lignes de résultats standards (Temps + Rang)
            # Recherche un format de temps comme 8:29,3 ou 1019,2: ou 10:26.9
            time_match = re.search(r"(\d{1,2}[:.]?\d{2}[.,]\d{1,2}(?::)?)", line)
            if time_match:
                raw_time = time_match.group(1)
                # Standardisation du format de temps pour la base de données (MM:SS.d)
                clean_time = raw_time.replace(",", ".").replace(":", ".", 1) if raw_time.count(":") == 0 else raw_time.replace(",", ".")
                clean_time = clean_time.rstrip(":")

                # Extraction de la position (numéro isolé en début ou fin de bloc de données)
                pos_match = re.search(r"\b(\d{1,2})\b\s*$", line) # Souvent en fin de segment de table OCR
                if not pos_match:
                    pos_match = re.search(r"^\s*(\d{1,2})\b", line)
                
                position = int(pos_match.group(1)) if pos_match else len(current_event.results) + 1

                # Extraction du club via la liste de référence
                club_found = None
                for c in known_clubs:
                    if c.lower() in line.lower():
                        club_found = c
                        line = re.sub(re.escape(c), "", line, flags=re.IGNORECASE)
                        break

                # Nettoyage final pour isoler l'identité de l'athlète
                athlete_line = re.sub(re.escape(raw_time), "", line)
                if pos_match:
                    athlete_line = re.sub(r"\b" + re.escape(pos_match.group(1)) + r"\b", "", athlete_line)
                athlete_line = re.sub(r"\d{2}:\d{2}:\d{2}", "", athlete_line) # Retire l'heure de départ
                athlete_line = re.sub(r"\b\d{1,3}\b", "", athlete_line) # Idem pour les dossards
                
                athlete_name = athlete_line.replace(",", "").strip()

                if athlete_name and len(athlete_name) > 3:
                    result = Result(
                        position=position,
                        athlete=Athlete(raw_name=athlete_name),
                        club=club_found,
                        time=clean_time,
                        raw_data={"line": line},
                    )
                    current_event.results.append(result)
                else:
                    self._add_failed_row({"line": line}, "Échec extraction nom athlète")
            else:
                # Si la ligne contient du texte mais pas de temps (ex: nom séparé du temps sur deux lignes OCR)
                if len(line) > 5 and not any(h in line for h in ["Départ", "no.", "Athlètes", "Résultat"]):
                    self._add_failed_row({"line": line}, "Ligne orpheline ou non reconnue")

        if current_event and current_event.results:
            events.append(current_event)

        if not events:
            self._add_warning("Aucun événement extrait du texte")

        return events

    def _parse_dataframe(self, df: pd.DataFrame) -> List[Event]:
        # Logique de secours si l'extraction tabulaire native de l'ingesteur est activée
        events: List[Event] = []
        current_event = Event()

        for idx, row in df.iterrows():
            row_dict = {str(k): (str(v).strip() if pd.notna(v) else "") for k, v in row.to_dict().items()}
            row_string = " ".join(row_dict.values())

            if any(re.search(r"(M\d+|Senior|Sennior|Maître).*(K1|C1)", v, re.IGNORECASE) for v in row_dict.values()):
                if current_event.results:
                    events.append(current_event)
                event_name = next((v for v in row_dict.values() if v), "Événement inconnu")
                current_event = Event(event_name=event_name.strip().replace("Sennior", "Senior"))
                continue

            # Extraction sémantique basée sur le contenu textuel de la ligne du DataFrame
            athlete = None
            club = None
            result_time = None
            position = None
            status = None

            # Détection des statuts
            if "disqualifié" in row_string.lower():
                status = "Disqualifié"
            elif "retrait" in row_string.lower():
                status = "Retrait"
            elif "inachevé" in row_string.lower():
                status = "Inachevé"

            # Recherche du temps
            time_search = re.search(r"(\d{1,2}[:.]?\d{2}[.,]\d{1,2})", row_string)
            if time_search:
                result_time = time_search.group(1).replace(",", ".")

            # Isolement de l'athlète et du club par analyse des cellules
            for col, val_str in row_dict.items():
                if not val_str:
                    continue
                if "athlète" in col.lower() or "nom" in col.lower() or "clubs" in col.lower():
                    # Nettoyage des métadonnées numériques dans la cellule
                    clean_val = re.sub(r"\d{2}:\d{2}:\d{2}|\b\d{1,3}\b", "", val_str).strip()
                    if len(clean_val) > 3:
                        athlete = clean_val

            if athlete:
                result = Result(
                    position=position if position else idx + 1,
                    athlete=Athlete(raw_name=athlete),
                    club=club,
                    time=result_time,
                    raw_data={**row_dict, "status": status} if status else row_dict,
                )
                current_event.results.append(result)

        if current_event.results:
            events.append(current_event)

        return events