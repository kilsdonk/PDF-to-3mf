#!/usr/bin/env python3
"""
start.py - Flask version for Render deployment
Updated with PDF processing support
"""

import os
import sys
import json
import tempfile
import time
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory

# Add current directory to path for module imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Check for available processing modules
try:
    from curve import generate_3mf_from_html_json
    GCODE_3MF_AVAILABLE = True
except ImportError:
    GCODE_3MF_AVAILABLE = False

try:
    from geometry_engine import round_svg_corners, generate_wall_offset_coordinates
    SHAPELY_AVAILABLE = True
    print("✓ Local Geometry Engine linked successfully")
except ImportError as e:
    SHAPELY_AVAILABLE = False
    print(f"⚠ Could not link Geometry Engine: {e}")

try:
    from pdf_processor import pdf_to_svg_pipeline, pdf_to_bitmap_png, bitmap_to_svg_potrace
    PDF_PROCESSOR_AVAILABLE = True
    print("✓ PDF Processor linked successfully")
except ImportError as e:
    PDF_PROCESSOR_AVAILABLE = False
    print(f"⚠ Could not link PDF Processor: {e}")

try:
    from hole_processor import get_hole_positions
    HOLE_PROCESSOR_AVAILABLE = True
    print("✓ Hole Processor linked successfully")
except ImportError as e:
    HOLE_PROCESSOR_AVAILABLE = False
    print(f"⚠ Could not link Hole Processor: {e}")

# ── App init ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

def debug_log(message, data=None):
    print(f"[DEBUG] {message}")
    if data is not None:
        print(f"[DEBUG-DATA] {data}")

# =====================================================
# BASIC ROUTES
# =====================================================

@app.route('/')
def index():
    return render_template('template.html')

@app.route('/test_upload.html')
def test_upload():
    return render_template('test_upload.html')

@app.route('/app2.html')
def app2():
    return render_template('app2.html')

@app.route('/status')
def status():
    return f"""<!DOCTYPE html>
<html><head><title>Server Status</title></head>
<body>
    <h1>Multi-Printer 3D Server - Flask</h1>
    <p>Status: Running</p>
    <p>Script Directory: {script_dir}</p>
    <ul>
        <li>gcode_3mf: {'Available' if GCODE_3MF_AVAILABLE else 'Not Available'}</li>
        <li>Geometry Engine: {'Available' if SHAPELY_AVAILABLE else 'Not Available'}</li>
        <li>PDF Processor: {'Available' if PDF_PROCESSOR_AVAILABLE else 'Not Available'}</li>
        <li>Hole Processor: {'Available' if HOLE_PROCESSOR_AVAILABLE else 'Not Available'}</li>
    </ul>
</body></html>"""

@app.route('/<path:filename>')
def serve_files(filename):
    file_path = os.path.join(script_dir, filename)
    if os.path.exists(file_path):
        if filename.endswith('.json'):
            with open(file_path, 'r') as f:
                return jsonify(json.load(f))
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
            return send_file(file_path)
        elif filename.endswith('.html'):
            return render_template(filename)
        elif '.' not in filename:
            try:
                return render_template(filename + '.html')
            except:
                pass
    return "Not found", 404

# =====================================================
# 3MF / GCODE ENDPOINT
# =====================================================

