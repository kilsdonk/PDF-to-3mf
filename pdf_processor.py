#!/usr/bin/env python3
"""
PDF Processor - Potrace vectorizer (PROFESSIONAL QUALITY)
Converts PDF signage files to clean SVG paths for laser cutting

Potrace is the industry standard vectorizer used by Inkscape internally.
Produces smooth Bezier curves - perfect for signage letters.
No letter splitting needed - traces whole image correctly with holes (O, R, P, A).
"""

import os
import sys
import subprocess
import tempfile
import re

# PDF processing
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
    print("✅ PyMuPDF loaded for PDF processing")
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("❌ PyMuPDF not available")

# PIL for image conversion
try:
    from PIL import Image
    PIL_AVAILABLE = True
    print("✅ Pillow loaded for image processing")
except ImportError:
    PIL_AVAILABLE = False
    print("❌ Pillow not available")


def find_potrace():
    """Find potrace binary on the system."""
    candidates = [
        '/usr/local/bin/potrace',    # Mac Homebrew Intel
        '/opt/homebrew/bin/potrace', # Mac M1/M4 Homebrew
        '/usr/bin/potrace',          # Linux apt
        'potrace',                   # PATH fallback
    ]
    for path in candidates:
        try:
            result = subprocess.run([path, '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ potrace found: {path}")
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    print("❌ potrace not found - install with: brew install potrace (Mac) or apt install potrace (Linux)")
    return None


POTRACE_BIN = find_potrace()
POTRACE_AVAILABLE = POTRACE_BIN is not None


def pdf_to_bitmap_png(pdf_path, output_png_path, dpi=None):
    """
    Convert PDF to PNG bitmap at specified DPI.

    Returns:
        tuple: (success, actual_dpi, width_cm, height_cm, content_rect)
    """
    if not PYMUPDF_AVAILABLE:
        return False, 0, 0, 0, None

    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        return False, 0, 0, 0, None

    page = doc[0]
    page_rect = page.rect
    width_cm  = page_rect.width  / 72 * 2.54
    height_cm = page_rect.height / 72 * 2.54

    # Detect content bounding box from drawings
    content_rect = None
    try:
        drawings = page.get_drawings()
        if drawings:
            xs = [d['rect'].x0 for d in drawings] + [d['rect'].x1 for d in drawings]
            ys = [d['rect'].y0 for d in drawings] + [d['rect'].y1 for d in drawings]
            content_rect = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
            content_w_cm = content_rect.width  / 72 * 2.54
            content_h_cm = content_rect.height / 72 * 2.54
            content_max_cm = max(content_w_cm, content_h_cm)
        else:
            content_max_cm = max(width_cm, height_cm)
    except Exception:
        content_max_cm = max(width_cm, height_cm)

    # Select DPI based on content size.
    # Higher DPI = more pixels = smoother edges = cleaner potrace curves, no spike artifacts.
    # But very large content doesn't need as high DPI (file size / memory tradeoff).
    if dpi:
        actual_dpi = dpi
    else:
        if content_max_cm > 50:
            actual_dpi = 72    # Large letters - low DPI
        elif content_max_cm > 20:
            actual_dpi = 100   # Medium letters
        else:
            actual_dpi = 150   # Small letters - higher DPI for detail
        print(f"   📏 Content size: {content_max_cm:.1f}cm  →  {actual_dpi} DPI")

    zoom = actual_dpi / 72.0
    mat  = fitz.Matrix(zoom, zoom)
    clip = content_rect if content_rect else page.rect
    pix  = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
    doc.close()

    pix.save(output_png_path)
    print(f"   ✅ Bitmap created: {pix.width}x{pix.height} pixels (content only)")

    return True, actual_dpi, width_cm, height_cm, content_rect


def bitmap_to_svg_potrace(png_path, output_svg_path, content_rect=None, actual_dpi=72):
    """
    Convert PNG bitmap to SVG using potrace CLI.

    - No letter splitting needed (traces whole image at once)
    - Correct holes in letters O, R, P, A, B, D via fill-rule=evenodd
    - Smooth Bezier curves (same engine Inkscape uses internally)
    - Correct letter positioning preserved

    Returns:
        bool: True if successful
    """
    if not POTRACE_AVAILABLE:
        print("   ❌ potrace not available")
        return False

    if not PIL_AVAILABLE:
        print("   ❌ Pillow not available")
        return False

    try:
        img = Image.open(png_path)
        img_w, img_h = img.size
        print(f"   🖼️ Input image: {img_w}x{img_h} pixels")

        with tempfile.TemporaryDirectory() as tmp:
            bmp_path = os.path.join(tmp, 'input.bmp')
            tmp_svg  = os.path.join(tmp, 'output.svg')

            # Convert PNG → grayscale → threshold → BMP for potrace
            # Important: potrace expects BLACK = foreground (ink), WHITE = background
            # PIL '1' mode can invert or produce wrong BMP - use 'L' grayscale BMP instead
            gray = img.convert('L')
            # Ensure clean black/white threshold
            import numpy as np
            arr = np.array(gray)
            arr = (arr < 128).astype(np.uint8) * 255  # dark pixels → 255
            # For potrace: black (0) = foreground, white (255) = background
            arr_potrace = np.where(arr > 0, 0, 255).astype(np.uint8)
            # PRE-FLIP vertically: BMP stores rows bottom-to-top, causing potrace
            # to add a Y-flip transform. By flipping the image here first,
            # the output needs NO transforms — just like Illustrator SVGs.
            arr_potrace = np.flipud(arr_potrace)
            bw_img = Image.fromarray(arr_potrace, mode='L')
            bw_img.save(bmp_path)
            print(f"   ✅ BMP created for potrace ({bw_img.size[0]}x{bw_img.size[1]})")

            # Run potrace with settings matched to Inkscape defaults
            result = subprocess.run([
                POTRACE_BIN,
                bmp_path,
                '--svg',
                '--alphamax',     '1.0',   # Match Inkscape "Smooth corners: 1"
                '--opttolerance', '0.2',   # Match Inkscape "Optimize: 0.2"
                '--turdsize',     '2',     # Match Inkscape "Speckles: 2"
                '--unit',         '1',
                '-o', tmp_svg
            ], capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                print(f"   ❌ potrace error: {result.stderr}")
                return False

            if not os.path.exists(tmp_svg):
                print("   ❌ potrace did not create output file")
                return False

            print("   ✅ potrace trace complete")

            # Read potrace SVG output
            with open(tmp_svg, 'r', encoding='utf-8') as f:
                svg = f.read()

            print(f"   🔍 Raw potrace SVG size: {len(svg)} bytes")
            print(f"   🔍 Raw SVG first 500 chars:\n{svg[:500]}")

            # OUTPUT FORMAT: match Boxy SVG — width/height in px, viewBox in same units.
            # Path coords rescaled NUMERICALLY to pt. No transforms anywhere.
            # Shapely ignores scale() transforms so scaling must be baked into coords.
            # px_to_pt = 72 / actual_dpi converts pixel coords → pt coords.
            # width/height use px unit with pt numeric value (same as Boxy).

            px_to_pt = 72.0 / actual_dpi
            w_pt = img_w * px_to_pt
            h_pt = img_h * px_to_pt

            # Rescale all numbers in path data from pixels to pt values
            def scale_path_coords(path_data, factor):
                def scale_num(m):
                    val = float(m.group(0))
                    scaled = val * factor
                    if scaled == int(scaled):
                        return str(int(scaled))
                    return f'{scaled:.4f}'
                return re.sub(r'-?\d+\.?\d*', scale_num, path_data)

            svg = re.sub(
                r'd="([^"]+)"',
                lambda m: 'd="' + scale_path_coords(m.group(1), px_to_pt) + '"',
                svg
            )

            # SVG tag: width/height in px, viewBox in pt — matches Boxy format
            svg = re.sub(
                r'<svg[^>]*>',
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{w_pt:.3f}px" height="{h_pt:.3f}px" '
                f'viewBox="0 0 {w_pt:.3f} {h_pt:.3f}">',
                svg
            )
            # Remove all transforms — coords are now final pt values
            svg = re.sub(
                r'<g[^>]*transform="[^"]*"[^>]*>',
                '<g fill="#000000" stroke="none">',
                svg
            )

            # Set fill and fill-rule on paths
            svg = re.sub(r'<path\b([^>]*?)\bfill="[^"]*"', r'<path\1', svg)
            svg = re.sub(r'<path\b', '<path fill="#000000" fill-rule="evenodd" ', svg)

            # Write final SVG
            with open(output_svg_path, 'w', encoding='utf-8') as f:
                f.write(svg)

            # Confirm Bezier curves
            if ' C ' in svg or ' c ' in svg:
                print("   ✅ Bezier curves confirmed in SVG output!")
            else:
                print("   ⚠️  No Bezier curves found - check potrace parameters")

            print(f"   📐 SVG dimensions: {w_pt:.1f}pt x {h_pt:.1f}pt  ({w_pt/72*25.4:.1f}mm x {h_pt/72*25.4:.1f}mm)")
            print(f"   ✅ SVG written: {os.path.getsize(output_svg_path)} bytes")
            return True

    except subprocess.TimeoutExpired:
        print("   ❌ potrace timed out")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def pdf_to_svg_pipeline(pdf_path, output_svg_path=None, dpi=None):
    """
    Complete pipeline: PDF → PNG → SVG via potrace

    Returns:
        tuple: (success, svg_path, png_path, message)
    """
    if not os.path.exists(pdf_path):
        return False, None, None, f"PDF not found: {pdf_path}"

    if output_svg_path is None:
        base = os.path.splitext(pdf_path)[0]
        output_svg_path = f"{base}_vectorized.svg"

    print("🚀 PDF → SVG  (potrace pipeline - PROFESSIONAL)")

    # Step 1: PDF → PNG
    print("📄 Step 1: PDF → PNG bitmap")

    png_filename = os.path.splitext(os.path.basename(output_svg_path))[0] + '.png'
    png_path = os.path.join(os.path.dirname(output_svg_path), png_filename)

    success, actual_dpi, w_cm, h_cm, content_rect = pdf_to_bitmap_png(pdf_path, png_path, dpi)

    if not success:
        return False, None, None, "PDF rasterization failed"

    # Step 2: PNG → SVG via potrace
    print("🎨 Step 2: PNG → SVG via potrace")
    ok = bitmap_to_svg_potrace(png_path, output_svg_path, content_rect, actual_dpi)

    if not ok:
        if os.path.exists(png_path):
            os.unlink(png_path)
        return False, None, None, "potrace vectorization failed"

    print("✅ Pipeline complete!")
    return True, output_svg_path, png_path, "Success"


def main():
    """Command-line interface for testing"""

    print("🚀 PDF PROCESSOR - Potrace Vectorizer (PROFESSIONAL)")
    print("=" * 80)

    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python pdf_processor.py input.pdf [output.svg] [dpi]")
        print("\nExamples:")
        print("  python pdf_processor.py letter.pdf")
        print("  python pdf_processor.py letter.pdf output.svg")
        print("  python pdf_processor.py letter.pdf output.svg 150")
        return

    pdf_path = sys.argv[1]
    output_svg = sys.argv[2] if len(sys.argv) > 2 else None
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else None

    success, svg_path, png_path, msg = pdf_to_svg_pipeline(pdf_path, output_svg, dpi)

    if success:
        print(f"\n✅ SUCCESS: {svg_path}")
        print(f"📁 File size: {os.path.getsize(svg_path)} bytes")
    else:
        print(f"\n❌ FAILED: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
