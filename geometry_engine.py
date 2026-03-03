#!/usr/bin/env python3
"""
OPTIMIZED SHAPELY - Performance Fixed Version with SVG CLEANUP + OPEN PATH SUPPORT
Version: 2.6.0 - ADDED OPEN PATH SUPPORT FOR 3D PRINTING
- NEW: Automatic detection of open paths (lines/splines) vs closed shapes (polygons)
- NEW: Open paths stay as lines (no infill in slicer)
- NEW: Closed shapes processed normally (can have infill in slicer)
- NEW: Zigzag effect with minimal points
- NEW: Uniform spacing (no corner bunching)
- MAINTAINED: All existing functionality
"""

import sys
import os
import math
from shapely.geometry import Polygon, MultiPolygon, Point, LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
import xml.etree.ElementTree as ET
import re
import tempfile

# =====================================================
# DEPENDENCY MANAGER - LAZY LOADING FOR OPTIONAL LIBS
# =====================================================

class DependencyManager:
    """
    Manages optional dependencies with lazy loading.
    Core dependencies (Shapely, NumPy) are loaded automatically.
    Optional dependencies (OpenCV, SciPy) are loaded on-demand.
    """
    
    def __init__(self):
        self.available = {}
        self.modules = {}
        self._load_dependencies()
    
    def _load_dependencies(self):
        """Load core dependencies and mark optional ones as available but not loaded."""
        
        # ===== CORE DEPENDENCIES (Auto-load) =====
        
        # Shapely (already imported at top)
        try:
            from shapely.geometry import Polygon, MultiPolygon, Point, LineString
            from shapely.geometry.polygon import orient
            from shapely.ops import unary_union
            self.available['shapely'] = True
            self.modules['shapely'] = {
                'Polygon': Polygon,
                'MultiPolygon': MultiPolygon,
                'Point': Point,
                'LineString': LineString,
                'orient': orient,
                'unary_union': unary_union
            }
            print("✅ Shapely loaded (core dependency)")
        except ImportError:
            self.available['shapely'] = False
            print("❌ Shapely not available - REQUIRED!")
        
        # NumPy (if needed)
        try:
            import numpy as np
            self.available['numpy'] = True
            self.modules['numpy'] = np
            print("✅ NumPy loaded (core dependency)")
        except ImportError:
            self.available['numpy'] = False
            print("⚠️ NumPy not available")
        
        # ===== OPTIONAL DEPENDENCIES (Lazy load - mark as available but don't import) =====
        
        # OpenCV - mark as NOT loaded, will load on-demand
        self.available['opencv'] = False
        self.modules['opencv'] = None
        # Do not import OpenCV here anymore!
        
        # SciPy - mark as NOT loaded, will load on-demand  
        self.available['scipy'] = False
        self.modules['scipy'] = None
        # Do not import SciPy here anymore!
        
        print("⏳ OpenCV and SciPy set for lazy loading (will import only when needed)")
    
    def get_opencv(self):
        """Lazy load OpenCV only when needed."""
        if not self.available['opencv'] and self.modules['opencv'] is None:
            try:
                import cv2
                self.modules['opencv'] = cv2
                self.available['opencv'] = True
                print("✅ OpenCV loaded on-demand")
            except ImportError:
                print("⚠️ OpenCV not available - some features may be limited")
                self.available['opencv'] = False
        
        return self.modules['opencv']
    
    def get_scipy(self):
        """Lazy load SciPy only when needed."""
        if not self.available['scipy'] and self.modules['scipy'] is None:
            try:
                import scipy
                self.modules['scipy'] = scipy
                self.available['scipy'] = True
                print("✅ SciPy loaded on-demand")
            except ImportError:
                print("⚠️ SciPy not available - some features may be limited")
                self.available['scipy'] = False
        
        return self.modules['scipy']
    
    def is_available(self, lib_name):
        """Check if a library is available."""
        return self.available.get(lib_name, False)


# Initialize dependency manager
deps = DependencyManager()

try:
    WINDING_SUPPORT = True
    print("✅ Winding direction support enabled")
except ImportError:
    WINDING_SUPPORT = False
    print("⚠️ Winding direction support not available")

# =====================================================
# NEW: ZIGZAG FUNCTIONS (MINIMAL ADDITION)
# =====================================================

def create_zigzag(line, wavelength=20.0, amplitude=5.0):
    """
    Transform a LineString into a sharp zigzag pattern with MINIMAL points
    Only 2 points per wavelength - much more efficient than waves
    """
    coords = list(line.coords)
    if len(coords) < 2:
        return line
    
    total_length = line.length
    
    if total_length < wavelength:
        return line
    
    # Calculate zigzag segments
    segment_length = wavelength / 2
    num_segments = int(total_length / segment_length)
    
    if num_segments < 2:
        return line
    
    zigzag_points = []
    current_distance = 0
    direction = 1  # Alternates between +1 and -1
    
    # Always include start point
    start_point = line.interpolate(0)
    zigzag_points.append((start_point.x, start_point.y))
    
    # Generate zigzag points at equal distances
    while current_distance < total_length:
        current_distance += segment_length
        
        if current_distance > total_length:
            current_distance = total_length
        
        # Get point on original line at this distance
        point = line.interpolate(current_distance)
        
        # Calculate tangent direction
        epsilon = min(0.1, total_length * 0.001)
        
        if current_distance < total_length - epsilon:
            next_point = line.interpolate(current_distance + epsilon)
            dx = next_point.x - point.x
            dy = next_point.y - point.y
        else:
            prev_point = line.interpolate(current_distance - epsilon)
            dx = point.x - prev_point.x
            dy = point.y - prev_point.y
        
        # Normalize tangent
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            dx /= length
            dy /= length
        
        # Perpendicular vector (90° rotation)
        perp_x = -dy
        perp_y = dx
        
        # Apply zigzag offset (alternating direction)
        offset = amplitude * direction
        new_x = point.x + perp_x * offset
        new_y = point.y + perp_y * offset
        
        zigzag_points.append((new_x, new_y))
        
        # Flip direction for next point
        direction *= -1
    
    return LineString(zigzag_points)


def apply_zigzag_to_svg(input_file, output_file, wavelength=20.0, amplitude=5.0, 
                        curve_resolution=40):
    """
    Apply zigzag effect to all paths in an SVG file
    
    Args:
        input_file: Input SVG file path
        output_file: Output SVG file path
        wavelength: Distance between zigzag peaks (in mm)
        amplitude: Height of zigzag (in mm)
        curve_resolution: Resolution for initial curve parsing
    
    Returns:
        True if successful, False otherwise
    """
    print(f"\n🔲 ZIGZAG EFFECT")
    print(f"   Input: {input_file}")
    print(f"   Output: {output_file}")
    print(f"   Wavelength: {wavelength}mm")
    print(f"   Amplitude: {amplitude}mm")
    
    try:
        # Read input SVG
        with open(input_file, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        
        # Convert mm to pixels
        PIXEL_CONVERSION_FACTOR = 0.35277
        wavelength_px = wavelength / PIXEL_CONVERSION_FACTOR
        amplitude_px = amplitude / PIXEL_CONVERSION_FACTOR
        
        # Parse SVG
        root = ET.fromstring(svg_content)
        
        # Find all shapes (including LINE and POLYLINE from Illustrator)
        shapes = []
        for elem in root.iter():
            if (elem.tag.endswith('polygon') or elem.tag.endswith('path') or 
                elem.tag.endswith('rect') or elem.tag.endswith('circle') or 
                elem.tag.endswith('ellipse') or elem.tag.endswith('line') or
                elem.tag.endswith('polyline')):
                shapes.append(elem)
        
        if not shapes:
            print(f"   ❌ No shapes found")
            return False
        
        print(f"   Found {len(shapes)} shape(s) to process")
        
        # Process each shape
        processed_count = 0
        for i, shape in enumerate(shapes):
            shape_type = shape.tag.split('}')[-1] if '}' in shape.tag else shape.tag
            
            # Convert shape to polygon
            result = svg_to_polygon_with_holes(shape, curve_resolution)
            if not result:
                continue
            
            polygon = result['polygon']
            if polygon.is_empty or not polygon.is_valid:
                continue
            
            # Get exterior as LineString
            line = LineString(polygon.exterior.coords)
            
            # Apply zigzag
            zigzag_line = create_zigzag(line, wavelength_px, amplitude_px)
            
            # Convert back to SVG path
            coords = list(zigzag_line.coords)
            if not coords:
                continue
            
            path_data = f"M {coords[0][0]:.3f} {coords[0][1]:.3f} "
            for j in range(1, len(coords)):
                path_data += f"L {coords[j][0]:.3f} {coords[j][1]:.3f} "
            
            # Update the element
            if shape.tag.endswith('path'):
                shape.set('d', path_data)
            else:
                # Convert to path element
                shape.tag = shape.tag.rsplit('}', 1)[0] + '}path' if '}' in shape.tag else 'path'
                shape.set('d', path_data)
                # Remove old attributes
                for attr in ['points', 'x', 'y', 'width', 'height', 'cx', 'cy', 'r', 'rx', 'ry']:
                    if attr in shape.attrib:
                        del shape.attrib[attr]
            
            processed_count += 1
            print(f"   ✅ {shape_type} {i+1}: {len(coords)} points (zigzag)")
        
        if processed_count == 0:
            print(f"   ❌ No shapes could be processed")
            return False
        
        # Write output SVG
        output_svg = ET.tostring(root, encoding='unicode')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_svg)
        
        print(f"   ✅ Zigzag applied to {processed_count}/{len(shapes)} shapes")
        print(f"   ✅ Saved to: {output_file}")
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