@app.route('/process', methods=['POST'])
def process():
    try:
        data = request.get_json()
        print("\n" + "="*80)
        print("DEBUG /process endpoint")
        print("="*80)
        print(f"Keys in request: {list(data.keys())}")

        if 'payload' in data:
            print("⚠️ Data is wrapped in 'payload', unwrapping...")
            data = data['payload']

        if not GCODE_3MF_AVAILABLE:
            return jsonify({'success': False, 'error': 'Processing module not available'}), 500

        success, result = generate_3mf_from_html_json(data)
        if success:
            return jsonify({'success': True, 'result': result})
        else:
            return jsonify({'success': False, 'error': result}), 500

    except Exception as e:
        debug_log(f"Error in /process: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================
# PDF → SVG ENDPOINT (simple, no holes)
# =====================================================

@app.route('/pdf_convert', methods=['POST'])
def pdf_convert():
    try:
        if not PDF_PROCESSOR_AVAILABLE:
            return jsonify({'success': False, 'error': 'PDF processor not available'}), 500

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['file']
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'Only PDF files accepted'}), 400

        dpi = request.form.get('dpi', None)
        if dpi:
            dpi = int(dpi)

        uploads_dir = os.path.join(tempfile.gettempdir(), 'pdf_uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        timestamp = int(time.time())

        pdf_path = os.path.join(uploads_dir, f'input_{timestamp}.pdf')
        svg_path = os.path.join(uploads_dir, f'output_{timestamp}.svg')
        file.save(pdf_path)

        print(f"🚀 Converting PDF: {os.path.basename(pdf_path)}")
        success, result_path, png_path, msg = pdf_to_svg_pipeline(pdf_path, svg_path, dpi)

        if not success:
            return jsonify({'success': False, 'error': msg}), 500

        with open(svg_path, 'r') as f:
            svg_content = f.read()

        png_filename = os.path.basename(png_path) if png_path else None

        return jsonify({
            'success':      True,
            'message':      f'Converted {file.filename} successfully',
            'svg_filename': os.path.basename(svg_path),
            'png_filename': png_filename,
            'svg_content':  svg_content,
            'file_size':    os.path.getsize(svg_path)
        })

    except Exception as e:
        debug_log(f"Error in pdf_convert: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================
# PDF + HOLES PIPELINE ENDPOINT (two PDFs)
# =====================================================

@app.route('/pdf_holes_convert', methods=['POST'])
def pdf_holes_convert():
    """
    Single-PDF pipeline:
    - pdf_file : PDF with black filled letters + red horizontal guide lines
    """
    try:
        if not PDF_PROCESSOR_AVAILABLE:
            return jsonify({'success': False, 'error': 'PDF processor not available'}), 500

        if 'pdf_file' not in request.files:
            return jsonify({'success': False, 'error': 'No PDF uploaded'}), 400

        pdf_file      = request.files['pdf_file']
        hole_diameter = float(request.form.get('hole_diameter', 6.0))
        dpi = request.form.get('dpi', None)
        if dpi:
            dpi = int(dpi)

        uploads_dir = os.path.join(tempfile.gettempdir(), 'pdf_uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        timestamp = int(time.time())

        pdf_path = os.path.join(uploads_dir, f'holes_{timestamp}.pdf')
        pdf_file.save(pdf_path)

        # Step 1: PDF → PNG (clipped to content)
        print(f"📄 Step 1: PDF → PNG")
        png_path = os.path.join(uploads_dir, f'letters_{timestamp}.png')
        success, actual_dpi, w_cm, h_cm, content_rect = pdf_to_bitmap_png(
            pdf_path, png_path, dpi
        )
        if not success:
            return jsonify({'success': False, 'error': 'PDF rasterization failed'}), 500

        # Step 2: Detect holes from red lines, draw onto bitmap
        print(f"🔩 Step 2: Detecting holes from red guide lines")
        from PIL import Image, ImageDraw
        try:
            from hole_processor import get_hole_positions as _ghp
        except ImportError as ie:
            return jsonify({'success': False, 'error': f'hole_processor.py not in server folder: {ie}'}), 500

        hole_positions_mm, page_w_mm, page_h_mm = _ghp(pdf_path, content_rect=content_rect, dpi=actual_dpi)[:3]
        print(f"   🔩 {len(hole_positions_mm)} hole(s) detected")

        img = Image.open(png_path).convert('RGB')
        draw = ImageDraw.Draw(img)
        mm_to_px = actual_dpi / 25.4

        # Hole positions are in full-page mm coords — subtract clip offset for bitmap coords
        clip_x0_mm = (content_rect.x0 / 72 * 25.4) if content_rect else 0
        clip_y0_mm = (content_rect.y0 / 72 * 25.4) if content_rect else 0

        hole_r_px = max(3, int((hole_diameter / 2) * mm_to_px))
        for hx_mm, hy_mm in hole_positions_mm:
            cx = int((hx_mm - clip_x0_mm) * mm_to_px)
            cy = int((hy_mm - clip_y0_mm) * mm_to_px)
            draw.ellipse([cx - hole_r_px, cy - hole_r_px,
                          cx + hole_r_px, cy + hole_r_px],
                         fill=(255, 255, 0), outline=(255, 255, 0))
            print(f"   ⚪ ({hx_mm:.1f}mm, {hy_mm:.1f}mm) → px ({cx},{cy}) r={hole_r_px}px")

        png_holes_path = os.path.join(uploads_dir, f'letters_holes_{timestamp}.png')
        img.save(png_holes_path)
        print(f"   ✅ Bitmap with holes saved")

        # Step 3: Bitmap with holes → SVG
        print(f"🎨 Step 3: PNG → SVG via potrace")
        svg_filename = f'output_holes_{timestamp}.svg'
        svg_path = os.path.join(uploads_dir, svg_filename)
        ok = bitmap_to_svg_potrace(png_holes_path, svg_path, content_rect, actual_dpi)
        if not ok:
            return jsonify({'success': False, 'error': 'potrace vectorization failed'}), 500

        with open(svg_path, 'r') as f:
            svg_content = f.read()

        return jsonify({
            'success':      True,
            'message':      f'Converted with {hole_diameter}mm holes ({len(hole_positions_mm)} holes)',
            'svg_filename': svg_filename,
            'png_filename': os.path.basename(png_holes_path),
            'svg_content':  svg_content,
            'file_size':    os.path.getsize(svg_path)
        })

    except Exception as e:
        debug_log(f"Error in pdf_holes_convert: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# =====================================================
# DOWNLOAD ENDPOINT
# =====================================================

@app.route('/download_svg/<filename>')
def download_svg(filename):
    for folder in ['pdf_uploads', 'shapely_uploads']:
        file_path = os.path.join(tempfile.gettempdir(), folder, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
    return "File not found", 404

# =====================================================
# SHAPELY ENDPOINTS
# =====================================================

@app.route('/shapely_convert', methods=['POST'])
def shapely_convert():
    try:
        if not SHAPELY_AVAILABLE:
            return jsonify({'success': False, 'error': 'Shapely not available'}), 500

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['file']
        file_data = file.read()

        params = {
            'offset':       float(request.form.get('offset', 0)),
            'corner':       float(request.form.get('corner', 0)),
            'white_offset': float(request.form.get('white_offset', 0)),
            'resolution':   int(request.form.get('resolution', 100))
        }

        uploads_dir = os.path.join(tempfile.gettempdir(), 'shapely_uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        filename = f"input_{int(time.time())}.svg"
        input_path = os.path.join(uploads_dir, filename)
        with open(input_path, 'wb') as f:
            f.write(file_data)

        face_filename   = f"face_{filename}"
        return_filename = f"return_{filename}"
        white_filename  = f"white_{filename}"
        face_path   = os.path.join(uploads_dir, face_filename)
        return_path = os.path.join(uploads_dir, return_filename)
        white_path  = os.path.join(uploads_dir, white_filename)

        face_success = round_svg_corners(
            input_path, face_path,
            offset=params['white_offset'], corner_radius=params['corner'],
            curve_resolution=params['resolution']
        )
        return_success = round_svg_corners(
            input_path, return_path,
            offset=params['offset'], corner_radius=params['corner'] + params['offset'],
            curve_resolution=params['resolution']
        )
        white_success = round_svg_corners(
            input_path, white_path,
            offset=0, corner_radius=params['corner'],
            curve_resolution=params['resolution']
        )

        if not (face_success and return_success and white_success):
            return jsonify({'success': False, 'error': 'Processing failed'}), 500

        with open(face_path, 'r') as f:
            face_svg = f.read()
        with open(return_path, 'r') as f:
            return_svg = f.read()

        return jsonify({
            'success':           True,
            'face_svg_content':  face_svg,
            'return_svg_content': return_svg,
            'face_filename':     face_filename,
            'return_filename':   return_filename,
            'white_filename':    white_filename,
            'message':           f"Processed {filename} successfully"
        })

    except Exception as e:
        debug_log(f"Error in shapely_convert: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/shapely_download/<filename>')
def shapely_download(filename):
    uploads_dir = os.path.join(tempfile.gettempdir(), 'shapely_uploads')
    file_path = os.path.join(uploads_dir, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
