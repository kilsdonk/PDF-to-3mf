
# SVG to 3MF Pipeline

A complete web-based pipeline system that converts SVG files into 3MF files ready for 3D printing.

Designed specifically for multi-layer 3D printing with advanced features like infill generation,
coordinate mapping, and compound SVG path handling.

---

## 🎯 Overview

This pipeline transforms 2D SVG designs into printable 3D models through a multi-stage process:

1. **SVG Processing** – Uses Shapely integration to create offset versions (face, return, white)  
2. **Coordinate Extraction** – Converts SVG paths into printable coordinates with proper subpath separation  
3. **Infill Generation** – Adds configurable infill patterns for structural support  
4. **G-code Generation** – Creates complete G-code with proper extrusion and movement commands  
5. **3MF Packaging** – Bundles everything into industry-standard 3MF files  

---

## ✨ Key Features

- 🌐 Web Interface – HTML-only frontend (JavaScript/HTML/CSS), no backend exposed
- 🔧 Fixed Coordinate Mapping – Consistent and configurable mapping for layered paths
- 🔲 Advanced Infill System – With hole-aware support and pattern options
- 📐 Compound SVG Support – Supports complex multi-subpath SVGs like letters with cutouts
- 🎨 Multi-Layer Printing – Handles multiple filament types per layer group
- ⚡ Real-time Processing – Instant preview and file generation
- 🧱 Secure Architecture – Only the HTML UI is public-facing; pipeline runs server-side behind access control

---

## 🚀 Quick Start (Development Mode)

**Prerequisites**

- Python 3.7+
- Modern web browser (Chrome, Firefox, Edge)
- Optional: Shapely library for advanced SVG handling

**Run Locally**

```bash
git clone https://github.com/yourusername/svg-to-3mf-pipeline.git
cd svg-to-3mf-pipeline
pip install -r requirements.txt
python v179_web.py
```

The system will open `http://localhost:8000` automatically. If the port is busy, it tries 8001–8009.

---

## 📋 Usage Guide

1. Upload SVG file via the web UI
2. Configure offsets, infill settings, and layer parameters
3. Preview face/return wall generation
4. Export G-code and 3MF file

---

## 📦 Repository Structure

| File | Purpose |
|------|---------|
| `v179_web.py` | Entry point and server launcher |
| `pipeline_server.py` | Main pipeline HTTP handler |
| `template.html` | Frontend interface (served statically) |
| `json_to_coordinates.py` | SVG path extraction and conversion |
| `infill_generator.py` | Infill pattern generator |
| `gcode_generator.py` | G-code generation logic |
| `h2d_templates.py` | 3MF packaging & BambuLab template support |
| `LICENSE.txt` | Commercial license |
| `README.md` | This file |

---

## 🔐 Commercial License

This software is proprietary and commercially licensed.  
Usage is strictly prohibited without a valid, signed commercial license agreement.

See `LICENSE.txt` for full legal terms.

Contact:  
- Roger Kilsdonk – kilsdonk@gmail.com  
- Harry Sprangers – harrys@uptbb.com

---

## 🛠️ Support & Contributions

- For issues, questions, or feature requests: open a GitHub Issue
- Contributions welcome: especially for infill patterns, new printer templates, or performance improvements
