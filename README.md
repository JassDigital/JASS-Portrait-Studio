# JASS Portrait Studio

**Version:** 0.2.0 — Professional Editing Tools  
**Platform:** Windows desktop

## New in v0.2.0

- Crop by entering an exact rectangle in pixels.
- Rotate left or right by 90 degrees.
- RGB histogram panel.
- Expanded editing toolbar and Image menu.
- Undo/redo history now captures crop and rotation geometry as well as adjustment values.
- Project saves include a companion PNG (`.source.png`) so crop/rotation state can reopen faithfully.

## Included

- Open JPEG, PNG, TIFF, BMP and WebP images.
- Exposure, brightness, contrast, saturation, sharpness, warmth and vignette.
- Before/original preview toggle.
- Undo, redo and reset adjustments.
- Export JPEG, PNG, WebP and TIFF.
- Save/reopen `.jps` projects.
- Local processing; no photo uploads.

## Run

```powershell
python -m pip install --upgrade pip
python -m pip install PySide6 numpy Pillow pytest
python app.py
```

OpenCV remains in the requirements for upcoming computer-vision features. Python 3.11+ is recommended; confirm wheel availability for your Python version.

## Project file note

The `.jps` project uses a companion `.source.png` to retain crop and rotation changes. Keep the `.jps` and companion PNG together when moving projects. The original source file is not modified.

## Roadmap

- v0.1.0: editor foundation and basic adjustments
- v0.2.0: crop, rotate, histogram and expanded editing workflow
- v0.3.0: localized masks and retouching
- v0.4.0: face landmarks and eye/skin tools
- v0.5.0: background removal/replacement and cinematic presets
- v0.6.0: batch processing and export profiles
- v1.0.0: packaging, performance, accessibility and release hardening