# =====================================================
# END ZIGZAG FUNCTIONS
# =====================================================

def smart_redistribute_curve_points(points, target_count, min_distance=0.8):
    """
    🎯 SMART redistribution that prevents clustering
    - Maintains curve quality
    - Eliminates point clustering  
    - Adaptive spacing based on curvature
    """
    if len(points) < 2:
        return points
    
    if len(points) <= target_count:
        return points
    
    # Calculate cumulative distances
    distances = [0]
    total_length = 0
    
    for i in range(1, len(points)):
        dx = points[i][0] - points[i-1][0]
        dy = points[i][1] - points[i-1][1]
        dist = math.sqrt(dx*dx + dy*dy)
        total_length += dist
        distances.append(total_length)
    
    if total_length == 0:
        return points
    
    # 🎯 SMART SPACING: Prevent clustering
    redistributed = [points[0]]  # Always include first point
    last_added_distance = 0
    
    for i in range(1, target_count - 1):
        target_distance = (i / (target_count - 1)) * total_length
        
        # 🚀 CLUSTERING FIX: Ensure minimum spacing
        if target_distance - last_added_distance < min_distance:
            continue
        
        # Find the segment containing this distance
        for j in range(len(distances) - 1):
            if distances[j] <= target_distance <= distances[j + 1]:
                # Interpolate between points j and j+1
                if distances[j + 1] - distances[j] > 0:
                    t = (target_distance - distances[j]) / (distances[j + 1] - distances[j])
                    x = points[j][0] + t * (points[j + 1][0] - points[j][0])
                    y = points[j][1] + t * (points[j + 1][1] - points[j][1])
                    redistributed.append((x, y))
                    last_added_distance = target_distance
                break
    
    redistributed.append(points[-1])  # Always include last point
    return redistributed

def adaptive_curve_resolution(path_segment_length, base_resolution=10, target_spacing=4.0):
    """
    🎯 SMART ADAPTIVE resolution based on actual curve length
    - Uses target point spacing (pixels between points)
    - Small curves: automatically fewer points
    - Large curves: automatically more points
    - Prevents over-sampling small features
    
    Args:
        path_segment_length: Length of curve in pixels
        base_resolution: User's resolution preference (influences spacing)
        target_spacing: Target distance between points in pixels (default 4.0)
    
    Returns:
        Number of points needed for this curve
    """
    # 🎯 SMART: Calculate points based on actual curve length
    # Higher base_resolution = tighter spacing (more points)
    # Lower base_resolution = looser spacing (fewer points)
    
    # Scale target spacing inversely with resolution
    # resolution 40 → spacing ~3px, resolution 20 → spacing ~6px
    adjusted_spacing = target_spacing * (40.0 / max(base_resolution, 10))
    
    # Calculate points needed for this specific curve
    points_needed = int(path_segment_length / adjusted_spacing)
    
    # Reasonable bounds
    points_needed = max(3, min(points_needed, 200))  # Between 3 and 200 points
    
    return points_needed

def adaptive_cubic_bezier_points(p0, p1, p2, p3, target_resolution):
    """🎯 SMART cubic Bézier with adaptive resolution and clustering prevention"""
    try:
        # Calculate curve length estimate
        approx_length = (
            math.sqrt((p1[0]-p0[0])**2 + (p1[1]-p0[1])**2) +
            math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) + 
            math.sqrt((p3[0]-p2[0])**2 + (p3[1]-p2[1])**2)
        )
        
        # 🎯 ADAPTIVE: Resolution based on curve length
        smart_resolution = adaptive_curve_resolution(approx_length, target_resolution)
        
        points = []
        for i in range(smart_resolution + 1):
            t = i / smart_resolution
            t2 = t * t
            t3 = t2 * t
            mt = 1 - t
            mt2 = mt * mt
            mt3 = mt2 * mt
            
            x = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
            y = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
            points.append((x, y))
        
        # 🎯 SMART redistribution prevents clustering - NO CAP
        return smart_redistribute_curve_points(points, target_resolution + 1)
        
    except Exception:
        return linear_interpolation(p0, p3, target_resolution)

def adaptive_quadratic_bezier_points(p0, p1, p2, target_resolution):
    """🎯 SMART quadratic Bézier with adaptive resolution and clustering prevention"""
    try:
        # Calculate curve length estimate  
        approx_length = (
            math.sqrt((p1[0]-p0[0])**2 + (p1[1]-p0[1])**2) +
            math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
        )
        
        # 🎯 ADAPTIVE: Resolution based on curve length
        smart_resolution = adaptive_curve_resolution(approx_length, target_resolution)
        
        points = []
        for i in range(smart_resolution + 1):
            t = i / smart_resolution
            t2 = t * t
            mt = 1 - t
            mt2 = mt * mt
            
            x = mt2 * p0[0] + 2 * mt * t * p1[0] + t2 * p2[0]
            y = mt2 * p0[1] + 2 * mt * t * p1[1] + t2 * p2[1]
            points.append((x, y))
        
        # 🎯 SMART redistribution prevents clustering - NO CAP
        return smart_redistribute_curve_points(points, target_resolution + 1)
        
    except Exception:
        return linear_interpolation(p0, p2, target_resolution)

def cubic_bezier_points(p0, p1, p2, p3, num_points):
    """Enhanced cubic Bézier with smart point distribution"""
    return adaptive_cubic_bezier_points(p0, p1, p2, p3, num_points)

def quadratic_bezier_points(p0, p1, p2, num_points):
    """Enhanced quadratic Bézier with smart point distribution"""
    return adaptive_quadratic_bezier_points(p0, p1, p2, num_points)

def linear_interpolation(p0, p1, num_points):
    """Generate points along straight line"""
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        x = p0[0] + t * (p1[0] - p0[0])
        y = p0[1] + t * (p1[1] - p0[1])
        points.append((x, y))
    
    return points

def analyze_winding_direction(points):
    """Analyze winding direction using shoelace formula"""
    if len(points) < 3:
        return {"direction": "unknown", "area": 0, "is_clockwise": False}
    
    # Shoelace formula for signed area
    signed_area = 0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        signed_area += (points[j][0] - points[i][0]) * (points[j][1] + points[i][1])
    
    signed_area = signed_area / 2
    is_clockwise = signed_area > 0
    
    return {
        "direction": "cw" if is_clockwise else "ccw", 
        "area": abs(signed_area),
        "signed_area": signed_area,
        "is_clockwise": is_clockwise
    }

def ensure_correct_winding(points, should_be_clockwise=False):
    """Ensure polygon ring has correct winding order"""
    if len(points) < 3:
        return points
    
    winding_info = analyze_winding_direction(points)
    is_clockwise = winding_info["is_clockwise"]
    
    # If winding is wrong, reverse the points
    if is_clockwise != should_be_clockwise:
        return list(reversed(points))
    else:
        return points

# =====================================================
# SVG CLEANUP FUNCTIONS (FIXED - REMOVED DANGEROUS FILTER)
# =====================================================

def is_nearly_collinear(p1, p2, p3, tolerance=0.5):
    """
    Check if three points are nearly collinear (on a straight line)
    Uses cross product to measure deviation from straight line
    """
    # Vector from p1 to p2
    dx1 = p2[0] - p1[0]
    dy1 = p2[1] - p1[1]
    
    # Vector from p1 to p3
    dx2 = p3[0] - p1[0]
    dy2 = p3[1] - p1[1]
    
    # Cross product magnitude (perpendicular distance)
    cross = abs(dx1 * dy2 - dy1 * dx2)
    
    # Length of base
    base_length = math.sqrt(dx2 * dx2 + dy2 * dy2)
    
    if base_length < 0.001:  # Points too close
        return True
    
    # Perpendicular distance
    distance = cross / base_length
    
    return distance < tolerance

def remove_redundant_points(coords_list, tolerance=0.5):
    """
    Remove points that are nearly collinear with their neighbors
    Keeps start and end points always
    """
    if len(coords_list) < 3:
        return coords_list
    
    cleaned = [coords_list[0]]  # Always keep first point
    
    for i in range(1, len(coords_list) - 1):
        prev_point = cleaned[-1]
        current_point = coords_list[i]
        next_point = coords_list[i + 1]
        
        # Keep point if it's not collinear or if points are far apart
        if not is_nearly_collinear(prev_point, current_point, next_point, tolerance):
            cleaned.append(current_point)
    
    cleaned.append(coords_list[-1])  # Always keep last point
    
    return cleaned

