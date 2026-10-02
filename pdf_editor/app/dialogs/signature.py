"""Create a signature: draw it, type it in a script-style font, or import an image."""

from __future__ import annotations

import os

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import InvalidInput
from ...core.operations.images import trim_image, white_to_transparent
from .settings import ColorButton

SCRIPT_FONTS = (
    "Segoe Script", "Brush Script MT", "Lucida Handwriting", "Bradley Hand", "Snell Roundhand",
    "Apple Chancery", "Z003", "URW Chancery L", "Dancing Script", "Great Vibes", "Allura", "Pacifico",
    "Comic Sans MS",
)


def image_to_png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def best_script_font() -> str:
    """The first installed handwriting-style font, else a generic fallback."""
    families = set(QFontDatabase.families())
    for name in SCRIPT_FONTS:
        if name in families:
            return name
    return QFont().defaultFamily()


def render_typed_signature(text: str, family: str, color: str = "#10306b") -> bytes:
    """Render text into a transparent, trimmed PNG."""
    if not text.strip():
        raise InvalidInput("Type your name first.")
    font = QFont(family)
    font.setPixelSize(160)
    if family not in SCRIPT_FONTS:
        font.setItalic(True)
    image = QImage(160 * max(4, len(text)), 320, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(20, 0, image.width() - 40, image.height()), Qt.AlignmentFlag.AlignVCenter, text)
    painter.end()
    return trim_image(image_to_png(image), padding=8)


class SignaturePad(QWidget):
    """A drawing surface; strokes are rendered at 3x resolution for crisp output."""

    SCALE = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 180)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.paths: list[QPainterPath] = []
        self.color = "#10306b"
        self.pen_width = 2.5

    def clear(self) -> None:
        self.paths.clear()
        self.update()

    def is_empty(self) -> bool:
        return not self.paths

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.paths.append(QPainterPath(event.position()))
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.paths and event.buttons() & Qt.MouseButton.LeftButton:
            self.paths[-1].lineTo(event.position())
            self.update()

    def _pen(self, scale: float = 1.0) -> QPen:
        pen = QPen(QColor(self.color), self.pen_width * scale)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#c8c8c8"), 1, Qt.PenStyle.DashLine))
        baseline = self.height() * 0.75
        painter.drawLine(QPointF(20, baseline), QPointF(self.width() - 20, baseline))
        painter.setPen(self._pen())
        for path in self.paths:
            painter.drawPath(path)

    def to_png(self) -> bytes:
        if self.is_empty():
            raise InvalidInput("Draw your signature first.")
        image = QImage(self.rect().width() * self.SCALE, self.rect().height() * self.SCALE, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.SCALE, self.SCALE)
        painter.setPen(self._pen())
        for path in self.paths:
            painter.drawPath(path)
        painter.end()
        return trim_image(image_to_png(image), padding=6)


class SignatureDialog(QDialog):
    """Returns a transparent PNG via :attr:`png`, optionally saved for reuse."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Signature")
        self.png: bytes | None = None
        self.tabs = QTabWidget(self)
        # draw
        draw = QWidget(self)
        self.pad = SignaturePad(draw)
        self.draw_color = ColorButton(self.pad.color, draw)
        clear = QPushButton("Clear", draw)
        clear.clicked.connect(self.pad.clear)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ink:", draw))
        row.addWidget(self.draw_color)
        row.addStretch(1)
        row.addWidget(clear)
        draw_layout = QVBoxLayout(draw)
        draw_layout.addWidget(QLabel("Sign with the mouse, pen or touchpad:", draw))
        draw_layout.addWidget(self.pad, 1)
        draw_layout.addLayout(row)
        self.tabs.addTab(draw, "Draw")
        # type
        typed = QWidget(self)
        self.name = QLineEdit(typed)
        self.font_box = QFontComboBox(typed)
        self.font_box.setCurrentFont(QFont(best_script_font()))
        self.type_color = ColorButton("#10306b", typed)
        self.preview = QLabel(typed)
        self.preview.setMinimumHeight(110)
        self.preview.setStyleSheet("background: white; border: 1px solid #ccc;")
        self.name.textChanged.connect(self._update_preview)
        self.font_box.currentFontChanged.connect(lambda _f: self._update_preview())
        form = QFormLayout(typed)
        form.addRow("Your name:", self.name)
        form.addRow("Font:", self.font_box)
        form.addRow("Colour:", self.type_color)
        form.addRow(self.preview)
        self.tabs.addTab(typed, "Type")
        # import
        imported = QWidget(self)
        self.image_path = QLineEdit(imported)
        browse = QPushButton("Browse…", imported)
        browse.clicked.connect(self._browse)
        self.remove_white = QCheckBox("Make white background transparent", imported)
        self.remove_white.setChecked(True)
        path_row = QHBoxLayout()
        path_row.addWidget(self.image_path, 1)
        path_row.addWidget(browse)
        import_layout = QVBoxLayout(imported)
        import_layout.addWidget(QLabel("Use a scan or photo of your signature:", imported))
        import_layout.addLayout(path_row)
        import_layout.addWidget(self.remove_white)
        import_layout.addStretch(1)
        self.tabs.addTab(imported, "Import Image")

        self.save = QCheckBox("Save this signature for later", self)
        self.save.setChecked(True)
        self.save_name = QLineEdit("My signature", self)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save)
        save_row.addWidget(self.save_name, 1)
        self.error = QLabel(self)
        self.error.setStyleSheet("color: #c0392b")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(save_row)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Signature Image", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)")
        if path:
            self.image_path.setText(path)

    def _update_preview(self) -> None:
        from PySide6.QtGui import QPixmap

        try:
            png = render_typed_signature(self.name.text(), self.font_box.currentFont().family(), self.type_color.color)
        except InvalidInput:
            self.preview.clear()
            return
        pix = QPixmap()
        pix.loadFromData(png)
        self.preview.setPixmap(pix.scaledToHeight(100, Qt.TransformationMode.SmoothTransformation))

    def build_png(self) -> bytes:
        index = self.tabs.currentIndex()
        if index == 0:
            self.pad.color = self.draw_color.color
            return self.pad.to_png()
        if index == 1:
            return render_typed_signature(self.name.text(), self.font_box.currentFont().family(), self.type_color.color)
        path = self.image_path.text().strip()
        if not path or not os.path.isfile(path):
            raise InvalidInput("Choose an image file.")
        from ...core.operations.images import load_image_bytes

        data = load_image_bytes(path)
        if self.remove_white.isChecked():
            data = white_to_transparent(data)
        return trim_image(data)

    def accept(self) -> None:
        try:
            self.png = self.build_png()
        except InvalidInput as exc:
            self.error.setText(exc.message)
            return
        super().accept()
