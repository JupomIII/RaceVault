"""Layout preview images and utilities for the GUI."""

from pathlib import Path
from PySide6.QtWidgets import QComboBox, QLabel
from PySide6.QtGui import QPixmap, QFont, QColor
from PySide6.QtCore import Qt, QSize


ASSETS_DIR = Path(__file__).parent / "assets" / "layout_previews"

LAYOUT_IMAGE_MAPPING = {
    "Auto-detect": "auto_detect.png",
    "layout_a": "layout_a.png",
    "layout_b": "layout_b.png",
    "layout_c": "layout_c.png",
    "layout_d": "layout_d.png",
}


class LayoutPreviewComboBox(QComboBox):
    def __init__(self, preview_widget=None):
        super().__init__()
        self.preview_widget = preview_widget
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.preview_widget:
            self.preview_widget.update_preview(self.currentText())


class LayoutPreviewPanel(QLabel):

    LAYOUT_DESCRIPTIONS = {
        "Auto-detect": {
            "title": "Automatic Detection",
            "description": "The system will automatically<br/>detect the PDF layout type",
            "color": "#e0e0e0",
            "icon": "🔍"
        },
        "layout_a": {
            "title": "Layout A",
            "description": "Standard format<br/>Basic race results",
            "color": "#bbdefb",
            "icon": "▭"
        },
        "layout_b": {
            "title": "Layout B",
            "description": "Extended format<br/>Detailed competition data",
            "color": "#c8e6c9",
            "icon": "▭▭"
        },
        "layout_c": {
            "title": "Layout C",
            "description": "Provincial format<br/>Youth competition races",
            "color": "#fff9c4",
            "icon": "C"
        },
        "layout_d": {
            "title": "Layout D",
            "description": "Distance races<br/>Optimized layout",
            "color": "#ffccbc",
            "icon": "D"
        },
    }

    def __init__(self):
        super().__init__()

        self.setMinimumWidth(300)
        self.setMinimumHeight(200)
        self.setMaximumHeight(400)

        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)

        self.setStyleSheet("""
            QLabel {
                border: 2px solid #999;
                border-radius: 6px;
                padding: 8px;
                background-color: #f5f5f5;
                font-family: 'Segoe UI', Arial;
            }
        """)

        font = QFont()
        font.setPointSize(9)
        self.setFont(font)

        self.current_layout = None
        self.update_preview("Auto-detect")

    def update_preview(self, layout_name: str):

        if layout_name == self.current_layout:
            return

        self.current_layout = layout_name

        if layout_name not in self.LAYOUT_DESCRIPTIONS:
            layout_name = "Auto-detect"

        pixmap = self._load_preview_image(layout_name)

        # =========================
        # IMAGE MODE (FILL OPTIMIZED)
        # =========================
        if pixmap is not None and not pixmap.isNull():

            self.setText("")
            self.setPixmap(QPixmap())
            self.setTextFormat(Qt.PlainText)

            w = self.width() if self.width() > 0 else 300
            h = self.height() if self.height() > 0 else 250

            # use almost full available space
            target_size = QSize(int(w * 0.98), int(h * 0.95))

            scaled = pixmap.scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            scaled.setDevicePixelRatio(self.devicePixelRatioF())

            self.setPixmap(scaled)
            self.setAlignment(Qt.AlignCenter)
            return

        # =========================
        # TEXT MODE (FALLBACK)
        # =========================
        self.setPixmap(QPixmap())
        self.setTextFormat(Qt.RichText)

        info = self.LAYOUT_DESCRIPTIONS[layout_name]

        html = f"""
        <div style="text-align: center;">
            <div style="font-size: 28px; margin-bottom: 8px;">{info['icon']}</div>

            <p style="font-weight: bold; font-size: 11pt; margin: 4px 0; color: #333;">
                {info['title']}
            </p>

            <p style="font-size: 9pt; margin: 0; color: #666;">
                {info['description']}
            </p>

            <div style="margin-top: 10px; padding: 8px;
                        background-color: {info['color']};
                        border-radius: 3px;
                        border: 1px solid #999;
                        font-size: 8pt;">
                <span style="color: #444;">
                    No custom image - fallback preview
                </span>
            </div>
        </div>
        """

        self.setText(html)

    def _load_preview_image(self, layout_name: str):

        if layout_name not in LAYOUT_IMAGE_MAPPING:
            return None

        image_path = ASSETS_DIR / LAYOUT_IMAGE_MAPPING[layout_name]

        if not image_path.exists():
            print(f"[Preview] Missing file: {image_path}")
            return None

        pixmap = QPixmap(str(image_path))

        if pixmap.isNull():
            print(f"[Preview] Failed loading: {image_path}")
            return None

        return pixmap