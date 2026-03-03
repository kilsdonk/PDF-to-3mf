# PDF → SVG Converter — System Documentation

## Overview

Two tools running in one web interface (`test_upload.html`), both served by `start.py`.

---

## Tool 1 — PDF → SVG

Converts a clean letter artwork PDF into a lasercutter-ready SVG.

### Workflow
```
PDF  →  PNG bitmap  →  SVG (via vtracer)
```

### Files involved

| File | Role |
|------|------|
| `start.py` | Flask endpoint `/pdf_convert` — receives upload, calls pipeline |
| `pdf_processor.py` | Core logic: rasterizes PDF to PNG, splits into letter regions, vectorizes each region via vtracer, reassembles into one SVG |
| `templates/test_upload.html` | Upload UI — tab **📄 PDF → SVG** |

### What `pdf_processor.py` does step by step
1. Opens PDF with PyMuPDF, measures content bounding box in cm
2. Auto-selects DPI: 72 for large signs (>20cm), 150 for small
3. Rasterizes to PNG bitmap
4. Scans columns to find individual letter regions (gaps between letters)
5. Crops each letter, runs vtracer on each separately (prevents stacking artifacts)
6. Reassembles all letter SVG paths with correct `translate()` positions
7. Returns final SVG with real mm dimensions

---

## Tool 2 — Letters + Drill Holes

Converts letter artwork to SVG and adds drill holes at the positions where the signmaker's guide lines cross each letter stroke.

### Workflow
```
Letters PDF  →  PNG bitmap  ─────────────────────────────┐
                                                          ▼
Holes PDF  →  guide line positions  →  draw holes  →  PNG with holes  →  SVG
```

### Files involved

| File | Role |
|------|------|
| `start.py` | Flask endpoint `/pdf_holes_convert` — receives two uploads, orchestrates pipeline |
| `pdf_processor.py` | Rasterizes letters PDF to PNG; vectorizes final holed PNG to SVG |
| `hole_processor.py` | Reads guide lines from holes PDF, scans letter crossings, returns hole positions in mm |
| `templates/test_upload.html` | Upload UI — tab **🔩 Letters + Drill Holes** |

### Two PDFs required

| Upload | Content |
|--------|---------|
| **Letters PDF** | Clean artwork — letter shapes only, no guide lines. Used for the final SVG output. |
| **Holes PDF** | Same artwork + horizontal guide lines drawn by the signmaker. Used only for hole position detection. |

### What `hole_processor.py` does step by step
1. Opens holes PDF with PyMuPDF
2. Finds all unfilled horizontal line strokes → these are the guide lines
3. Rasterizes holes PDF to bitmap at 72 DPI
4. For each guide line: scans the row for dark pixel groups (letter crossings)
5. Groups crossings by letter bounding box (from PDF fill shapes)
6. Selects outer two strokes per letter (left and right legs)
7. Uses distance transform (`cv2.distanceTransform`) to find the most central X within each stroke
8. Returns list of `(x_mm, y_mm)` hole positions

### What `start.py` does with hole positions
1. Calls `get_hole_positions(holes_pdf)` → list of mm coordinates
2. Opens the letters PNG
3. Draws white filled circles at each position (hole diameter configurable, default 6mm)
4. Saves new PNG with holes
5. Calls `bitmap_to_svg_vtracer()` with the holed PNG for rendering but the **original PNG** for region detection — this prevents white holes from merging letter regions

---

## Shared infrastructure

### `start.py` — all endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main app template |
| `/test_upload.html` | GET | PDF converter UI |
| `/pdf_convert` | POST | Simple PDF → SVG |
| `/pdf_holes_convert` | POST | PDF + holes → SVG |
| `/download_svg/<filename>` | GET | Download any output file |
| `/shapely_convert` | POST | Shapely corner rounding |
| `/shapely_download/<filename>` | GET | Download Shapely output |
| `/process` | POST | 3MF / gcode generation |

### `geometry_engine.py`
Shapely-based SVG processing for corner rounding and wall offsets. Used by `/shapely_convert`. Includes hole-preservation fix so letters like O, R, A keep their counter (inner hole) through the smoothing buffer operations.

---

## Required files in server folder

```
start.py
pdf_processor.py
hole_processor.py
geometry_engine.py
templates/
    test_upload.html
    template.html
```

## Python dependencies

| Package | Used by |
|---------|---------|
| `flask` | `start.py` |
| `PyMuPDF` (fitz) | `pdf_processor.py`, `hole_processor.py` |
| `vtracer` | `pdf_processor.py` |
| `opencv-python` (cv2) | `hole_processor.py` |
| `numpy` | `hole_processor.py` |
| `Pillow` (PIL) | `start.py` (drawing holes), `pdf_processor.py` |
| `shapely` | `geometry_engine.py` |

`skimage` is **not** required for normal operation — it is only imported lazily inside `process_holes()` which is not called by the web interface.