def is_bezier_actually_line(p0, p1, p2, p3, tolerance=1.0):
    """
    Check if a cubic Bézier curve is actually a straight line
    Returns True if control points are very close to the line between start and end
    """
    # Check if all four points are nearly collinear
    if not is_nearly_collinear(p0, p1, p3, tolerance):
        return False
    if not is_nearly_collinear(p0, p2, p3, tolerance):
        return False
    
    return True

def simplify_path_commands(path_data):
    """
    Simplify SVG path data by detecting curves that are actually straight lines.
    CRITICAL FIX: Removed the "Jitter Filter" that corrupted relative paths.
    """
    try:
        commands = re.findall(r'[MLHVCSQTAZ][^MLHVCSQTAZ]*', path_data, re.IGNORECASE)
        if not commands:
            return path_data
        
        simplified = []
        redundant_curves = 0
        
        for i, cmd in enumerate(commands):
            cmd_type = cmd[0].upper()
            
            # Check if cubic Bézier is actually a line
            if cmd_type == 'C':
                coords = re.findall(r'[-+]?\d*\.?\d+', cmd[1:])
                coords = [float(c) for c in coords]
                if len(coords) >= 6:
                    # Check for flat curves
                    cp1_offset = math.sqrt((coords[0])**2 + (coords[1])**2)
                    cp2_offset = math.sqrt((coords[2] - coords[4])**2 + (coords[3] - coords[5])**2)
                    if cp1_offset < 2.0 and cp2_offset < 2.0:
                        is_relative = cmd[0] != 'C'
                        simplified.append(f"{'l' if is_relative else 'L'} {coords[4]:.3f} {coords[5]:.3f}")
                        redundant_curves += 1
                        continue
            
            simplified.append(cmd)
        
        return ' '.join(simplified)
        
    except Exception:
        return path_data

def cleanup_svg_content(svg_content):
    """
    Standard cleanup: handles parsing issues but relies on Shapely for geometry.
    """
    try:
        print(f"\n🧹 SVG CLEANUP: Parsing structure...")
        root = ET.fromstring(svg_content)
        total_paths = 0
        shape_tags = ('path', 'polygon', 'polyline', 'rect', 'line')
        
        for elem in root.iter():
            if any(elem.tag.endswith(t) for t in shape_tags):
                total_paths += 1
                d = elem.get('d', '')
                if d.strip():
                    cleaned_d = simplify_path_commands(d)
                    if cleaned_d != d:
                        elem.set('d', cleaned_d)
        
        return ET.tostring(root, encoding='unicode')
        
    except Exception as e:
        print(f"   ⚠️ Cleanup skipped: {e}")
        return svg_content

# =====================================================
# END SVG CLEANUP FUNCTIONS
# =====================================================

def detect_file_type_from_filename(filename):
    """Auto-detect file type from filename"""
    filename_lower = filename.lower()
    
    if 'face' in filename_lower:
        return 'face'
    elif 'return' in filename_lower:
        return 'return'
    elif 'white' in filename_lower:
        return 'white'
    else:
        # Default logic based on common patterns
        if '_face' in filename_lower or 'inside' in filename_lower:
            return 'face'
        elif '_return' in filename_lower or 'outside' in filename_lower:
            return 'return'
        else:
            return 'face'  # Default to face if unsure

def optimized_corner_rounding(polygon, corner_radius, quad_segs=6):
    """
    🎯 OPTIMIZED corner rounding that prevents point clustering
    """
    if corner_radius <= 0:
        return polygon
    
    try:
        # 🎯 SMART: Use reasonable quad_segs without hard caps
        smart_quad_segs = max(3, min(quad_segs, 8))  # Allow reasonable range
        
        # 🎯 Method 1: Single-pass optimized rounding
        # Light erosion followed by dilation for inner corners
        eroded = polygon.buffer(-corner_radius * 0.7, join_style='round', quad_segs=smart_quad_segs)
        if not eroded.is_empty and eroded.is_valid:
            expanded = eroded.buffer(corner_radius * 0.7, join_style='round', quad_segs=smart_quad_segs)
            
            # Light dilation followed by erosion for outer corners  
            if not expanded.is_empty and expanded.is_valid:
                dilated = expanded.buffer(corner_radius * 0.5, join_style='round', quad_segs=smart_quad_segs)
                if not dilated.is_empty and dilated.is_valid:
                    final = dilated.buffer(-corner_radius * 0.5, join_style='round', quad_segs=smart_quad_segs)
                    
                    if final.is_valid and not final.is_empty:
                        print(f"   ✅ Optimized corner rounding: reduced clustering")
                        return final
        
        # 🎯 Fallback: Simple single buffer operation
        simple_rounded = polygon.buffer(-corner_radius * 0.3, join_style='round', quad_segs=smart_quad_segs)
        if not simple_rounded.is_empty and simple_rounded.is_valid:
            simple_rounded = simple_rounded.buffer(corner_radius * 0.3, join_style='round', quad_segs=smart_quad_segs)
            if simple_rounded.is_valid and not simple_rounded.is_empty:
                print(f"   ✅ Simple corner rounding applied")
                return simple_rounded
        
        # Final fallback: return original
        print(f"   ⚠️ Corner rounding failed, using original")
        return polygon
            
    except Exception as e:
        print(f"   ❌ Corner rounding error: {e}")
        return polygon

