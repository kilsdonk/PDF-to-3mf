#!/usr/bin/env python3
"""
Hole Processor for Signage Letters
- No red line logic for positioning
- Each letter gets exactly 4 holes: top-left, top-right, bottom-left, bottom-right
- Each hole = thickest black point in that corner zone (30% x 30% of letter rect)
- Red lines only used to identify WHICH letters to process
"""

import fitz
import numpy as np
import cv2

HOLE_DIAMETER_MM = 6.0
HOLE_COLOR       = (0, 200, 0)    # Green
CORNER_ZONE      = 0.30           # 30% of letter width/height per corner
NARROW_RATIO     = 0.88           # letters narrower than 88% of height = T/I type → 3 holes


def is_red(color):
    if color is None:
        return False
    if len(color) >= 3:
        r, g, b = color[0], color[1], color[2]
        return r > 0.5 and g < 0.3 and b < 0.3
    return False


def best_point_in_zone(dist, y0, y1, x0, x1):
    """Find the pixel with highest dist value in the given rectangle. Returns (x, y) in full image coords."""
    zone = dist[y0:y1, x0:x1]
    if zone.size == 0 or zone.max() == 0:
        return None
    idx = np.unravel_index(np.argmax(zone), zone.shape)
    return (x0 + idx[1], y0 + idx[0])  # (x, y)


def get_hole_positions(pdf_path, content_rect=None, dpi=150):
    print(f"   4-corner hole placement | colour: yellow")

    doc = fitz.open(pdf_path)
    page = doc[0]
    page_rect = page.rect
    page_w    = page_rect.width
    page_h    = page_rect.height

    drawings     = page.get_drawings()
    guide_lines  = []
    letter_rects = []

    for d in drawings:
        stroke_color = d.get('color')
        fill_color   = d.get('fill')
        if is_red(stroke_color) and fill_color is None:
            for item in d.get('items', []):
                if item[0] == 'l':
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) < 5:
                        guide_lines.append({
                            'y':  (p1.y + p2.y) / 2,
                            'x0': min(p1.x, p2.x),
                            'x1': max(p1.x, p2.x)
                        })
        elif fill_color is not None:
            r = d.get('rect')
            if r and r.width > 10 and r.height > 10:
                letter_rects.append(r)

    print(f"   {len(guide_lines)} red line(s), {len(letter_rects)} letter rect(s)")

    if not letter_rects:
        doc.close()
        print("   No letter rects found — cannot place holes")
        return [], page_w / 72 * 25.4, page_h / 72 * 25.4

    dpi  = max(dpi, 150)
    zoom = dpi / 72.0
    mat  = fitz.Matrix(zoom, zoom)
    pix  = page.get_pixmap(matrix=mat, clip=page_rect, alpha=False)
    doc.close()

    img      = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    img_h_px, img_w_px = img.shape[:2]
    scale_x  = img_w_px / page_w
    scale_y  = img_h_px / page_h

    r_ch = img[:,:,0].astype(np.float32)
    g_ch = img[:,:,1].astype(np.float32)
    b_ch = img[:,:,2].astype(np.float32)
    is_red_px   = (r_ch > 150) & (g_ch < 100) & (b_ch < 100) & \
                  (r_ch > g_ch * 1.5) & (r_ch > b_ch * 1.5)
    gray        = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    letter_mask = ((gray < 128) & ~is_red_px).astype(np.uint8)
    dist        = cv2.distanceTransform(letter_mask, cv2.DIST_L2, 5)

    hole_positions_mm = []

    for lr in sorted(letter_rects, key=lambda r: r.x0):
        lx0 = max(0, int(lr.x0 * scale_x))
        lx1 = min(img_w_px, int(lr.x1 * scale_x))
        ly0 = max(0, int(lr.y0 * scale_y))
        ly1 = min(img_h_px, int(lr.y1 * scale_y))

        w = lx1 - lx0
        h = ly1 - ly0
        if w < 4 or h < 4:
            continue

        zw = max(4, int(w * CORNER_ZONE))
        zh = max(4, int(h * CORNER_ZONE))

        print(f"   Letter x={lr.x0*25.4/72:.0f}-{lr.x1*25.4/72:.0f}mm")

        # Detect T/I type: check if BOTH bottom corners have black
        # If a bottom corner has no black → narrow letter → 3 holes
        bl_has_black = best_point_in_zone(dist, ly1 - zh, ly1, lx0,      lx0 + zw) is not None
        br_has_black = best_point_in_zone(dist, ly1 - zh, ly1, lx1 - zw, lx1     ) is not None

        if bl_has_black and br_has_black:
            corners = [
                ('top-left',     ly0,      ly0 + zh, lx0,      lx0 + zw),
                ('top-right',    ly0,      ly0 + zh, lx1 - zw, lx1     ),
                ('bottom-left',  ly1 - zh, ly1,      lx0,      lx0 + zw),
                ('bottom-right', ly1 - zh, ly1,      lx1 - zw, lx1     ),
            ]
        else:
            # T/I type — 3 holes: top-left, top-right, bottom-centre
            print(f"     Narrow letter (T/I type) → 3 holes")
            corners = [
                ('top-left',     ly0,      ly0 + zh, lx0,                  lx0 + zw            ),
                ('top-right',    ly0,      ly0 + zh, lx1 - zw,             lx1                 ),
                ('bottom-centre',ly1 - zh, ly1,      lx0 + w//2 - zw//2,  lx0 + w//2 + zw//2  ),
            ]
        for name, zy0, zy1, zx0, zx1 in corners:
            pt = best_point_in_zone(dist, zy0, zy1, zx0, zx1)
            # If no black in corner zone, expand zone inward (wider/taller) until found
            if pt is None:
                for expand in [0.40, 0.50, 0.60, 0.70, 0.80]:
                    ezw = max(4, int(w * expand))
                    ezh = max(4, int(h * expand))
                    if 'left' in name:
                        ex0, ex1 = lx0, lx0 + ezw
                    else:
                        ex0, ex1 = lx1 - ezw, lx1
                    if 'top' in name:
                        ey0, ey1 = ly0, ly0 + ezh
                    else:
                        ey0, ey1 = ly1 - ezh, ly1
                    pt = best_point_in_zone(dist, ey0, ey1, ex0, ex1)
                    if pt is not None:
                        break
            if pt is None:
                print(f"     {name}: no black found")
                continue
            hole_x_mm = pt[0] / scale_x / 72 * 25.4
            hole_y_mm = pt[1] / scale_y / 72 * 25.4
            hole_positions_mm.append((hole_x_mm, hole_y_mm))
            print(f"     {name}: ({hole_x_mm:.1f}mm, {hole_y_mm:.1f}mm)")

    print(f"   Total holes: {len(hole_positions_mm)}")
    return hole_positions_mm, page_w / 72 * 25.4, page_h / 72 * 25.4
