
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import (
    QAction,
    QColor,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QSlider,
    QPushButton,
    QToolBar,
    QStatusBar,
    QScrollArea,
    QGroupBox,
    QSplitter,
    QFormLayout,
    QDialog,
    QDialogButtonBox,
    QSpinBox,
    QComboBox,
)


APP_NAME = "JASS Portrait Studio"
VERSION = "0.2.0"


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    image = image.convert("RGB")
    data = image.tobytes("raw", "RGB")
    qimage = QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def apply_adjustments(image: Image.Image, values: dict[str, int]) -> Image.Image:
    """Apply edits from the current source image; never compound preview edits."""
    result = image.convert("RGB").copy()
    exposure = values["exposure"] / 100.0
    if exposure:
        arr = np.asarray(result).astype(np.float32)
        arr *= 2.0 ** exposure
        result = Image.fromarray(np.uint8(np.clip(arr, 0, 255)))
    result = ImageEnhance.Brightness(result).enhance(1.0 + values["brightness"] / 100.0)
    result = ImageEnhance.Contrast(result).enhance(1.0 + values["contrast"] / 100.0)
    result = ImageEnhance.Color(result).enhance(1.0 + values["saturation"] / 100.0)
    result = ImageEnhance.Sharpness(result).enhance(1.0 + values["sharpness"] / 100.0)
    warmth = values["warmth"]
    if warmth:
        arr = np.asarray(result).astype(np.int16)
        arr[:, :, 0] = np.clip(arr[:, :, 0] + warmth, 0, 255)
        arr[:, :, 2] = np.clip(arr[:, :, 2] - warmth, 0, 255)
        result = Image.fromarray(arr.astype(np.uint8))
    vignette = max(0, values["vignette"]) / 100.0
    if vignette:
        arr = np.asarray(result).astype(np.float32)
        h, w = arr.shape[:2]
        y, x = np.ogrid[-1:1:complex(h), -1:1:complex(w)]
        radius = np.sqrt(x * x + y * y)
        mask = np.clip(1.0 - vignette * np.maximum(0, radius - 0.25), 0.55, 1.0)
        arr *= mask[:, :, None]
        result = Image.fromarray(np.uint8(np.clip(arr, 0, 255)))
    return result