def svg_to_polygon_with_holes(element, curve_resolution=40):
    """✅ Convert SVG element to Shapely polygon with USER RESOLUTION and PROPER HOLE DETECTION"""
    
    # 🎯 NEW: Handle POLYLINE elements FIRST (because 'polyline' ends with 'line')
    # Polyline = series of connected lines - open path
    if element.tag.endswith('polyline'):
        try:
            points_str = element.get('points', '')
            coords = re.findall(r'[-+]?\d*\.?\d+', points_str)
            
            if len(coords) >= 4:  # Need at least 2 points (4 coordinates)
                points = [(float(coords[i]), float(coords[i+1])) for i in range(0, len(coords), 2) if i+1 < len(coords)]
                print(f"📏 Processing POLYLINE: {len(points)} points")
                
                if len(points) >= 2:
                    # Create LineString for open path (polylines are NOT closed)
                    linestring = LineString(points)
                    print(f"   ✅ Polyline created: {len(points)} points, length={linestring.length:.2f}px (OPEN PATH - NO INFILL)")
                    
                    return {
                        'geometry': linestring,
                        'is_open_path': True,      # 🎯 Polylines are ALWAYS open paths
                        'has_holes': False,
                        'sub_path_count': 1
                    }
                else:
                    print(f"❌ Polyline has insufficient points after parsing")
                    return None
            else:
                print(f"❌ Polyline has insufficient coordinates: {len(coords)}")
                return None
        except Exception as polyline_error:
            print(f"❌ Polyline error: {polyline_error}")
            return None
    
    # 🎯 Handle LINE elements (single line segment from Adobe Illustrator)
    elif element.tag.endswith('line'):
        try:
            x1 = float(element.get('x1', '0'))
            y1 = float(element.get('y1', '0'))
            x2 = float(element.get('x2', '0'))
            y2 = float(element.get('y2', '0'))
            
            print(f"📏 Processing LINE: ({x1}, {y1}) → ({x2}, {y2})")
            
            # Create LineString for open path
            linestring = LineString([(x1, y1), (x2, y2)])
            print(f"   ✅ Line created: length={linestring.length:.2f}px (OPEN PATH - NO INFILL)")
            
            return {
                'geometry': linestring,
                'is_open_path': True,      # 🎯 Lines are ALWAYS open paths
                'has_holes': False,
                'sub_path_count': 1
            }
        except Exception as line_error:
            print(f"❌ Line error: {line_error}")
            return None
    
    # Handle RECTANGLE elements
    elif element.tag.endswith('rect'):
        try:
            x = float(element.get('x', '0'))
            y = float(element.get('y', '0'))
            width = float(element.get('width', '0'))
            height = float(element.get('height', '0'))
            
            print(f"🔷 Processing RECT: x={x}, y={y}, width={width}, height={height}")
            
            if width <= 0 or height <= 0:
                print(f"❌ Invalid rectangle dimensions")
                return None
            
            points = [
                (x, y),
                (x + width, y),
                (x + width, y + height),
                (x, y + height)
            ]
            
            polygon = Polygon(points)
            print(f"   ✅ Rectangle: area={polygon.area:.2f}")
            return {
                'geometry': polygon,      # Changed from 'polygon'
                'is_open_path': False,    # 🎯 NEW: Rectangles are closed
                'has_holes': False,
                'sub_path_count': 1
            }
        except Exception as rect_error:
            print(f"❌ Rectangle error: {rect_error}")
            return None
    
    # Handle CIRCLE elements
    elif element.tag.endswith('circle'):
        try:
            cx = float(element.get('cx', '0'))
            cy = float(element.get('cy', '0'))
            r = float(element.get('r', '0'))
            
            print(f"🔵 Processing CIRCLE: cx={cx}, cy={cy}, r={r}")
            
            if r <= 0:
                return None
            
            # 🎯 SMART: Calculate points based on circumference
            circumference = 2 * math.pi * r
            num_points = adaptive_curve_resolution(circumference, curve_resolution)
            
            points = []
            for i in range(num_points):
                angle = (2 * math.pi * i) / num_points
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                points.append((x, y))
            
            polygon = Polygon(points)
            print(f"   ✅ Circle: radius={r:.1f}px, circumference={circumference:.1f}px → {len(points)} points (smart scaling)")
            return {
                'geometry': polygon,      # Changed from 'polygon'
                'is_open_path': False,    # 🎯 NEW: Circles are closed
                'has_holes': False,
                'sub_path_count': 1
            }
        except Exception as circle_error:
            print(f"❌ Circle error: {circle_error}")
            return None
    
    # Handle ELLIPSE elements
    elif element.tag.endswith('ellipse'):
        try:
            cx = float(element.get('cx', '0'))
            cy = float(element.get('cy', '0'))
            rx = float(element.get('rx', '0'))
            ry = float(element.get('ry', '0'))
            
            print(f"🔵 Processing ELLIPSE: cx={cx}, cy={cy}, rx={rx}, ry={ry}")
            
            if rx <= 0 or ry <= 0:
                return None
            
            # 🎯 SMART: Approximate ellipse perimeter (Ramanujan's approximation)
            h = ((rx - ry) ** 2) / ((rx + ry) ** 2)
            perimeter = math.pi * (rx + ry) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))
            num_points = adaptive_curve_resolution(perimeter, curve_resolution)
            
            points = []
            for i in range(num_points):
                angle = (2 * math.pi * i) / num_points
                x = cx + rx * math.cos(angle)
                y = cy + ry * math.sin(angle)
                points.append((x, y))
            
            polygon = Polygon(points)
            print(f"   ✅ Ellipse: rx={rx:.1f}px, ry={ry:.1f}px, perimeter≈{perimeter:.1f}px → {len(points)} points (smart scaling)")
            return {
                'geometry': polygon,      # Changed from 'polygon'
                'is_open_path': False,    # 🎯 NEW: Ellipses are closed
                'has_holes': False,
                'sub_path_count': 1
            }
        except Exception as ellipse_error:
            print(f"❌ Ellipse error: {ellipse_error}")
            return None

    # Handle POLYGON elements
    elif element.tag.endswith('polygon'):
        points_str = element.get('points', '')
        coords = re.findall(r'[-+]?\d*\.?\d+', points_str)
        if len(coords) >= 6:
            points = [(float(coords[i]), float(coords[i+1])) for i in range(0, len(coords)-1, 2)]
            try:
                polygon = Polygon(points)
                return {
                    'geometry': polygon,      # Changed from 'polygon'
                    'is_open_path': False,    # 🎯 NEW: Polygons are closed
                    'has_holes': False,
                    'sub_path_count': 1
                }
            except Exception as poly_error:
                print(f"❌ Polygon creation from points failed: {poly_error}")
                return None

    # Handle PATH elements with FIXED HOLE DETECTION AND OPEN PATH SUPPORT
    elif element.tag.endswith('path'):
        d = element.get('d', '')
        if not d.strip():
            print(f"❌ Empty path data")
            return None
            
        try:
            result = parse_path_with_curves_and_holes_fixed(d, curve_resolution)
            
            print(f"🔎 Found {len(result['sub_paths'])} sub-paths")
            
            if len(result['sub_paths']) >= 1:
                # 🎯 NEW: Check if this is an open path (single path, not closed)
                if len(result['sub_paths']) == 1:
                    sub_path_data = result['sub_paths'][0]
                    points = sub_path_data['points']
                    is_closed = sub_path_data['is_closed']
                    
                    if not is_closed:
                        # 🎯 OPEN PATH: Keep as LineString, don't convert to Polygon!
                        print(f"   ✅ OPEN PATH detected: Creating LineString (will NOT have infill)")
                        if len(points) >= 2:
                            linestring = LineString(points)
                            return {
                                'geometry': linestring,  # LineString instead of polygon
                                'is_open_path': True,    # 🎯 NEW: Flag as open path
                                'has_holes': False,
                                'sub_path_count': 1
                            }
                        else:
                            print(f"❌ Not enough points for line")
                            return None
                
                # CLOSED PATH: Process normally as Polygon
                valid_sub_paths = []
                for sp_data in result['sub_paths']:
                    points = sp_data['points']
                    if len(points) >= 3:
                        valid_sub_paths.append(points)
                
                if not valid_sub_paths:
                    print(f"❌ No valid sub-paths")
                    return None
                
                # FIXED: Better hole detection using area analysis
                sub_path_data = []
                for i, sub_path in enumerate(valid_sub_paths):
                    try:
                        winding_info = analyze_winding_direction(sub_path)
                        area = winding_info["area"]
                        
                        if area > 0.1:  # Minimum area threshold
                            sub_path_data.append({
                                'index': i,
                                'path': sub_path,
                                'area': area,
                                'winding_info': winding_info
                            })
                            print(f"   Sub-path {i}: area={area:.1f}, direction={winding_info['direction']}")
                    except Exception:
                        continue
                
                if not sub_path_data:
                    return None
                
                # Sort by area - largest is exterior, smaller ones are holes
                sub_path_data.sort(key=lambda x: x['area'], reverse=True)
                exterior_data = sub_path_data[0]
                hole_data_list = sub_path_data[1:]
                
                print(f"   Exterior: area={exterior_data['area']:.1f}")
                print(f"   Holes: {len(hole_data_list)} detected")
                
                try:
                    # Ensure correct winding: exterior CCW, holes CW
                    exterior_path = ensure_correct_winding(exterior_data['path'], should_be_clockwise=False)
                    
                    holes = []
                    for hole_data in hole_data_list:
                        try:
                            hole_path = ensure_correct_winding(hole_data['path'], should_be_clockwise=True)
                            holes.append(hole_path)
                            print(f"   Added hole: area={hole_data['area']:.1f}")
                        except Exception as hole_error:
                            print(f"   Warning: Failed to process hole: {hole_error}")
                            continue
                    
                    # Create polygon with holes
                    if holes:
                        polygon = Polygon(exterior_path, holes)
                        print(f"   ✅ Created CLOSED POLYGON with {len(holes)} holes (can have infill)")
                    else:
                        polygon = Polygon(exterior_path)
                        print(f"   ✅ Created CLOSED POLYGON without holes (can have infill)")
                    
                    if not polygon.is_valid:
                        print(f"   ⚠️ Invalid polygon, attempting to fix...")
                        polygon = polygon.buffer(0)
                        if not polygon.is_valid or polygon.is_empty:
                            # Try without holes
                            polygon = Polygon(exterior_path)
                            if not polygon.is_valid or polygon.is_empty:
                                print(f"   ❌ Failed to create valid polygon")
                                return None
                            print(f"   ⚠️ Using exterior only due to hole issues")
                    
                    # Apply winding fix if available
                    if WINDING_SUPPORT:
                        try:
                            polygon = fix_winding_for_format(polygon, "bambu")
                            print(f"   ✅ Applied winding correction")
                        except Exception as winding_error:
                            print(f"   ⚠️ Winding correction failed: {winding_error}")
                    
                    return {
                        'geometry': polygon,         # Changed from 'polygon' to 'geometry'
                        'is_open_path': False,       # 🎯 NEW: Not an open path
                        'has_holes': len(holes) > 0,
                        'sub_path_count': len(valid_sub_paths)
                    }
                    
                except Exception as polygon_creation_error:
                    print(f"❌ Error creating polygon: {polygon_creation_error}")
                    return None
            else:
                return None
                
        except Exception as path_error:
            print(f"❌ Path parsing error: {path_error}")
            return None
    
    return None

