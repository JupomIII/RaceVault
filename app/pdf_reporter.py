"""PDF report generation for race results."""
from __future__ import annotations
import logging
import os
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List

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
            textColor=colors.HexColor("#1f4788"),
            spaceAfter=12,
            alignment=1,
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#2e5c8a"),
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
                story.append(self._create_results_table(results_list))
                story.append(Spacer(1, 0.2 * inch))

        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("Summary Statistics", heading_style))
        summary_table = self._create_summary_table(search_results, event_grouped)
        story.append(summary_table)

        if include_charts and len(event_grouped) > 0:
            story.append(PageBreak())
            story.append(Paragraph("Charts & Visualizations", heading_style))
            story.append(Spacer(1, 0.2 * inch))

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
            data.append([str(i), athlete_name, club, time])

        table = Table(data, colWidths=[0.8 * inch, 2.2 * inch, 1.5 * inch, 1.2 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e5c8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

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

        if len(event_grouped) > 0:
            events = list(event_grouped.keys())[:5]
            event_counts = [len(event_grouped[e]) for e in events]

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(range(len(events)), event_counts, color="#2e5c8a")
            ax.set_xlabel("Event")
            ax.set_ylabel("Number of Results")
            ax.set_title("Results per Event")
            ax.set_xticks(range(len(events)))
            ax.set_xticklabels([e[:15] + "..." if len(e) > 15 else e for e in events], rotation=45, ha="right")
            fig.tight_layout()

            chart_path = os.path.join(self.output_path, f"chart_{datetime.now().timestamp()}.png")
            fig.savefig(chart_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            chart_paths.append(chart_path)

        if any(r.get("time") for r in sum(event_grouped.values(), [])):
            try:
                times_by_event = {}
                for event_name, results in event_grouped.items():
                    times = []
                    for r in results:
                        time_str = r.get("time", "")
                        if time_str:
                            times.append(time_str)
                    if times:
                        times_by_event[event_name[:20]] = len(times)

                if times_by_event:
                    fig, ax = plt.subplots(figsize=(8, 4))
                    ax.barh(list(times_by_event.keys()), list(times_by_event.values()), color="#5a8cc2")
                    ax.set_xlabel("Count")
                    ax.set_title("Finishers by Event")
                    fig.tight_layout()

                    chart_path = os.path.join(self.output_path, f"chart_times_{datetime.now().timestamp()}.png")
                    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
                    plt.close(fig)
                    chart_paths.append(chart_path)
            except Exception as e:
                logger.warning(f"Failed to generate time chart: {e}")

        return chart_paths