class HistogramWidget(QWidget):
    """Draw a lightweight RGB histogram for the current preview."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.histograms = None
        self.setMinimumHeight(100)
        self.setMaximumHeight(145)
        self.setToolTip("RGB histogram of the current preview")

    def set_image(self, image: Image.Image | None):
        """Calculate normalized RGB histograms from the supplied image."""
        self.histograms = None

        if image is not None:
            arr = np.asarray(image.convert("RGB"))

            histograms = [
                np.histogram(
                    arr[:, :, channel],
                    bins=64,
                    range=(0, 256),
                )[0]
                for channel in range(3)
            ]

            peak = max(int(hist.max()) for hist in histograms)

            if peak > 0:
                self.histograms = [
                    hist.astype(np.float32) / peak
                    for hist in histograms
                ]

        self.update()

    def paintEvent(self, event):
        """Render the histogram using Qt's painting API."""
        painter = QPainter(self)

        try:
            painter.setRenderHint(
                QPainter.RenderHint.Antialiasing, True
            )

            painter.fillRect(self.rect(), self.palette().base())

            border_color = self.palette().mid().color()
            painter.setPen(QPen(border_color, 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

            if not self.histograms:
                painter.setPen(border_color)
                painter.drawText(
                    self.rect(),
                    Qt.AlignmentFlag.AlignCenter,
                    "Histogram appears here",
                )
                return

            # RGB channel colors. QColor accepts RGBA values.
            colors = [
                QColor(220, 75, 75, 180),
                QColor(75, 190, 100, 180),
                QColor(80, 130, 230, 180),
            ]

            margin = 5
            width = max(1, self.width() - 2 * margin)
            height = max(1, self.height() - 2 * margin)

            for histogram, color in zip(self.histograms, colors):
                if len(histogram) < 2:
                    continue

                pen = QPen(color)
                pen.setWidth(1)
                painter.setPen(pen)

                points = []

                for index, value in enumerate(histogram):
                    x = margin + (
                        index / (len(histogram) - 1)
                    ) * width

                    y = margin + height - (
                        float(value) * height
                    )

                    points.append((round(x), round(y)))

                for start, end in zip(points, points[1:]):
                    painter.drawLine(
                        start[0],
                        start[1],
                        end[0],
                        end[1],
                    )

        finally:
            painter.end()



class CropDialog(QDialog):
    def __init__(self, width: int, height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop Image")
        self.setMinimumWidth(330)
        layout = QVBoxLayout(self)
        note = QLabel(f"Image size: {width} × {height} pixels. Enter a crop rectangle.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.x = self._spin(0, width - 1, 0)
        self.y = self._spin(0, height - 1, 0)
        self.w = self._spin(1, width, width)
        self.h = self._spin(1, height, height)
        form.addRow("Left (X)", self.x)
        form.addRow("Top (Y)", self.y)
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        layout.addLayout(form)
        self.x.valueChanged.connect(lambda v: self.w.setMaximum(max(1, width - v)))
        self.y.valueChanged.connect(lambda v: self.h.setMaximum(max(1, height - v)))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(minimum, maximum, value):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def crop_box(self):
        return self.x.value(), self.y.value(), self.x.value() + self.w.value(), self.y.value() + self.h.value()


class PortraitStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1380, 900)
        self.original: Image.Image | None = None
        self.current_path: Path | None = None
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.values = self._default_values()
        self.sliders: dict[str, QSlider] = {}
        self.value_labels: dict[str, QLabel] = {}
        self.before_after = False
        self._build_ui()
        self._build_actions()
        self._update_buttons()
        self.statusBar().showMessage("Open a portrait to begin.")

    @staticmethod
    def _default_values():
        return {"exposure": 0, "brightness": 0, "contrast": 0, "saturation": 0,
                "sharpness": 0, "warmth": 0, "vignette": 0}

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel("Open a photo to begin\n\nSupported: JPEG, PNG, TIFF, BMP, WebP")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(480, 420)
        self.preview.setStyleSheet("QLabel { background:#20242b; color:#d9dee7; border:1px solid #3b414c; border-radius:8px; padding:12px; }")
        preview_layout.addWidget(self.preview, 1)

        preview_buttons = QHBoxLayout()
        self.compare_btn = QPushButton("Show Original")
        self.compare_btn.setCheckable(True)
        self.compare_btn.toggled.connect(self._toggle_before_after)
        self.fit_btn = QPushButton("Fit Image")
        self.fit_btn.clicked.connect(self._render_preview)
        self.rotate_left_btn = QPushButton("↶ Rotate 90°")
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_image(-90))
        self.rotate_right_btn = QPushButton("↷ Rotate 90°")
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_image(90))
        self.crop_btn = QPushButton("Crop…")
        self.crop_btn.clicked.connect(self.crop_image)
        for button in (self.compare_btn, self.rotate_left_btn, self.rotate_right_btn, self.crop_btn):
            preview_buttons.addWidget(button)
        preview_buttons.addStretch(1)
        preview_buttons.addWidget(self.fit_btn)
        preview_layout.addLayout(preview_buttons)

        hist_group = QGroupBox("Histogram")
        hist_layout = QVBoxLayout(hist_group)
        self.histogram = HistogramWidget()
        hist_layout.addWidget(self.histogram)
        preview_layout.addWidget(hist_group)
        splitter.addWidget(preview_panel)

        controls = QWidget()
        controls.setMinimumWidth(290)
        controls.setMaximumWidth(400)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(8, 0, 0, 0)
        heading = QLabel("Portrait Adjustments")
        heading.setStyleSheet("font-size:18px; font-weight:600; padding:4px 0;")
        controls_layout.addWidget(heading)
        intro = QLabel("Adjustments are applied from the source image. The original file remains unchanged.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#7b8493;")
        controls_layout.addWidget(intro)

        group = QGroupBox("Light and Color")
        form = QFormLayout(group)
        slider_specs = [
            ("exposure", "Exposure", -100, 100),
            ("brightness", "Brightness", -50, 50),
            ("contrast", "Contrast", -50, 100),
            ("saturation", "Saturation", -100, 100),
            ("sharpness", "Sharpness", -50, 150),
            ("warmth", "Warmth", -50, 50),
            ("vignette", "Vignette", 0, 80),
        ]
        for key, label, low, high in slider_specs:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 3, 0, 3)
            value_label = QLabel("0")
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setValue(0)
            slider.valueChanged.connect(lambda val, k=key: self._slider_changed(k, val))
            row_layout.addWidget(slider)
            row_layout.addWidget(value_label)
            form.addRow(label, row)
            self.sliders[key] = slider
            self.value_labels[key] = value_label
        controls_layout.addWidget(group)

        buttons = QHBoxLayout()
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn = QPushButton("Redo")
        self.redo_btn.clicked.connect(self.redo)
        buttons.addWidget(self.undo_btn)
        buttons.addWidget(self.redo_btn)
        controls_layout.addLayout(buttons)
        action_buttons = QHBoxLayout()
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_adjustments)
        export_btn = QPushButton("Export Image")
        export_btn.clicked.connect(self.export_image)
        action_buttons.addWidget(reset_btn)
        action_buttons.addWidget(export_btn)
        controls_layout.addLayout(action_buttons)
        controls_layout.addStretch(1)
        note = QLabel("Tip: subtle adjustments usually look more natural. Crop and rotation are reversible within the editing session.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#7b8493; font-size:11px;")
        controls_layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(controls)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([980, 350])
        layout.addWidget(splitter)
        self.setCentralWidget(root)

        toolbar = QToolBar("Main")
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)
        for label, callback in [("Open", self.open_image), ("Save Project", self.save_project),
                                ("Open Project", self.open_project), ("Crop", self.crop_image),
                                ("Export", self.export_image)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)

    def _build_actions(self):
        file_menu = self.menuBar().addMenu("&File")
        actions = [("Open Image…", self.open_image, QKeySequence.StandardKey.Open),
                   ("Open Project…", self.open_project, None),
                   ("Save Project…", self.save_project, QKeySequence.StandardKey.Save),
                   ("Export Image…", self.export_image, QKeySequence.StandardKey.SaveAs),
                   ("Exit", self.close, None)]
        for label, callback, shortcut in actions:
            action = QAction(label, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
            file_menu.addAction(action)
        edit_menu = self.menuBar().addMenu("&Edit")
        for label, callback, shortcut in [("Undo", self.undo, QKeySequence.StandardKey.Undo),
                                          ("Redo", self.redo, QKeySequence.StandardKey.Redo),
                                          ("Reset Adjustments", self.reset_adjustments, None)]:
            action = QAction(label, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
            edit_menu.addAction(action)
        image_menu = self.menuBar().addMenu("&Image")
        for label, callback in [("Crop…", self.crop_image), ("Rotate Left 90°", lambda: self.rotate_image(-90)),
                                ("Rotate Right 90°", lambda: self.rotate_image(90))]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            image_menu.addAction(action)

    def _snapshot(self):
        return {"image": self.original.copy() if self.original else None,
                "values": self.values.copy(), "path": self.current_path}

    def _push_undo(self):
        self.undo_stack.append(self._snapshot())
        self.redo_stack.clear()

    def _restore(self, state):
        self.original = state["image"].copy() if state["image"] else None
        self.values = state["values"].copy()
        self.current_path = state["path"]
        self._sync_sliders()
        self._render_preview()
        self._update_buttons()

    def open_image(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Portrait", "", "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp)")
        if not filename:
            return
        try:
            image = ImageOps.exif_transpose(Image.open(filename)).convert("RGB")
            self.original = image.copy()
            self.current_path = Path(filename)
            self.values = self._default_values()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._sync_sliders()
            self.compare_btn.setChecked(False)
            self._render_preview()
            self.statusBar().showMessage(f"Loaded {self.current_path.name} — {image.width} × {image.height}")
            self._update_buttons()
        except Exception as exc:
            QMessageBox.critical(self, "Could not open image", str(exc))

    def _slider_changed(self, key, value):
        self.value_labels[key].setText(str(value))
        if self.original is None or self.values[key] == value:
            return
        # Store a history entry only for changed slider values. This is reliable,
        # although a future refinement can group continuous slider drags.
        self._push_undo()
        self.values[key] = value
        self._render_preview()
        self._update_buttons()

    def _sync_sliders(self):
        for key, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(self.values[key])
            slider.blockSignals(False)
            self.value_labels[key].setText(str(self.values[key]))

    def _render_preview(self):
        if self.original is None:
            self.histogram.set_image(None)
            return
        edited = apply_adjustments(self.original, self.values)
        self.histogram.set_image(edited)
        image = self.original if self.before_after else edited
        pixmap = pil_to_qpixmap(image)
        available = self.preview.size() - QSize(24, 24)
        self.preview.setPixmap(pixmap.scaled(available, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_preview()

    def _toggle_before_after(self, checked):
        self.before_after = checked
        self.compare_btn.setText("Show Edited" if checked else "Show Original")
        self._render_preview()

    def rotate_image(self, degrees):
        if self.original is None:
            return
        self._push_undo()
        # PIL positive angles rotate counterclockwise; expand retains the full image.
        self.original = self.original.rotate(degrees, expand=True)
        self._render_preview()
        self.statusBar().showMessage(f"Rotated image {degrees}°")

    def crop_image(self):
        if self.original is None:
            QMessageBox.information(self, "No image", "Open a portrait before cropping.")
            return
        dialog = CropDialog(self.original.width, self.original.height, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        box = dialog.crop_box()
        if box[2] <= box[0] or box[3] <= box[1]:
            QMessageBox.warning(self, "Invalid crop", "Crop width and height must be greater than zero.")
            return
        self._push_undo()
        self.original = self.original.crop(box)
        self._render_preview()
        self.statusBar().showMessage(f"Cropped to {self.original.width} × {self.original.height}")

    def reset_adjustments(self):
        if self.original is None:
            return
        self._push_undo()
        self.values = self._default_values()
        self._sync_sliders()
        self._render_preview()
        self._update_buttons()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())

    def _update_buttons(self):
        if hasattr(self, "undo_btn"):
            self.undo_btn.setEnabled(bool(self.undo_stack))
            self.redo_btn.setEnabled(bool(self.redo_stack))

    def export_image(self):
        if self.original is None:
            QMessageBox.information(self, "No image", "Open a portrait before exporting.")
            return
        default_name = (self.current_path.stem if self.current_path else "portrait") + "_edited.jpg"
        filename, _ = QFileDialog.getSaveFileName(self, "Export Edited Portrait", default_name,
            "JPEG Image (*.jpg *.jpeg);;PNG Image (*.png);;WebP Image (*.webp);;TIFF Image (*.tiff)")
        if not filename:
            return
        try:
            output = apply_adjustments(self.original, self.values)
            suffix = Path(filename).suffix.lower()
            if not suffix:
                filename += ".jpg"
                suffix = ".jpg"
            if suffix in (".jpg", ".jpeg"):
                output.save(filename, quality=95, optimize=True)
            else:
                output.save(filename)
            self.statusBar().showMessage(f"Exported {Path(filename).name}")
            QMessageBox.information(self, "Export complete", f"Saved edited image to:\n{filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def save_project(self):
        if self.original is None:
            QMessageBox.information(self, "No image", "Open an image before saving a project.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Save Portrait Studio Project",
            str((self.current_path or Path("portrait")).with_suffix(".jps")), "JASS Portrait Studio Project (*.jps)")
        if not filename:
            return
        try:
            payload = {"app": APP_NAME, "version": VERSION,
                       "source_image": str(self.current_path.resolve()) if self.current_path else None,
                       "working_image": None, "adjustments": self.values,
                       "note": "v0.2 project stores edits and source path; crop/rotation are stored in working image in future portable project format."}
            # Store the current geometric edit state in a sidecar image so projects reopen faithfully.
            sidecar = Path(filename).with_suffix(".source.png")
            self.original.save(sidecar, format="PNG")
            payload["working_image"] = sidecar.name
            Path(filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.statusBar().showMessage(f"Project saved: {Path(filename).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Project save failed", str(exc))

    def open_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Portrait Studio Project", "", "JASS Portrait Studio Project (*.jps);;JSON (*.json)")
        if not filename:
            return
        try:
            payload = json.loads(Path(filename).read_text(encoding="utf-8"))
            working = payload.get("working_image")
            source = Path(filename).parent / working if working else None
            if not source or not source.exists():
                source_value = payload.get("source_image")
                source = Path(source_value) if source_value else None
            if not source or not source.exists():
                selected, _ = QFileDialog.getOpenFileName(self, "Locate Source Image", "", "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp)")
                if not selected:
                    return
                source = Path(selected)
            self.original = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
            self.current_path = Path(payload.get("source_image") or source)
            incoming = payload.get("adjustments", {})
            self.values = {key: int(incoming.get(key, 0)) for key in self.values}
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._sync_sliders()
            self.compare_btn.setChecked(False)
            self._render_preview()
            self.statusBar().showMessage(f"Project opened: {Path(filename).name}")
            self._update_buttons()
        except Exception as exc:
            QMessageBox.critical(self, "Could not open project", str(exc))


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PortraitStudio()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