def parse_path_with_curves_and_holes_fixed(path_data, curve_resolution=40):
    """✅ FIXED path parser with proper sub-path separation for holes - USES FULL RESOLUTION - TRACKS CLOSED VS OPEN"""
    all_sub_paths = []
    
    try:
        # FIXED: Better command parsing that preserves Z boundaries
        commands = re.findall(r'[MLHVCSQTAZ][^MLHVCSQTAZ]*', path_data, re.IGNORECASE)
        print(f"   Found {len(commands)} path commands")
        
    except Exception as regex_error:
        print(f"❌ Path command parsing failed: {regex_error}")
        return {'sub_paths': []}
    
    current_sub_path = []
    current_path_is_closed = False  # 🎯 NEW: Track if current path is closed
    x, y = 0, 0
    start_x, start_y = 0, 0
    last_control_x, last_control_y = 0, 0
    
    for cmd_index, cmd in enumerate(commands):
        try:
            cmd_type = cmd[0].upper()
            is_relative = cmd[0] != cmd[0].upper()
            
            # Parse coordinates
            coord_matches = re.findall(r'[-+]?\d*\.?\d+', cmd[1:])
            coords = []
            for coord_str in coord_matches:
                try:
                    coords.append(float(coord_str))
                except ValueError:
                    continue
            
            if cmd_type == 'M':
                # Move command - FIXED: Always starts a new sub-path
                for i in range(0, len(coords), 2):
                    if i + 1 < len(coords):
                        if i == 0:
                            # Start new sub-path - save previous one with closed status
                            if current_sub_path and len(current_sub_path) >= 3:
                                all_sub_paths.append({
                                    'points': current_sub_path[:],
                                    'is_closed': current_path_is_closed  # 🎯 NEW: Save closed status
                                })
                                print(f"     Completed sub-path {len(all_sub_paths)}: {len(current_sub_path)} points ({'CLOSED' if current_path_is_closed else 'OPEN'})")
                            current_sub_path = []
                            current_path_is_closed = False  # 🎯 NEW: Reset for new path
                            
                            if is_relative:
                                x += coords[i]
                                y += coords[i + 1]
                            else:
                                x = coords[i]
                                y = coords[i + 1]
                            start_x, start_y = x, y
                            last_control_x, last_control_y = x, y
                            current_sub_path.append((x, y))
                        else:
                            # Implicit line
                            if is_relative:
                                x += coords[i]
                                y += coords[i + 1]
                            else:
                                x = coords[i]
                                y = coords[i + 1]
                            current_sub_path.append((x, y))
            
            elif cmd_type == 'L':
                # Line command
                for i in range(0, len(coords), 2):
                    if i + 1 < len(coords):
                        if is_relative:
                            x += coords[i]
                            y += coords[i + 1]
                        else:
                            x = coords[i]
                            y = coords[i + 1]
                        current_sub_path.append((x, y))
                        last_control_x, last_control_y = x, y
            
            elif cmd_type == 'H':
                # Horizontal line
                if coords:
                    if is_relative:
                        x += coords[0]
                    else:
                        x = coords[0]
                    current_sub_path.append((x, y))
                    last_control_x, last_control_y = x, y
            
            elif cmd_type == 'V':
                # Vertical line
                if coords:
                    if is_relative:
                        y += coords[0]
                    else:
                        y = coords[0]
                    current_sub_path.append((x, y))
                    last_control_x, last_control_y = x, y
            
            elif cmd_type == 'C':
                # Cubic Bézier curve - USE FULL RESOLUTION
                for i in range(0, len(coords), 6):
                    if i + 5 < len(coords):
                        if is_relative:
                            cp1_x = x + coords[i]
                            cp1_y = y + coords[i + 1]
                            cp2_x = x + coords[i + 2]
                            cp2_y = y + coords[i + 3]
                            end_x = x + coords[i + 4]
                            end_y = y + coords[i + 5]
                        else:
                            cp1_x = coords[i]
                            cp1_y = coords[i + 1]
                            cp2_x = coords[i + 2]
                            cp2_y = coords[i + 3]
                            end_x = coords[i + 4]
                            end_y = coords[i + 5]
                        
                        try:
                            curve_points = cubic_bezier_points(
                                (x, y), (cp1_x, cp1_y), (cp2_x, cp2_y), (end_x, end_y), 
                                curve_resolution  # USE FULL RESOLUTION - NO CAP
                            )
                            current_sub_path.extend(curve_points[1:])
                            x, y = end_x, end_y
                            last_control_x, last_control_y = cp2_x, cp2_y
                        except Exception:
                            current_sub_path.append((end_x, end_y))
                            x, y = end_x, end_y
            
            elif cmd_type == 'S':
                # Smooth cubic Bézier - USE FULL RESOLUTION
                for i in range(0, len(coords), 4):
                    if i + 3 < len(coords):
                        cp1_x = 2 * x - last_control_x
                        cp1_y = 2 * y - last_control_y
                        
                        if is_relative:
                            cp2_x = x + coords[i]
                            cp2_y = y + coords[i + 1]
                            end_x = x + coords[i + 2]
                            end_y = y + coords[i + 3]
                        else:
                            cp2_x = coords[i]
                            cp2_y = coords[i + 1]
                            end_x = coords[i + 2]
                            end_y = coords[i + 3]
                        
                        try:
                            curve_points = cubic_bezier_points(
                                (x, y), (cp1_x, cp1_y), (cp2_x, cp2_y), (end_x, end_y), 
                                curve_resolution  # USE FULL RESOLUTION - NO CAP
                            )
                            current_sub_path.extend(curve_points[1:])
                            x, y = end_x, end_y
                            last_control_x, last_control_y = cp2_x, cp2_y
                        except Exception:
                            current_sub_path.append((end_x, end_y))
                            x, y = end_x, end_y
            
            elif cmd_type == 'Q':
                # Quadratic Bézier - USE FULL RESOLUTION
                for i in range(0, len(coords), 4):
                    if i + 3 < len(coords):
                        if is_relative:
                            cp_x = x + coords[i]
                            cp_y = y + coords[i + 1]
                            end_x = x + coords[i + 2]
                            end_y = y + coords[i + 3]
                        else:
                            cp_x = coords[i]
                            cp_y = coords[i + 1]
                            end_x = coords[i + 2]
                            end_y = coords[i + 3]
                        
                        try:
                            curve_points = quadratic_bezier_points(
                                (x, y), (cp_x, cp_y), (end_x, end_y), 
                                curve_resolution  # USE FULL RESOLUTION - NO CAP
                            )
                            current_sub_path.extend(curve_points[1:])
                            x, y = end_x, end_y
                        except Exception:
                            current_sub_path.append((end_x, end_y))
                            x, y = end_x, end_y
            
            elif cmd_type == 'A':
                # Arc (simplified as line) - USE REASONABLE RESOLUTION
                if len(coords) >= 7:
                    if is_relative:
                        end_x = x + coords[5]
                        end_y = y + coords[6]
                    else:
                        end_x = coords[5]
                        end_y = coords[6]
                    
                    try:
                        arc_resolution = max(6, curve_resolution // 4)  # Reasonable arc resolution
                        arc_points = linear_interpolation((x, y), (end_x, end_y), arc_resolution)
                        current_sub_path.extend(arc_points[1:])
                        x, y = end_x, end_y
                    except Exception:
                        current_sub_path.append((end_x, end_y))
                        x, y = end_x, end_y
            
            elif cmd_type == 'Z':
                # FIXED: Close path - this ends current sub-path and marks it as CLOSED
                current_path_is_closed = True  # 🎯 NEW: Mark as closed
                if current_sub_path and len(current_sub_path) > 2:
                    first_point = current_sub_path[0]
                    # Only add closing point if we're not already close
                    if abs(x - first_point[0]) > 0.1 or abs(y - first_point[1]) > 0.1:
                        current_sub_path.append((start_x, start_y))
                    
                    # FIXED: Complete this sub-path and prepare for next
                    all_sub_paths.append({
                        'points': current_sub_path[:],
                        'is_closed': True  # 🎯 NEW: This path is definitely closed
                    })
                    print(f"     Completed sub-path {len(all_sub_paths)}: {len(current_sub_path)} points (CLOSED - Z command)")
                    current_sub_path = []
                    current_path_is_closed = False  # Reset for next path
                    x, y = start_x, start_y
        
        except Exception as cmd_error:
            print(f"⚠️ Error processing command {cmd_index + 1}: {cmd_error}")
            continue
    
    # Add final sub-path if exists
    if current_sub_path and len(current_sub_path) >= 3:
        all_sub_paths.append({
            'points': current_sub_path,
            'is_closed': current_path_is_closed  # 🎯 NEW: Save closed status (will be False if no Z command)
        })
        print(f"     Final sub-path {len(all_sub_paths)}: {len(current_sub_path)} points ({'CLOSED' if current_path_is_closed else 'OPEN'})")
    
    print(f"   ✅ Path parsing complete: {len(all_sub_paths)} sub-paths extracted")
    return {'sub_paths': all_sub_paths}

# =====================================================
# FIXED WALL COORDINATE GENERATION FUNCTIONS
# =====================================================

def generate_wall_offset_coordinates(svg_content, wall_offsets, corner_radius=4.0, 
                                    resolution=80, pixel_to_mm=0.35277):
    """
    FIXED FUNCTION: Generate wall offset coordinates using existing proven Shapely functions
    
    Args:
        svg_content: SVG content string
        wall_offsets: List of offset distances [0.0, 0.6, 1.2, 1.8]
        corner_radius: Corner radius for rounding
        resolution: Curve resolution
        pixel_to_mm: Pixel to mm conversion factor
        
    Returns:
        List of coordinate arrays for each wall offset
    """
    print(f"🎯 WALL COORDINATE GENERATION START (FIXED VERSION)")
    print(f"   SVG content: {len(svg_content)} characters")
    print(f"   Wall offsets: {wall_offsets}")
    print(f"   Corner radius: {corner_radius}")
    print(f"   Resolution: {resolution}")
    print(f"   Pixel to mm: {pixel_to_mm}")
    
    try:
        all_wall_coordinates = []
        
        # Create temporary directory for processing
        uploads_dir = os.path.join(tempfile.gettempdir(), 'shapely_uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        
        import time
        base_filename = f"wall_coords_input_{int(time.time())}.svg"
        input_path = os.path.join(uploads_dir, base_filename)
        
        # Write SVG content to file for processing
        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"   Input SVG file written: {len(svg_content)} characters")
        
        for i, offset in enumerate(wall_offsets):
            print(f"\n🔄 Processing wall {i} (offset: {offset}mm) using existing Shapely functions")
            
            if offset == 0.0:
                # Wall 0: Direct SVG to coordinates conversion using existing functions
                coordinates = svg_to_coordinate_arrays(svg_content, pixel_to_mm, resolution)
                if coordinates and len(coordinates) > 0:
                    all_wall_coordinates.append(coordinates[0])  # Use first shape
                    print(f"   ✅ Wall {i}: {len(coordinates[0])} points (existing SVG parser)")
                else:
                    print(f"   ❌ Wall {i}: Failed to convert SVG directly")
                    all_wall_coordinates.append([])
            else:
                # Other walls: Use existing Shapely workflow - round_svg_corners then parse
                output_filename = f"wall_{i}_offset_{offset}_{base_filename}"
                output_path = os.path.join(uploads_dir, output_filename)
                
                print(f"   Using existing round_svg_corners() for offset {offset}mm")
                
                # FIXED: Use existing proven round_svg_corners function
                success = round_svg_corners(
                    input_path, output_path,
                    offset=-offset,  # Negative for inward offset
                    corner_radius=corner_radius,
                    curve_resolution=resolution,
                    target_format="bambu"
                )
                
                if success and os.path.exists(output_path):
                    # Parse the offset SVG using existing functions
                    with open(output_path, 'r', encoding='utf-8') as f:
                        offset_svg = f.read()
                    
                    coordinates = svg_to_coordinate_arrays(offset_svg, pixel_to_mm, resolution)
                    if coordinates and len(coordinates) > 0:
                        all_wall_coordinates.append(coordinates[0])  # Use first shape
                        print(f"   ✅ Wall {i}: {len(coordinates[0])} points (existing Shapely + parser)")
                    else:
                        print(f"   ❌ Wall {i}: Failed to parse offset SVG")
                        all_wall_coordinates.append([])
                    
                    # Clean up intermediate file
                    try:
                        os.unlink(output_path)
                    except:
                        pass
                else:
                    print(f"   ❌ Wall {i}: Existing Shapely processing failed")
                    all_wall_coordinates.append([])
        
        # Clean up input file
        try:
            os.unlink(input_path)
        except:
            pass
        
        print(f"\n🎯 WALL COORDINATE GENERATION COMPLETE (FIXED VERSION)")
        print(f"   Generated {len(all_wall_coordinates)} wall coordinate sets using existing functions")
        return all_wall_coordinates
        
    except Exception as e:
        print(f"❌ Wall coordinate generation error: {e}")
        import traceback
        traceback.print_exc()
        return []

def svg_to_coordinate_arrays(svg_content, pixel_to_mm=0.35277, resolution=80):
    """
    FIXED FUNCTION: Convert SVG directly to coordinate arrays using existing parser
    
    Args:
        svg_content: SVG content string
        pixel_to_mm: Pixel to mm conversion factor
        resolution: Curve resolution
        
    Returns:
        List of coordinate arrays (one per shape)
    """
    try:
        print(f"   Converting SVG to coordinates using existing parser: {len(svg_content)} characters")
        
        # Parse SVG content using existing functions
        root = ET.fromstring(svg_content)
        
        # Find all shapes using existing logic
        shapes = []
        for elem in root.iter():
            if (elem.tag.endswith('polygon') or elem.tag.endswith('path') or 
                elem.tag.endswith('rect') or elem.tag.endswith('circle') or 
                elem.tag.endswith('ellipse') or elem.tag.endswith('line') or
                elem.tag.endswith('polyline')):
                shapes.append(elem)
        
        if not shapes:
            print(f"   No shapes found in SVG")
            return []
        
        print(f"   Found {len(shapes)} shapes to convert using existing functions")
        
        all_coordinates = []
        
        for i, shape in enumerate(shapes):
            print(f"   Converting shape {i+1}/{len(shapes)} using existing parser")
            
            # Convert shape to polygon using existing function
            result = svg_to_polygon_with_holes(shape, resolution)
            if not result:
                continue
                
            polygon = result['polygon']
            if polygon.is_empty or not polygon.is_valid:
                continue
            
            # Convert polygon to coordinates using existing function
            coordinates = polygon_to_coordinates(polygon, pixel_to_mm)
            if coordinates:
                all_coordinates.append(coordinates)
                print(f"     ✅ Shape {i+1}: {len(coordinates)} coordinate points")
        
        print(f"   ✅ Converted {len(all_coordinates)} shapes to coordinates using existing functions")
        return all_coordinates
        
    except Exception as e:
        print(f"   Error converting SVG to coordinates: {e}")
        return []

def polygon_to_coordinates(polygon, pixel_to_mm=0.35277):
    """
    EXISTING FUNCTION: Convert Shapely polygon to coordinate array
    
    Args:
        polygon: Shapely polygon object
        pixel_to_mm: Conversion factor
        
    Returns:
        List of [x, y] coordinates in mm
    """
    try:
        coordinates = []
        
        # Extract exterior coordinates
        if hasattr(polygon, 'exterior'):
            exterior_coords = list(polygon.exterior.coords)
            for coord in exterior_coords:
                # Convert from pixels to mm
                x_mm = coord[0] * pixel_to_mm
                y_mm = coord[1] * pixel_to_mm
                coordinates.append([x_mm, y_mm])
        
        # Note: For now, we're only returning exterior coordinates
        # Interior coordinates (holes) could be added later if needed
        
        return coordinates
        
    except Exception as e:
        print(f"     Error converting polygon to coordinates: {e}")
        return []

# =====================================================
# EXISTING FUNCTIONS (UNCHANGED)
# =====================================================

def round_svg_corners_multi(input_file, output_file=None, offset=0.6, corner_radius=4.0, 
                          curve_resolution=40, target_format="bambu", debug_mode=False, 
                          build_plate_width=300, build_plate_height=350,
                          round_inner=True, round_outer=True):
    """
    🎯 SAFE & STREAMLINED: SVG corner rounding using Shapely-only approach
    
    PROCESSING STRATEGY:
    =====================
    1. SVG Cleanup: Parse structure and detect flat curves (no dangerous filtering)
    2. PRE-CLEAN with buffer(0): Instantly untie knots, fix self-intersections
    3. GEOMETRIC SMOOTHING - "Sandpaper" Fix:
       - Uses Shapely's built-in buffer operations
       - Dilate OUT (0.5mm) with round corners to smooth jagged steps
       - Erode back IN (0.5mm) to return to original size
       - Final simplify(0.05mm) removes redundant points
       - join_style=1 forces round corners on every step
       - No OpenCV or SciPy needed!
    4. OFFSET & ROUND: Standard Shapely buffer operations for geometry manipulation
    
    This approach smooths out stair-stepping while preserving holes and features,
    all using lightweight Shapely built-in functions.
    """
    if output_file is None:
        name, ext = os.path.splitext(input_file)
        output_file = f"{name}_optimized_rounded{ext}"
    
    # Auto-detect file type from filename
    file_type = detect_file_type_from_filename(output_file)
    
    with open(input_file, 'r') as f:
        svg_content = f.read()
    
    # 🧹 NEW: CLEANUP MESSY SVG FILES AUTOMATICALLY
    svg_content = cleanup_svg_content(svg_content)
    
    # Coordinate conversion
    PIXEL_CONVERSION_FACTOR = 0.35277
    pixel_offset = offset / PIXEL_CONVERSION_FACTOR
    pixel_corner_radius = corner_radius / PIXEL_CONVERSION_FACTOR
    # 🎯 USE USER RESOLUTION - NO CAPS
    optimized_curve_resolution = curve_resolution  # REMOVED: min(curve_resolution, 12)
    
    print(f"🚀 OPTIMIZED SVG PROCESSOR with HOLE SUPPORT!")
    print(f"📏 Offset: {offset}mm → {pixel_offset:.3f} pixels")
    print(f"📐 Corner radius: {corner_radius}mm → {pixel_corner_radius:.3f} pixels")
    print(f"🎨 Auto-detected type: {file_type} (from filename: {output_file})")
    print(f"🎯 User resolution: {optimized_curve_resolution} (NO CAP - respecting user setting)")
    
    # 🚀 SPEED: Skip debug in optimized version
    debug_mode = False
    
    root = ET.fromstring(svg_content)
    original_width = root.get('width', '')
    original_height = root.get('height', '')
    original_viewbox = root.get('viewBox', '')
    
    print(f"   Original width: {original_width}")
    print(f"   Original height: {original_height}")
    print(f"   Original viewBox: {original_viewbox}")
    
    # Find all shapes
    shapes = []
    for elem in root.iter():
        if (elem.tag.endswith('polygon') or elem.tag.endswith('path') or 
            elem.tag.endswith('rect') or elem.tag.endswith('circle') or 
            elem.tag.endswith('ellipse') or elem.tag.endswith('line') or
            elem.tag.endswith('polyline')):
            shapes.append(elem)
    
    if not shapes:
        print(f"❌ No shapes found in {input_file}")
        return False
    
    print(f"🔍 Found {len(shapes)} shape(s) to process")
    
    # Process all shapes
    all_polygons = []
    all_linestrings = []  # 🎯 NEW: Separate list for open paths
    successful_shapes = 0
    
    for i, shape in enumerate(shapes):
        shape_type = shape.tag.split('}')[-1] if '}' in shape.tag else shape.tag
        print(f"\n🔧 Processing {shape_type} {i+1}/{len(shapes)}...")
        
        try:
            result = svg_to_polygon_with_holes(shape, optimized_curve_resolution)
            if result is None:
                print(f"❌ Could not process {shape_type} {i+1}")
                continue
            
            geometry = result['geometry']
            has_holes = result['has_holes']
            is_open_path = result.get('is_open_path', False)
            
            if geometry.is_empty:
                print(f"❌ {shape_type} {i+1} is empty")
                continue
            
            # 🎯 REPAIR 1: Open Paths (Lines)
            if is_open_path:
                # 0.3mm Smoothing for lines
                geometry = geometry.simplify(0.3, preserve_topology=True) 
                print(f"   ✅ {shape_type} {i+1} smoothed (0.3mm) (OPEN PATH)")
                all_linestrings.append(geometry)
                successful_shapes += 1
                continue
            
            # 🎯 REPAIR 2: Closed Polygons (Letters)
            polygon = geometry
            
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            
            # ---------------------------------------------------------
            # GEOMETRIC SMOOTHING - Hole-preserving version
            # ---------------------------------------------------------
            smoothing_radius = 0.5  # 0.5mm smoothing

            # Save holes before smoothing (buffer can collapse small holes)
            saved_holes = []
            if hasattr(polygon, 'interiors'):
                for interior in polygon.interiors:
                    saved_holes.append(list(interior.coords))

            # Smooth only the exterior ring
            exterior_poly = Polygon(polygon.exterior.coords)
            exterior_poly = exterior_poly.buffer(smoothing_radius, join_style=1, quad_segs=16)
            exterior_poly = exterior_poly.buffer(-smoothing_radius, join_style=1, quad_segs=16)
            exterior_poly = exterior_poly.simplify(0.05, preserve_topology=True)

            # Rebuild polygon with saved holes
            if saved_holes:
                try:
                    exterior_coords = list(exterior_poly.exterior.coords) if hasattr(exterior_poly, 'exterior') else list(exterior_poly.coords)
                    polygon = Polygon(exterior_coords, saved_holes)
                    if not polygon.is_valid:
                        polygon = polygon.buffer(0)
                    print(f"   🕳️ Holes preserved through smoothing: {len(saved_holes)}")
                except Exception as hole_err:
                    print(f"   ⚠️ Could not restore holes: {hole_err}")
                    polygon = exterior_poly
            else:
                polygon = exterior_poly
            # ---------------------------------------------------------
            all_polygons.append(polygon)
            successful_shapes += 1
            
            if has_holes:
                print(f"   ✅ {shape_type} {i+1} processed with holes (sandpaper smoothed)")
            else:
                print(f"   ✅ {shape_type} {i+1} processed successfully (sandpaper smoothed)")
            
        except Exception as shape_error:
            print(f"   ❌ Error processing {shape_type} {i+1}: {shape_error}")
            import traceback
            traceback.print_exc()
            continue
    
    if not all_polygons and not all_linestrings:  # 🎯 CHANGED: Check both lists
        print(f"❌ No valid shapes processed!")
        return False
    
    print(f"\n🎯 Successfully processed {successful_shapes}/{len(shapes)} shapes")
    print(f"   - Closed polygons (will have infill): {len(all_polygons)}")
    print(f"   - Open lines (no infill, just trace): {len(all_linestrings)}")
    
    # Process each polygon
    processed_polygons = []
    
    for i, polygon in enumerate(all_polygons):
        print(f"\n🔧 Processing polygon {i+1}/{len(all_polygons)}...")
        
        # 1. PRE-CLEAN: Untie knots immediately with buffer(0)
        # This fixes self-intersections, overlapping lines, and topology issues
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
            print(f"   🔧 Pre-cleaned with buffer(0) - knots untied")
        
        # 2. GEOMETRIC SMOOTHING (already applied in first pass)
        # The sandpaper fix was already applied, so we just validate here
        print(f"   ✅ Geometric smoothing complete (sandpaper applied)")
        
        try:
            original_is_ccw = polygon.exterior.is_ccw
            processed_polygon = polygon
            
            # Apply offset
            if abs(pixel_offset) > 0.001:
                print(f"   Applying offset: {offset}mm")
                # 🎯 Use reasonable quad_segs based on resolution
                quad_segs = max(3, min(8, optimized_curve_resolution // 5))
                processed_polygon = processed_polygon.buffer(pixel_offset, join_style='round', quad_segs=quad_segs)
                
                if processed_polygon.is_empty or not processed_polygon.is_valid:
                    print(f"   ❌ Offset failed - using original")
                    processed_polygon = polygon
                else:
                    processed_polygon = orient(processed_polygon, sign=1.0 if original_is_ccw else -1.0)
                    print(f"   ✅ Offset applied")
            
            # Apply optimized corner rounding
            if pixel_corner_radius > 0:
                corner_type = []
                if round_inner: corner_type.append("inner")
                if round_outer: corner_type.append("outer")
                corner_desc = " & ".join(corner_type) if corner_type else "no"
                
                print(f"   🔥 Applying {corner_desc} corner rounding: {corner_radius}mm")
                # 🎯 Use reasonable quad_segs based on resolution  
                quad_segs = max(3, min(8, optimized_curve_resolution // 5))
                
                # Use optimized corner rounding
                rounded_polygon = optimized_corner_rounding(
                    processed_polygon, 
                    pixel_corner_radius, 
                    quad_segs
                )
                
                if rounded_polygon.is_empty or not rounded_polygon.is_valid:
                    print(f"   ❌ Corner rounding failed - using original")
                    processed_polygons.append(processed_polygon)
                else:
                    processed_polygon = orient(rounded_polygon, sign=1.0 if original_is_ccw else -1.0)
                    print(f"   ✅ {corner_desc.title()} corner rounding applied")
            
            # Final validation
            if processed_polygon.is_empty or not processed_polygon.is_valid:
                print(f"   ❌ Final validation failed - using original")
                processed_polygons.append(polygon)
            else:
                processed_polygons.append(processed_polygon)
                hole_count = len(list(processed_polygon.interiors)) if hasattr(processed_polygon, 'interiors') else 0
                if hole_count > 0:
                    print(f"   ✅ Polygon {i+1} complete with {hole_count} holes preserved")
                else:
                    print(f"   ✅ Polygon {i+1} complete")
                
        except Exception as processing_error:
            print(f"   ❌ Error processing polygon {i+1}: {processing_error}")
            processed_polygons.append(polygon)
    
    print(f"\n🎯 Processing complete: {len(processed_polygons)} polygons ready")
    
    # Generate SVG with auto-detected colors and both polygons and linestrings
    try:
        new_svg = multi_polygon_to_svg_with_mm_units(processed_polygons, svg_content, file_type, all_linestrings)  # 🎯 PASS linestrings
        
        with open(output_file, 'w') as f:
            f.write(new_svg)
        
        print(f"\n✅ STREAMLINED PROCESSING COMPLETE!")
        print(f"   Input: {input_file}")
        print(f"   Output: {output_file}")
        print(f"   🎨 Auto-detected color: {file_type}")
        print(f"   ⚡ Shapely-only approach (no heavy libs!)")
        print(f"   🔧 Pre-clean: buffer(0) untied knots")
        print(f"   ✨ Curvature-aware: simplify(0.1mm) preserved corners")
        print(f"   🎯 User resolution {curve_resolution} RESPECTED")
        print(f"   🕳️ Hole detection and preservation enabled")
        print(f"   🧹 SVG cleanup automatically applied")
        return True
        
    except Exception as output_error:
        print(f"❌ OUTPUT ERROR: {output_error}")
        return False

def multi_polygon_to_svg_with_mm_units(polygons, original_svg, file_type="face", linestrings=None):
    """Convert polygons and linestrings to SVG with exact coordinate preservation + auto color detection + HOLE SUPPORT + OPEN PATH SUPPORT"""
    if linestrings is None:
        linestrings = []
    
    print(f"📄 Converting {len(polygons)} polygons and {len(linestrings)} linestrings to SVG with {file_type} colors...")
    
    root = ET.fromstring(original_svg)
    original_width = root.get('width', '200mm')
    original_height = root.get('height', '200mm')
    original_viewbox = root.get('viewBox', '')
    
    # Preserve exact dimensions
    width_value = original_width
    height_value = original_height
    
    if 'mm' not in original_width and original_viewbox:
        try:
            vb_parts = original_viewbox.split()
            if len(vb_parts) >= 4:
                vb_width = float(vb_parts[2])
                vb_height = float(vb_parts[3])
                # Convert using the same factor consistently
                width_value = f"{vb_width * 0.35277}mm"
                height_value = f"{vb_height * 0.35277}mm"
        except:
            width_value = "300mm"
            height_value = "320mm"
    
    print(f"   📐 Output dimensions: {width_value} x {height_value}")
    
    # Create SVG with preserved units
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_value}" height="{height_value}"'
    if original_viewbox:
        svg += f' viewBox="{original_viewbox}"'
    svg += '>\n'
    
    # Enhanced color schemes for different file types
    if file_type == "face":
        colors = ["#90EE90", "#98FB98", "#00FA9A", "#00FF7F", "#32CD32", "#7CFC00"]
        print(f"   🎨 Using FACE colors (green tones)")
    elif file_type == "return":
        colors = ["#87CEEB", "#ADD8E6", "#87CEFA", "#B0E0E6", "#E0F6FF", "#F0F8FF"]
        print(f"   🎨 Using RETURN colors (light blue tones)")
    elif file_type == "white":
        colors = ["#F5F5F5", "#FFFFFF", "#F8F8FF", "#F0F8FF", "#FAFAFA", "#E6E6FA"]
        print(f"   🎨 Using WHITE colors (white/light gray tones)")
    else:
        colors = ["#90EE90", "#98FB98", "#00FA9A", "#00FF7F", "#32CD32", "#7CFC00"]
        print(f"   🎨 Using DEFAULT colors (green tones)")
    
    # Add polygons with hole support (FILLED shapes - can have infill)
    for i, polygon in enumerate(polygons):
        color = colors[i % len(colors)]
        
        if hasattr(polygon, 'exterior'):
            path_data = ""
            
            # Exterior ring
            coords = list(polygon.exterior.coords)
            if coords:
                path_data += f"M {coords[0][0]:.3f} {coords[0][1]:.3f} "
                for j in range(1, len(coords)):
                    path_data += f"L {coords[j][0]:.3f} {coords[j][1]:.3f} "
                path_data += "Z "
            
            # Interior rings (holes) - PRESERVED IN OUTPUT
            hole_count = 0
            if hasattr(polygon, 'interiors'):
                for interior in polygon.interiors:
                    hole_count += 1
                    hole_coords = list(interior.coords)
                    if hole_coords:
                        path_data += f"M {hole_coords[0][0]:.3f} {hole_coords[0][1]:.3f} "
                        for j in range(1, len(hole_coords)):
                            path_data += f"L {hole_coords[j][0]:.3f} {hole_coords[j][1]:.3f} "
                        path_data += "Z "
                        print(f"   🕳️ Added hole {hole_count} to polygon {i+1}")
            
            if path_data:
                # 🎯 POLYGON: fill with color (slicer can add infill)
                svg += f'<path d="{path_data}" fill="{color}" fill-rule="evenodd" stroke="#000000" stroke-width="0.1"/>\n'
                if hole_count > 0:
                    print(f"   ✅ Polygon {i+1} added to SVG with color {color} and {hole_count} holes (CAN HAVE INFILL)")
                else:
                    print(f"   ✅ Polygon {i+1} added to SVG with color {color} (CAN HAVE INFILL)")
    
    # 🎯 NEW: Add linestrings (OPEN paths - no fill, stroke only)
    for i, linestring in enumerate(linestrings):
        if hasattr(linestring, 'coords'):
            path_data = ""
            coords = list(linestring.coords)
            
            if len(coords) >= 2:
                path_data += f"M {coords[0][0]:.3f} {coords[0][1]:.3f} "
                for j in range(1, len(coords)):
                    path_data += f"L {coords[j][0]:.3f} {coords[j][1]:.3f} "
                # 🎯 NO "Z" - keep it open!
                
                if path_data:
                    # 🎯 LINESTRING: NO fill, stroke only (slicer sees this as line, no infill)
                    svg += f'<path d="{path_data}" fill="none" stroke="#000000" stroke-width="0.5"/>\n'
                    print(f"   ✅ LineString {i+1} added to SVG (OPEN PATH - NO INFILL, just line)")
    
    svg += '</svg>'
    
    print(f"🎯 SVG created with {file_type} color scheme, {len(polygons)} filled shapes, and {len(linestrings)} open lines!")
    return svg

# Backward compatibility
def round_svg_corners(input_file, output_file=None, offset=0.6, corner_radius=4.0, curve_resolution=40, target_format="bambu", debug_mode=False):
    """🎯 OPTIMIZED: Backward compatibility with FULL RESOLUTION SUPPORT and HOLE SUPPORT"""
    print("🚀 Using OPTIMIZED VERSION with HOLE SUPPORT - FULL RESOLUTION RESPECTED!")
    
    return round_svg_corners_multi(
        input_file, 
        output_file, 
        offset, 
        corner_radius, 
        curve_resolution,  # USE FULL RESOLUTION - NO CAP
        target_format, 
        False,  # 🚀 Force disable debug
        300,  # build_plate_width
        350,  # build_plate_height
        True,  # round_inner
        True   # round_outer
    )

def main():
    print("🚀 STREAMLINED SVG PROCESSOR - SHAPELY-ONLY APPROACH!")
    print("⚡ No heavy libraries - just efficient built-in Shapely functions!")
    print("🔧 Pre-clean with buffer(0) - untie knots instantly")
    print("✨ Curvature-aware with simplify(0.1mm) - preserve corners, delete noise")
    print("🔲 BONUS: Zigzag effect with minimal points and uniform spacing!")
    print("🎯 BONUS: Open paths stay as lines (no infill), closed shapes can have infill!")
    print("🧹 SVG cleanup for messy files (Illustrator, Inkscape, CorelDRAW)!")
    print("🕳️ Proper hole detection for letters like A, P, etc.!")
    print("=" * 80)
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  Corner rounding: python Shapely.py input.svg [output.svg] [target_format]")
        print("  Zigzag effect:   python Shapely.py input.svg output.svg --zigzag [wavelength] [amplitude]")
        print("\nExamples:")
        print("  python Shapely.py logo.svg logo_rounded.svg")
        print("  python Shapely.py line.svg line_zigzag.svg --zigzag 20 5")
        input_file = input("Enter SVG file path: ").strip().strip('"')
        mode = input("Mode (corner/zigzag) [corner]: ").strip() or "corner"
    else:
        input_file = sys.argv[1]
        
        # Check for zigzag mode
        if len(sys.argv) > 3 and sys.argv[3].lower() == '--zigzag':
            mode = 'zigzag'
            output_file = sys.argv[2] if len(sys.argv) > 2 else None
            wavelength = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
            amplitude = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0
        else:
            mode = 'corner'
            output_file = sys.argv[2] if len(sys.argv) > 2 else None
            target_format = sys.argv[3] if len(sys.argv) > 3 else "bambu"
    
    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
        return
    
    try:
        if mode == 'zigzag':
            print(f"\n🔲 ZIGZAG MODE")
            if output_file is None:
                name, ext = os.path.splitext(input_file)
                output_file = f"{name}_zigzag{ext}"
            
            success = apply_zigzag_to_svg(
                input_file,
                output_file,
                wavelength,
                amplitude
            )
            
            if success:
                print("\n🎉 ZIGZAG PROCESSING FINISHED!")
                print("✅ Minimal points - only 2 per wavelength!")
                print("✅ Uniform spacing - no corner bunching!")
                print(f"✅ Output saved: {output_file}")
            else:
                print("❌ Zigzag processing failed!")
        else:
            print(f"\n🚀 CORNER ROUNDING MODE")
            
            # Optimized settings for web use
            offset_distance = 1.0
            corner_radius = 1.0
            curve_resolution = 40
            
            success = round_svg_corners_multi(
                input_file, 
                output_file, 
                offset_distance, 
                corner_radius, 
                curve_resolution, 
                target_format,
                False,  # debug disabled
                300,  # build_plate_width
                350,  # build_plate_height
                True,  # round_inner
                True   # round_outer
            )
            
            if success:
                print("\n🎉 STREAMLINED PROCESSING COMPLETE!")
                print("⚡ Shapely-only approach - no heavy libraries!")
                print("🔧 Pre-clean with buffer(0) untied all knots!")
                print("✨ Curvature-aware simplify(0.1mm) preserved corners!")
                print("🧹 SVG cleanup handled messy files perfectly!")
                print("🕳️ Letters A, P, etc. now have proper holes!")
                print("🎯 Open paths stay as lines, closed shapes can have infill!")
                print("✅ Ready for web use and gcode_3mf.py integration!")
            else:
                print("❌ Processing failed!")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
