"""PDF report generation for race results."""
from __future__ import annotations
import logging
import os
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    Image,
)
from reportlab.platypus.flowables import KeepTogether
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

logger = logging.getLogger(__name__)


class PDFReporter:
    def __init__(self, output_path: str = "output"):
        self.output_path = output_path
        os.makedirs(output_path, exist_ok=True)

        # Palette
        self.PRIMARY = colors.HexColor("#1A365D")
        self.SECONDARY = colors.HexColor("#3182CE")
        self.GOLD = colors.HexColor("#D4AF37")
        self.ROW_ALT = colors.HexColor("#F7FAFC")

    def generate_report(
        self,
        search_results: List[Dict[str, Any]],
        title: str = "RaceVault Results Report",
        include_charts: bool = True,
    ) -> str:
        """
        Generate a professional PDF report from search results.

        Args:
            search_results: List of filtered search result dictionaries
            title: Report title
            include_charts: Whether to include charts/graphs

        Returns:
            Path to generated PDF file
        """
        if not search_results:
            raise ValueError("No results to report on")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.pdf"
        filepath = os.path.join(self.output_path, filename)

        doc = SimpleDocTemplate(filepath, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
        story = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=self.PRIMARY,
            spaceAfter=12,
            alignment=1,
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=self.PRIMARY,
            spaceAfter=8,
            spaceBefore=8,
        )

        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.3 * inch))

        event_grouped = self._group_by_event(search_results)
        unique_competitions = self._extract_competitions(event_grouped)

        for comp_name, events_dict in sorted(unique_competitions.items()):
            story.append(Paragraph(f"Competition: {comp_name or 'Unknown'}", heading_style))
            story.append(Spacer(1, 0.15 * inch))

            for event_name, results_list in sorted(events_dict.items()):
                story.append(Paragraph(f"Event: {event_name or 'Unknown'}", styles["Heading3"]))

                # If small result sets (1-2 lines) render compact side-by-side cards
                if len(results_list) > 0 and len(results_list) <= 2:
                    story.append(self._create_side_by_side_cards(results_list, styles))
                else:
                    story.append(KeepTogether([self._create_results_table(results_list)]))

                story.append(Spacer(1, 0.2 * inch))

        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("Summary Statistics", heading_style))
        story.append(self._create_kpi_row(search_results, event_grouped, styles))

        if include_charts and len(event_grouped) > 0:
            story.append(PageBreak())
            story.append(Paragraph("Charts & Visualizations", heading_style))
            story.append(Spacer(1, 0.2 * inch))
            # Generate performance progression charts
            chart_images = self._generate_charts(event_grouped)
            for img_path in chart_images:
                if os.path.exists(img_path):
                    try:
                        img = Image(img_path, width=6.5 * inch, height=3 * inch)
                        story.append(img)
                        story.append(Spacer(1, 0.3 * inch))
                    except Exception as e:
                        logger.warning(f"Failed to add chart image: {e}")

        story.append(Spacer(1, 0.2 * inch))
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        footer = Paragraph(f"<i>Generated on {generated_at}</i>", styles["Normal"])
        story.append(footer)

        doc.build(story)
        logger.info(f"PDF report generated: {filepath}")
        return filepath

    def _group_by_event(self, results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group results by event_name."""
        grouped = defaultdict(list)
        for result in results:
            event_name = result.get("event_name", "Unknown")
            grouped[event_name].append(result)
        return dict(grouped)

    def _extract_competitions(
        self, event_grouped: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Extract unique competitions from events and organize results."""
        competitions = defaultdict(lambda: defaultdict(list))
        for event_name, results_list in event_grouped.items():
            for result in results_list:
                source_file = result.get("source_file", "Unknown")
                competitions[source_file][event_name].extend([result])
        return dict(competitions)

    def _create_results_table(self, results: List[Dict[str, Any]]) -> Table:
        """Create a formatted table for event results."""
        data = [["Position", "Athlete", "Club", "Time"]]
        for i, result in enumerate(results, 1):
            athlete_name = result.get("athlete_name", "N/A")
            club = result.get("club", "N/A")
            time = result.get("time", "N/A")

            # Header-value alignment check: if athlete_name actually looks like a time,
            # shift it into the time column and try to recover the athlete/club
            try:
                ath_secs = self._parse_time_to_seconds(str(athlete_name))
            except Exception:
                ath_secs = None

            if ath_secs is not None and (time is None or self._parse_time_to_seconds(str(time)) is None):
                # move athlete column into time, and attempt to fill athlete from club
                time = athlete_name
                athlete_name = club or "N/A"
                club = ""

            data.append([str(i), athlete_name, club, time])

        table = Table(data, colWidths=[0.7 * inch, 2.4 * inch, 1.6 * inch, 1.1 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.PRIMARY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, self.PRIMARY),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, self.ROW_ALT]),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _create_side_by_side_cards(self, results: List[Dict[str, Any]], styles) -> Table:
        """Create a 2-column layout of compact race cards for small result sets."""
        cards = []
        for r in results:
            header = Paragraph(r.get("athlete_name", "N/A"), styles["Heading4"]) if r.get("athlete_name") else Paragraph("Athlete", styles["Normal"]) 
            table = self._create_results_table([r])
            cards.append(KeepTogether([header, Spacer(1, 4), table]))

        # Ensure two columns
        if len(cards) == 1:
            cards.append(Paragraph("", styles["Normal"]))

        grid = Table([[cards[0], cards[1]]], colWidths=[3.25 * inch, 3.25 * inch])
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return grid

    def _create_kpi_row(self, results: List[Dict[str, Any]], event_grouped: Dict[str, List[Dict[str, Any]]], styles) -> Table:
        total_results = len(results)
        unique_athletes = len(set((r.get("athlete_name"), r.get("normalized_name")) for r in results))
        unique_events = len(event_grouped)
        total_sources = len(set(r.get("source_file") for r in results))

        kpis = [
            ("Total Events", str(unique_events)),
            ("Total Results", str(total_results)),
            ("Unique Athletes", str(unique_athletes)),
            ("Source Files", str(total_sources)),
        ]

        row = []
        for title, val in kpis:
            cell = [[Paragraph(f"<b>{val}</b>", styles["Heading3"])], [Paragraph(title, styles["Normal"])]]
            t = Table(cell, colWidths=[1.5 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.5, self.SECONDARY),
            ]))
            row.append(t)

        grid = Table([row], colWidths=[1.5 * inch] * len(row))
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return grid

    def _create_summary_table(
        self, results: List[Dict[str, Any]], event_grouped: Dict[str, List[Dict[str, Any]]]
    ) -> Table:
        """Create a summary statistics table."""
        total_results = len(results)
        unique_athletes = len(set((r.get("athlete_name"), r.get("normalized_name")) for r in results))
        unique_events = len(event_grouped)
        unique_sources = len(set(r.get("source_file") for r in results))

        data = [
            ["Metric", "Count"],
            ["Total Events", str(unique_events)],
            ["Total Results", str(total_results)],
            ["Unique Athletes", str(unique_athletes)],
            ["Source Files", str(unique_sources)],
        ]

        table = Table(data, colWidths=[3 * inch, 1.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e5c8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("FONTSIZE", (0, 1), (-1, -1), 11),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _generate_charts(self, event_grouped: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """Generate matplotlib charts for visualization."""
        chart_paths = []
        # Build performance progression plots by grouping identical distance/boat categories
        try:
            # Collect times per (event_category, athlete)
            data = {}
            for event_name, results in event_grouped.items():
                for r in results:
                    time_str = r.get("time")
                    athlete = r.get("athlete_name") or r.get("athlete") or "Unknown"
                    src = r.get("source_file") or r.get("file") or "Unknown"
                    if not time_str:
                        continue
                    secs = self._parse_time_to_seconds(time_str)
                    if secs is None:
                        continue
                    key = event_name
                    data.setdefault(key, {}).setdefault(athlete, []).append((src, secs))

            # For each event category, make a progression plot
            for ev, athletes in list(data.items())[:6]:
                fig, ax = plt.subplots(figsize=(8, 3.5))
                for athlete, entries in athletes.items():
                    # sort by source filename to give chronological order if dates unavailable
                    entries_sorted = sorted(entries, key=lambda x: x[0])
                    xs = [e[0] for e in entries_sorted]
                    ys = [e[1] for e in entries_sorted]
                    if len(xs) < 2:
                        continue
                    ax.plot(range(len(xs)), ys, marker="o", label=athlete)

                if not ax.lines:
                    plt.close(fig)
                    continue

                ax.set_title(f"Performance Progression — {ev}")
                ax.set_ylabel("Time (seconds)")
                ax.set_xticks(range(max(1, max(len(v) for v in athletes.values()))))
                # use athlete-specific labels: use first athlete's x labels as representative
                sample = next(iter(athletes.values()))
                tick_labels = [s[0] for s in sorted(sample, key=lambda x: x[0])]
                ax.set_xticklabels([t[:20] + "..." if len(t) > 20 else t for t in tick_labels], rotation=45, ha="right")
                ax.grid(True, linestyle="--", alpha=0.4)
                ax.legend(fontsize=8)
                fig.tight_layout()

                chart_path = os.path.join(self.output_path, f"progress_{datetime.now().timestamp()}.png")
                fig.savefig(chart_path, dpi=150, bbox_inches="tight")
                plt.close(fig)
                chart_paths.append(chart_path)
        except Exception as e:
            logger.warning(f"Failed to generate progression charts: {e}")

        return chart_paths

    def _parse_time_to_seconds(self, time_str: str) -> Optional[float]:
        """Convert time strings like '04:16.37' or '0416.37' to seconds."""
        if not time_str or not isinstance(time_str, str):
            return None

        # Remove stray trailing punctuation
        s = time_str.strip().strip(":;")

        # Ensure colon between minutes and seconds
        s = re.sub(r"\b(\d{2})(\d{2}\.\d{1,3})\b", r"\1:\2", s)

        m = re.match(r"^(?:(\d+):)?(\d{1,2})\.(\d{1,3})$", s)
        if not m:
            # fallback: try mm:ss
            m2 = re.match(r"^(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?$", s)
            if not m2:
                return None
            minutes = int(m2.group(1))
            seconds = int(m2.group(2))
            frac = float("0." + (m2.group(3) or "0"))
            return minutes * 60 + seconds + frac

        minutes = int(m.group(1)) if m.group(1) else 0
        seconds = int(m.group(2))
        frac = float("0." + (m.group(3) or "0"))
        return minutes * 60 + seconds + frac
