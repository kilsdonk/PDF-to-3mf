#!/usr/bin/env python3
"""
====================================================================
GCODE CORE - UNIFIED MODULE (v4.4.0 - Pipeline Edition)
====================================================================

Complete gcode core processing with centralized dependency management
Uses processing_pipeline.py for clean dependency control

Version: v4.4.0-PIPELINE
- Centralized dependency management via processing_pipeline
- Clean import structure
- Easy to add NumPy, SciPy, OpenCV operations
- Backward compatible with existing code

ARCHITECTURE: Python = Pure Processing Logic, JSON = All Configuration Data
"""
import hashlib
import math
import os
import tempfile
import uuid
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

# ============================================================================
# PROCESSING PIPELINE - Centralized dependency management
# ============================================================================
from processing_pipeline import ProcessingPipeline, create_pipeline

# Create global pipeline instance
PROCESSING_PIPELINE = create_pipeline()

# Backward compatibility flags - get from pipeline
HAS_SHAPELY = PROCESSING_PIPELINE.deps.is_available('shapely')
HAS_SCIPY = PROCESSING_PIPELINE.deps.is_available('scipy')
HAS_NUMPY = PROCESSING_PIPELINE.deps.is_available('numpy')

# Get modules from pipeline for direct use
if HAS_SHAPELY:
    shapely_modules = PROCESSING_PIPELINE.deps.get('shapely')
    Polygon = shapely_modules['Polygon']
    Point = shapely_modules['Point']
    LineString = shapely_modules['LineString']
    box = shapely_modules['box']
    MultiPolygon = shapely_modules['MultiPolygon']
    unary_union = shapely_modules['unary_union']
    print("✓ Shapely loaded via processing pipeline")

if HAS_NUMPY:
    np = PROCESSING_PIPELINE.deps.get('numpy')
    print("✓ NumPy loaded via processing pipeline")

if HAS_SCIPY:
    scipy_modules = PROCESSING_PIPELINE.deps.get('scipy')
    print("✓ SciPy loaded via processing pipeline")

# Optional imports - Keep existing
try:
    from infill_generator import create_infill_generator
    HAS_INFILL_GENERATOR = True
    print("✓ Infill generator imported successfully")
except ImportError:
    HAS_INFILL_GENERATOR = False
    print("WARNING: Infill generator not available - infill patterns limited")

try:
    from winding_handler import fix_winding_for_format
    HAS_WINDING_HANDLER = True
    print("✓ Winding handler imported successfully")
except ImportError:
    HAS_WINDING_HANDLER = False
    print("INFO: Winding handler not available - using default Shapely orientation")


# =====================================================
# CORNER ROUNDING CLASS
# =====================================================

class CornerRounder:
    """
    Corner rounding implementation that reads configuration from JSON
    NO HARDCODED VALUES - everything from JSON configuration
    
    This is core geometric processing, not G-code generation specific
    """
    
    def __init__(self, config_manager):
        """
        Initialize corner rounder with JSON configuration
        
        Args:
            config_manager: Configuration manager with JSON settings
        """
        self.config = config_manager
        
        # Read corner radius from JSON - NO DEFAULTS
        self.corner_radius = self._get_corner_radius_from_json()
        self.curve_resolution = self._get_curve_resolution_from_json()
        
        print(f"CornerRounder initialized in CORE module:")
        print(f"  Corner radius: {self.corner_radius}mm (from JSON)")
        print(f"  Curve resolution: {self.curve_resolution} segments (from JSON)")
        
        if self.corner_radius <= 0:
            print("  Corner rounding DISABLED (radius = 0)")
        else:
            print("  Corner rounding ENABLED")
    
    def _get_corner_radius_from_json(self) -> float:
        """Read corner radius from JSON - FORCE PRIORITY for CONFIG FILE values"""
        
        print("=== CORNER RADIUS DETECTION ===")
        
        # ABSOLUTE PRIORITY: Direct config file access (bambu_a1_mini.json)
        if hasattr(self.config, 'config'):
            config_data = self.config.config
            print(f"Config data keys: {list(config_data.keys())}")
            
            # Check shapelySettings first
            if 'shapelySettings' in config_data:
                shapely_settings = config_data['shapelySettings']
                print(f"ShapelySettings found: {shapely_settings}")
                if 'corner' in shapely_settings:
                    corner_radius = float(shapely_settings['corner'])
                    print(f"✓ FOUND CONFIG FILE CORNER RADIUS: {corner_radius}mm")
                    return corner_radius
            
            # Check pathSettings fallback
            if 'pathSettings' in config_data:
                path_settings = config_data['pathSettings']
                print(f"PathSettings found: {path_settings}")
                if 'corner' in path_settings:
                    corner_radius = float(path_settings['corner'])
                    print(f"✓ FOUND CONFIG FILE CORNER RADIUS (pathSettings): {corner_radius}mm")
                    return corner_radius
        
        print("✗ NO corner radius found in config file")
        print("Available config sections:")
        if hasattr(self.config, 'config'):
            for key in self.config.config.keys():
                print(f"  - {key}")
        
        # If no corner radius found, return 0 (disabled)
        print("⚠️ Defaulting to 0.0mm (corner rounding disabled)")
        return 0.0
    
    def _get_curve_resolution_from_json(self) -> int:
        """Read curve resolution from JSON configuration - NO HARDCODED DEFAULTS"""
        
        # Try shapelySettings first
        if hasattr(self.config, 'config'):
            shapely_settings = self.config.config.get('shapelySettings', {})
            if 'resolution' in shapely_settings:
                resolution = shapely_settings['resolution']
                print(f"Found curve resolution in shapelySettings: {resolution}")
                return int(resolution)
        
        # Try pathSettings as fallback
        if hasattr(self.config, 'config'):
            path_settings = self.config.config.get('pathSettings', {})
            if 'curveResolution' in path_settings:
                resolution = path_settings['curveResolution']
                print(f"Found curve resolution in pathSettings: {resolution}")
                return int(resolution)
        
        # Check algorithm settings for fallback resolution
        algorithm_settings = self.config.get_algorithm_settings()
        if 'fallbackCurveResolution' in algorithm_settings:
            resolution = algorithm_settings['fallbackCurveResolution']
            print(f"Using fallback curve resolution from algorithmSettings: {resolution}")
            return int(resolution)
        
        # Fallback to reasonable default if not found
        print("⚠️ Curve resolution not found, using fallback value: 20")
        return 20
    
    def is_rounded_corners_enabled(self) -> bool:
        """Check if corner rounding is enabled (radius > 0)"""
        return self.corner_radius > 0
    
    def apply_rounded_corners_to_rectangle(self, rect_coords: List[List[float]]) -> List[List[float]]:
        """
        Apply simple rounded corners to rectangle coordinates
        Creates clean rounded rectangle like the green example
        
        Args:
            rect_coords: Rectangle coordinates [[x1,y1], [x2,y2], [x3,y3], [x4,y4], [x1,y1]]
            
        Returns:
            New coordinates with simple rounded corners
        """
        if not self.is_rounded_corners_enabled():
            print("Corner rounding disabled, returning original coordinates")
            return rect_coords
        
        if len(rect_coords) < 4:
            print("Not enough coordinates for rectangle corner rounding")
            return rect_coords
        
        print(f"Creating SIMPLE rounded rectangle with {self.corner_radius}mm radius corners")
        
        # Get rectangle bounds
        working_coords = rect_coords[:4] if len(rect_coords) >= 4 else rect_coords
        
        # Find min/max coordinates to define rectangle bounds
        x_coords = [coord[0] for coord in working_coords]
        y_coords = [coord[1] for coord in working_coords]
        
        min_x = min(x_coords)
        max_x = max(x_coords)
        min_y = min(y_coords)
        max_y = max(y_coords)
        
        print(f"  Rectangle bounds: {min_x:.1f},{min_y:.1f} to {max_x:.1f},{max_y:.1f}")
        
        # Ensure radius doesn't exceed half the rectangle dimensions
        width = max_x - min_x
        height = max_y - min_y
        max_radius = min(width, height) / 2
        actual_radius = min(self.corner_radius, max_radius)
        
        if actual_radius != self.corner_radius:
            print(f"  Radius clamped from {self.corner_radius}mm to {actual_radius}mm (rectangle too small)")
        
        # Create simple rounded rectangle
        rounded_coords = self._create_simple_rounded_rectangle(min_x, min_y, max_x, max_y, actual_radius)
        
        print(f"Generated {len(rounded_coords)} coordinates for simple rounded rectangle")
        return rounded_coords
    
    def _create_simple_rounded_rectangle(self, min_x: float, min_y: float, max_x: float, max_y: float, radius: float) -> List[List[float]]:
        """
        Create a simple rounded rectangle with quarter-circle corners
        Like the green example - clean and simple
        
        Args:
            min_x, min_y: Bottom-left corner of rectangle
            max_x, max_y: Top-right corner of rectangle
            radius: Corner radius
            
        Returns:
            List of coordinates forming rounded rectangle
        """
        coords = []
        
        # Calculate corner centers (where quarter-circles are centered)
        corners = [
            (min_x + radius, min_y + radius),  # Bottom-left corner center
            (max_x - radius, min_y + radius),  # Bottom-right corner center
            (max_x - radius, max_y - radius),  # Top-right corner center
            (min_x + radius, max_y - radius),  # Top-left corner center
        ]
        
        # Quarter-circle start angles for each corner (in radians)
        start_angles = [
            math.pi,        # Bottom-left: start at 180°
            3*math.pi/2,    # Bottom-right: start at 270°
            0,              # Top-right: start at 0°
            math.pi/2,      # Top-left: start at 90°
        ]
        
        print(f"  Creating 4 quarter-circle corners with {radius}mm radius")
        
        segments_per_quarter = max(4, self.curve_resolution // 4)  # Smooth quarters
        
        for corner_idx, ((cx, cy), start_angle) in enumerate(zip(corners, start_angles)):
            print(f"    Corner {corner_idx + 1}: center ({cx:.1f}, {cy:.1f}), start angle {math.degrees(start_angle):.0f}°")
            
            # Generate quarter-circle arc (90 degrees)
            for i in range(segments_per_quarter + 1):
                t = i / segments_per_quarter
                angle = start_angle + t * (math.pi / 2)  # 90 degree sweep
                
                x = cx + radius * math.cos(angle)
                y = cy + radius * math.sin(angle)
                coords.append([x, y])
        
        # Close the path
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        
        return coords
    
    def apply_corner_rounding_to_boundaries(self, boundaries: List) -> List:
        """
        Apply corner rounding to all boundaries if they are rectangles
        
        Args:
            boundaries: List of BoundaryInfo objects
            
        Returns:
            List of boundaries with rounded corners applied
        """
        if not self.is_rounded_corners_enabled():
            return boundaries
        
        print(f"Applying corner rounding to {len(boundaries)} boundaries")
        
        rounded_boundaries = []
        for boundary in boundaries:
            if self._boundary_looks_like_rectangle(boundary.coordinates):
                print(f"Applying corner rounding to boundary {boundary.boundary_id} ({boundary.boundary_type})")
                rounded_coords = self.apply_rounded_corners_to_rectangle(boundary.coordinates)
                
                # Create new boundary with rounded coordinates
                # BoundaryInfo is defined in this same file, so we can use it directly
                rounded_boundary = BoundaryInfo(
                    rounded_coords, 
                    boundary.boundary_type,
                    boundary.boundary_id,
                    boundary.parent_id
                )
                rounded_boundaries.append(rounded_boundary)
            else:
                print(f"Boundary {boundary.boundary_id} doesn't look like rectangle, keeping original")
                rounded_boundaries.append(boundary)
        
        return rounded_boundaries
    
    def _boundary_looks_like_rectangle(self, coords: List[List[float]]) -> bool:
        """Check if boundary coordinates are actually a rectangle (not just 4 points)"""
        if not coords or len(coords) < 4:
            return False
        
        # Remove duplicate closing point if present
        working_coords = coords[:-1] if len(coords) > 4 and coords[0] == coords[-1] else coords
        if len(working_coords) != 4:
            return False
        
        # Check if it's actually a rectangle by verifying:
        # 1. Has 4 distinct points
        # 2. Opposite sides are parallel (or very close to parallel)
        # 3. Adjacent sides are perpendicular (or very close to perpendicular)
        
        # Get the 4 corner points
        p0, p1, p2, p3 = working_coords[0], working_coords[1], working_coords[2], working_coords[3]
        
        # Calculate vectors for the 4 sides
        v01 = [p1[0] - p0[0], p1[1] - p0[1]]  # Side 0-1
        v12 = [p2[0] - p1[0], p2[1] - p1[1]]  # Side 1-2
        v23 = [p3[0] - p2[0], p3[1] - p2[1]]  # Side 2-3
        v30 = [p0[0] - p3[0], p0[1] - p3[1]]  # Side 3-0
        
        # Check if opposite sides are parallel (dot product should be close to |v1| * |v2|)
        # For parallel vectors: v1 · v2 ≈ |v1| * |v2| (or ≈ -|v1| * |v2| for opposite direction)
        def dot_product(v1, v2):
            return v1[0] * v2[0] + v1[1] * v2[1]
        
        def vector_length(v):
            return math.sqrt(v[0]**2 + v[1]**2)
        
        def are_parallel(v1, v2, tolerance=0.01):
            """Check if two vectors are parallel"""
            len1 = vector_length(v1)
            len2 = vector_length(v2)
            if len1 < 0.001 or len2 < 0.001:
                return False
            # Normalize vectors
            n1 = [v1[0] / len1, v1[1] / len1]
            n2 = [v2[0] / len2, v2[1] / len2]
            # Check if normalized vectors are parallel (dot product ≈ 1 or ≈ -1)
            dot = abs(dot_product(n1, n2))
            return abs(dot - 1.0) < tolerance
        
        def are_perpendicular(v1, v2, tolerance=0.01):
            """Check if two vectors are perpendicular"""
            len1 = vector_length(v1)
            len2 = vector_length(v2)
            if len1 < 0.001 or len2 < 0.001:
                return False
            # For perpendicular vectors, dot product should be ≈ 0
            dot = abs(dot_product(v1, v2))
            return dot / (len1 * len2) < tolerance
        
        # Check if opposite sides are parallel
        sides_parallel_01_23 = are_parallel(v01, v23)
        sides_parallel_12_30 = are_parallel(v12, v30)
        
        # Check if adjacent sides are perpendicular
        corners_perpendicular = (
            are_perpendicular(v01, v12) and
            are_perpendicular(v12, v23) and
            are_perpendicular(v23, v30) and
            are_perpendicular(v30, v01)
        )
        
        # It's a rectangle if opposite sides are parallel AND adjacent sides are perpendicular
        is_rectangle = (sides_parallel_01_23 and sides_parallel_12_30 and corners_perpendicular)
        
        return is_rectangle

# =====================================================
# PRINTER REGISTRY
# =====================================================

class CompleteSVGPathParser:
    """
    Complete SVG Path Parser with multi-sub-path support for boundary separation
    
    DEPENDENCY ANALYSIS:
    - No hardcoded printer dependencies
    - Only depends on standard XML parsing
    - Configurable via parameters (curve_resolution, pixel_to_mm)
    - Truly printer-agnostic component
    """
    
    def __init__(self, curve_resolution: int, pixel_to_mm: float):
        """
        Initialize with configurable parameters
        
        Args:
            curve_resolution: Number of segments for curve tessellation
            pixel_to_mm: Conversion factor from pixels to mm
        """
        self.curve_resolution = curve_resolution
        self.pixel_to_mm = pixel_to_mm
        print(f"SVG Parser initialized: {curve_resolution} curve resolution, {pixel_to_mm} px/mm")
        print("✓ Full curve support: M, L, H, V, C, c, S, s, Q, q, A, Z")
        print("✓ Multi-sub-path support for boundary separation")
    
    def parse_svg(self, svg_content: str) -> List:
        """Parse SVG content into Shapely polygons with REPAIR PIPELINE"""
        polygons = []
        try:
            # 1. Standard SVG Parsing - get coordinate data
            root = ET.fromstring(svg_content)
            
            # Extract path elements
            paths = root.findall('.//path')
            for path in paths:
                d_attr = path.get('d', '')
                if d_attr.strip():
                    sub_paths = self.parse_path_d_with_subpaths(d_attr)
                    # Convert closed paths to polygons
                    for sub_path_data in sub_paths:
                        if isinstance(sub_path_data, dict) and sub_path_data.get('is_closed', True):
                            coords = sub_path_data['coords']
                            if len(coords) >= 3 and HAS_SHAPELY:
                                try:
                                    poly = Polygon(coords)
                                    if poly.is_valid:
                                        polygons.append(poly)
                                except Exception:
                                    pass
            
            # Extract basic shape elements
            shape_paths = self.extract_shape_elements(root)
            for shape_coords in shape_paths:
                if len(shape_coords) >= 3 and HAS_SHAPELY:
                    try:
                        poly = Polygon(shape_coords)
                        if poly.is_valid:
                            polygons.append(poly)
                    except Exception:
                        pass
            
            print(f"✓ Parsed {len(polygons)} polygons from SVG")
            
            # 2. THE MISSING LINK: Call the Repair Pipeline
            # This triggers the buffer(0) and simplify logic we added
            if polygons and HAS_SHAPELY:
                print(f"🛠️ REPAIR: Sending {len(polygons)} polygons to Pipeline...")
                polygons = PROCESSING_PIPELINE.process(polygons)
                print(f"✓ Pipeline repair complete: {len(polygons)} repaired polygons")
                
            return polygons
            
        except Exception as e:
            print(f"❌ SVG Parsing error: {e}")
            return []
    
    def parse_svg_to_coordinates(self, svg_content: str) -> List[dict]:
        """Parse SVG content with multi-sub-path resolution
        Returns list of dicts with 'coords' and 'is_closed' keys"""
        if not svg_content:
            return []
        
        try:
            # Handle namespace issues
            svg_content_clean = re.sub(r'\s*xmlns="[^"]*"', '', svg_content)
            root = ET.fromstring(svg_content_clean)
            
            all_paths = []
            
            # Extract path elements with multi-sub-path resolution
            paths = root.findall('.//path')
            for path in paths:
                d_attr = path.get('d', '')
                if d_attr.strip():
                    # Parse sub-paths separately
                    sub_paths = self.parse_path_d_with_subpaths(d_attr)
                    if sub_paths:
                        all_paths.extend(sub_paths)  # Add each sub-path as separate path
                        print(f"✓ Parsed path with {len(sub_paths)} sub-paths")
                        for i, sub_path_data in enumerate(sub_paths):
                            coords = sub_path_data['coords'] if isinstance(sub_path_data, dict) else sub_path_data
                            is_closed = sub_path_data.get('is_closed', True) if isinstance(sub_path_data, dict) else True
                            status = "CLOSED" if is_closed else "OPEN"
                            print(f"   Sub-path {i}: {len(coords)} points ({status})")
            
            # Extract basic shape elements (these are always closed)
            shape_paths = self.extract_shape_elements(root)
            for shape_path in shape_paths:
                all_paths.append({'coords': shape_path, 'is_closed': True})
            
            print(f"✓ SVG Parser: Found {len(all_paths)} paths/sub-paths with boundary separation support")
            return all_paths
            
        except ET.ParseError as e:
            print(f"SVG parsing error: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error parsing SVG: {e}")
            return []
    
    def parse_path_d_with_subpaths(self, d_attr: str) -> List[dict]:
        """
        Parse SVG path with multi-sub-path support
        Returns a list of sub-path dicts, each containing:
          - 'coords': list of coordinates
          - 'is_closed': True if path was closed with Z command
        """
        # Clean up the path data
        d_attr = re.sub(r'[,\s]+', ' ', d_attr.strip())
        
        # Split into commands
        commands = re.findall(r'[MmLlHhVvZzCcSsQqTtAa][^MmLlHhVvZzCcSsQqTtAa]*', d_attr)
        
        if not commands:
            return []
        
        print(f"  Parsing {len(commands)} path commands with sub-path detection")
        
        # Track sub-paths separately
        all_sub_paths = []
        current_sub_path = []
        current_pos = [0.0, 0.0]
        start_pos = [0.0, 0.0]
        last_control_x, last_control_y = 0.0, 0.0
        sub_path_count = 0
        current_path_is_closed = False  # Track if current path has Z command
        
        for command_index, command in enumerate(commands):
            cmd_type = command[0]
            is_relative = cmd_type != cmd_type.upper()
            cmd_type = cmd_type.upper()
            
            params = command[1:].strip()
            
            if cmd_type == 'M':  # Move to - POTENTIAL NEW SUB-PATH
                coords = self.parse_number_pairs(params)
                if coords:
                    # Create new sub-path for any M command that has content in current sub-path
                    if current_sub_path and len(current_sub_path) >= 2:
                        # Finish current sub-path and start new one
                        all_sub_paths.append({
                            'coords': current_sub_path,
                            'is_closed': current_path_is_closed
                        })
                        status = "CLOSED" if current_path_is_closed else "OPEN"
                        print(f"    Finished sub-path {sub_path_count}: {len(current_sub_path)} points ({status})")
                        sub_path_count += 1
                        current_sub_path = []
                        current_path_is_closed = False  # Reset for new path
        
                    # Process first coordinate as move
                    if is_relative:
                        current_pos[0] += coords[0][0]
                        current_pos[1] += coords[0][1]
                    else:
                        current_pos = list(coords[0])
        
                    start_pos = list(current_pos)
                    last_control_x, last_control_y = current_pos[0], current_pos[1]
                    current_sub_path.append(list(current_pos))
        
                    # Additional coordinate pairs are treated as line-to
                    for coord in coords[1:]:
                        if is_relative:
                            current_pos[0] += coord[0]
                            current_pos[1] += coord[1]
                        else:
                            current_pos = list(coord)
                        current_sub_path.append(list(current_pos))
            
            elif cmd_type == 'L':  # Line to
                coords = self.parse_number_pairs(params)
                for coord in coords:
                    if is_relative:
                        current_pos[0] += coord[0]
                        current_pos[1] += coord[1]
                    else:
                        current_pos = list(coord)
                    current_sub_path.append(list(current_pos))
                    last_control_x, last_control_y = current_pos[0], current_pos[1]
            
            elif cmd_type == 'H':  # Horizontal line
                numbers = self.parse_numbers(params)
                for num in numbers:
                    if is_relative:
                        current_pos[0] += num
                    else:
                        current_pos[0] = num
                    current_sub_path.append(list(current_pos))
                    last_control_x, last_control_y = current_pos[0], current_pos[1]
            
            elif cmd_type == 'V':  # Vertical line
                numbers = self.parse_numbers(params)
                for num in numbers:
                    if is_relative:
                        current_pos[1] += num
                    else:
                        current_pos[1] = num
                    current_sub_path.append(list(current_pos))
                    last_control_x, last_control_y = current_pos[0], current_pos[1]
            
            elif cmd_type == 'C':  # Cubic Bézier curve
                coords = self.parse_number_pairs(params)
                for i in range(0, len(coords), 3):
                    if i + 2 < len(coords):
                        if is_relative:
                            cp1_x = current_pos[0] + coords[i][0]
                            cp1_y = current_pos[1] + coords[i][1]
                            cp2_x = current_pos[0] + coords[i+1][0]
                            cp2_y = current_pos[1] + coords[i+1][1]
                            end_x = current_pos[0] + coords[i+2][0]
                            end_y = current_pos[1] + coords[i+2][1]
                        else:
                            cp1_x, cp1_y = coords[i]
                            cp2_x, cp2_y = coords[i+1]
                            end_x, end_y = coords[i+2]
                        
                        curve_points = self.cubic_bezier_points(
                            current_pos, [cp1_x, cp1_y], [cp2_x, cp2_y], [end_x, end_y], 
                            self.curve_resolution
                        )
                        
                        current_sub_path.extend(curve_points[1:])
                        current_pos = [end_x, end_y]
                        last_control_x, last_control_y = cp2_x, cp2_y
            
            elif cmd_type == 'S':  # Smooth cubic Bézier
                coords = self.parse_number_pairs(params)
                for i in range(0, len(coords), 2):
                    if i + 1 < len(coords):
                        cp1_x = 2 * current_pos[0] - last_control_x
                        cp1_y = 2 * current_pos[1] - last_control_y
                        
                        if is_relative:
                            cp2_x = current_pos[0] + coords[i][0]
                            cp2_y = current_pos[1] + coords[i][1]
                            end_x = current_pos[0] + coords[i+1][0]
                            end_y = current_pos[1] + coords[i+1][1]
                        else:
                            cp2_x, cp2_y = coords[i]
                            end_x, end_y = coords[i+1]
                        
                        curve_points = self.cubic_bezier_points(
                            current_pos, [cp1_x, cp1_y], [cp2_x, cp2_y], [end_x, end_y], 
                            self.curve_resolution
                        )
                        
                        current_sub_path.extend(curve_points[1:])
                        current_pos = [end_x, end_y]
                        last_control_x, last_control_y = cp2_x, cp2_y
            
            elif cmd_type == 'Q':  # Quadratic Bézier
                coords = self.parse_number_pairs(params)
                for i in range(0, len(coords), 2):
                    if i + 1 < len(coords):
                        if is_relative:
                            cp_x = current_pos[0] + coords[i][0]
                            cp_y = current_pos[1] + coords[i][1]
                            end_x = current_pos[0] + coords[i+1][0]
                            end_y = current_pos[1] + coords[i+1][1]
                        else:
                            cp_x, cp_y = coords[i]
                            end_x, end_y = coords[i+1]
                        
                        curve_points = self.quadratic_bezier_points(
                            current_pos, [cp_x, cp_y], [end_x, end_y], 
                            self.curve_resolution
                        )
                        
                        current_sub_path.extend(curve_points[1:])
                        current_pos = [end_x, end_y]
                        last_control_x, last_control_y = cp_x, cp_y
            
            elif cmd_type == 'T':  # Smooth quadratic Bézier
                coords = self.parse_number_pairs(params)
                for coord in coords:
                    cp_x = 2 * current_pos[0] - last_control_x
                    cp_y = 2 * current_pos[1] - last_control_y
                    
                    if is_relative:
                        end_x = current_pos[0] + coord[0]
                        end_y = current_pos[1] + coord[1]
                    else:
                        end_x, end_y = coord
                    
                    curve_points = self.quadratic_bezier_points(
                        current_pos, [cp_x, cp_y], [end_x, end_y], 
                        self.curve_resolution
                    )
                    
                    current_sub_path.extend(curve_points[1:])
                    current_pos = [end_x, end_y]
                    last_control_x, last_control_y = cp_x, cp_y
            
            elif cmd_type == 'A':  # Arc
                coords = self.parse_arc_params(params)
                for arc_params in coords:
                    if len(arc_params) >= 7:
                        rx, ry, x_axis_rotation, large_arc_flag, sweep_flag, x, y = arc_params[:7]
                        
                        if is_relative:
                            end_x = current_pos[0] + x
                            end_y = current_pos[1] + y
                        else:
                            end_x, end_y = x, y
                        
                        arc_points = self.elliptical_arc_points(
                            current_pos, [end_x, end_y], rx, ry, x_axis_rotation,
                            large_arc_flag, sweep_flag, self.curve_resolution
                        )
                        
                        current_sub_path.extend(arc_points[1:])
                        current_pos = [end_x, end_y]
            
            elif cmd_type == 'Z':  # Close path
                current_path_is_closed = True  # Mark this path as closed
                if current_sub_path and current_sub_path[0] != current_pos:
                    current_sub_path.append(list(start_pos))
                current_pos = list(start_pos)
        
        # Don't forget the last sub-path
        if current_sub_path and len(current_sub_path) >= 2:
            all_sub_paths.append({
                'coords': current_sub_path,
                'is_closed': current_path_is_closed
            })
            status = "CLOSED" if current_path_is_closed else "OPEN"
            print(f"    Finished final sub-path {sub_path_count}: {len(current_sub_path)} points ({status})")
        
        print(f"  ✓ Path parsing complete: {len(all_sub_paths)} sub-paths found")
        return all_sub_paths
    
    def get_svg_dimensions(self, svg_content: str) -> Tuple[float, float]:
        """Extract the natural dimensions of the SVG"""
        if not svg_content:
            return 0.0, 0.0
        
        try:
            # Handle namespace issues
            svg_content_clean = re.sub(r'\s*xmlns="[^"]*"', '', svg_content)
            root = ET.fromstring(svg_content_clean)

            # ── Priority 1: read width/height attributes when they carry mm units ──
            w_attr = root.get('width', '')
            h_attr = root.get('height', '')
            if w_attr.endswith('mm') and h_attr.endswith('mm'):
                try:
                    svg_width_mm  = float(w_attr[:-2])
                    svg_height_mm = float(h_attr[:-2])
                    print(f"✓ SVG natural dimensions from attributes: {svg_width_mm:.1f}x{svg_height_mm:.1f}mm")
                    return svg_width_mm, svg_height_mm
                except ValueError:
                    pass  # fall through to path-based calculation

            # ── Fallback: calculate bounding box from path coordinates ──
            # Find bounding box of all paths
            all_coords = []
            
            # Extract path elements with multi-sub-path parsing
            paths = root.findall('.//path')
            for path in paths:
                d_attr = path.get('d', '')
                if d_attr.strip():
                    sub_paths = self.parse_path_d_with_subpaths(d_attr)
                    for sub_path_data in sub_paths:
                        # Handle both old format (list) and new format (dict)
                        if isinstance(sub_path_data, dict):
                            all_coords.extend(sub_path_data['coords'])
                        else:
                            all_coords.extend(sub_path_data)
            
            # Extract basic shape elements  
            shape_paths = self.extract_shape_elements(root)
            for shape_path in shape_paths:
                all_coords.extend(shape_path)
            
            if not all_coords:
                return 0.0, 0.0
            
            # Calculate bounding box
            min_x = min(coord[0] for coord in all_coords)
            max_x = max(coord[0] for coord in all_coords)
            min_y = min(coord[1] for coord in all_coords)
            max_y = max(coord[1] for coord in all_coords)
            
            svg_width = max_x - min_x
            svg_height = max_y - min_y
            
            # Convert to mm
            svg_width_mm = svg_width * self.pixel_to_mm
            svg_height_mm = svg_height * self.pixel_to_mm
            
            print(f"✓ SVG natural dimensions: {svg_width:.1f}x{svg_height:.1f} units = {svg_width_mm:.1f}x{svg_height_mm:.1f}mm")
            return svg_width_mm, svg_height_mm
            
        except Exception as e:
            print(f"Error extracting SVG dimensions: {e}")
            return 0.0, 0.0
    
    # Curve generation methods (printer-agnostic)
    def cubic_bezier_points(self, p0, p1, p2, p3, num_points):
        """Generate points along cubic Bézier curve"""
        if num_points < 2:
            return [p0, p3]
        
        points = []
        for i in range(num_points + 1):
            t = i / num_points
            t2 = t * t
            t3 = t2 * t
            mt = 1 - t
            mt2 = mt * mt
            mt3 = mt2 * mt
            
            x = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
            y = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
            points.append([x, y])
        
        return points
    
    def quadratic_bezier_points(self, p0, p1, p2, num_points):
        """Generate points along quadratic Bézier curve"""
        if num_points < 2:
            return [p0, p2]
        
        points = []
        for i in range(num_points + 1):
            t = i / num_points
            t2 = t * t
            mt = 1 - t
            mt2 = mt * mt
            
            x = mt2 * p0[0] + 2 * mt * t * p1[0] + t2 * p2[0]
            y = mt2 * p0[1] + 2 * mt * t * p1[1] + t2 * p2[1]
            points.append([x, y])
        
        return points
    
    def elliptical_arc_points(self, start, end, rx, ry, x_axis_rotation, 
                            large_arc_flag, sweep_flag, num_points):
        """Generate points along elliptical arc"""
        if num_points < 2:
            return [start, end]
        
        # Simplified arc implementation - for complex arcs, use proper elliptical arc math
        points = []
        for i in range(num_points + 1):
            t = i / num_points
            x = start[0] + t * (end[0] - start[0])
            y = start[1] + t * (end[1] - start[1])
            points.append([x, y])
        
        return points
    
    def parse_number_pairs(self, params: str) -> List[List[float]]:
        """Parse coordinate pairs from parameter string"""
        if not params.strip():
            return []
        
        numbers = self.parse_numbers(params)
        pairs = []
        
        for i in range(0, len(numbers) - 1, 2):
            pairs.append([numbers[i], numbers[i + 1]])
        
        return pairs
    
    def parse_arc_params(self, params: str) -> List[List[float]]:
        """Parse arc parameters (rx ry x-axis-rotation large-arc-flag sweep-flag x y)"""
        if not params.strip():
            return []
        
        numbers = self.parse_numbers(params)
        arc_params = []
        
        for i in range(0, len(numbers) - 6, 7):
            if i + 6 < len(numbers):
                arc_params.append(numbers[i:i+7])
        
        return arc_params
    
    def parse_numbers(self, params: str) -> List[float]:
        """Parse numbers from parameter string"""
        if not params.strip():
            return []
        
        number_pattern = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
        matches = re.findall(number_pattern, params)
        
        return [float(match) for match in matches]
    
    def extract_shape_elements(self, root) -> List[List[List[float]]]:
        """Extract basic SVG shapes with configurable resolution"""
        shape_paths = []
        
        # Rectangles
        rects = root.findall('.//rect')
        print(f"  Found {len(rects)} rectangle(s)")
        for rect in rects:
            coords = self.rect_to_coordinates(rect)
            if coords:
                print(f"  ✓ Rectangle: {len(coords)} points")
                shape_paths.append(coords)
            else:
                print(f"  ⚠️  Rectangle parsing failed")
        
        # Circles with configurable resolution
        circles = root.findall('.//circle')
        print(f"  Found {len(circles)} circle(s)")
        for circle in circles:
            coords = self.circle_to_coordinates(circle, segments=self.curve_resolution)
            if coords:
                print(f"  ✓ Circle: {len(coords)} points")
                shape_paths.append(coords)
        
        # Polygons
        polygons = root.findall('.//polygon')
        print(f"  Found {len(polygons)} polygon(s)")
        for polygon in polygons:
            coords = self.polygon_to_coordinates(polygon)
            if coords:
                print(f"  ✓ Polygon: {len(coords)} points")
                shape_paths.append(coords)
            else:
                print(f"  ⚠️  Polygon parsing failed")
        
        # Polylines (CRITICAL FOR SIGNMAKER SOFTWARE!)
        polylines = root.findall('.//polyline')
        print(f"  Found {len(polylines)} polyline(s)")
        for polyline in polylines:
            coords = self.polyline_to_coordinates(polyline)
            if coords:
                print(f"  ✓ Polyline: {len(coords)} points")
                shape_paths.append(coords)
            else:
                print(f"  ⚠️  Polyline parsing failed")
        
        print(f"  Total shape paths extracted: {len(shape_paths)}")
        return shape_paths
    
    def rect_to_coordinates(self, rect) -> Optional[List[List[float]]]:
        """Convert rectangle element to coordinates"""
        try:
            x = float(rect.get('x', 0))
            y = float(rect.get('y', 0))
            width = float(rect.get('width', 0))
            height = float(rect.get('height', 0))
            
            return [
                [x, y],
                [x + width, y],
                [x + width, y + height],
                [x, y + height],
                [x, y]
            ]
        except (ValueError, TypeError):
            return None
    
    def circle_to_coordinates(self, circle, segments: int = None):
        """Convert circle element to coordinate approximation"""
        if segments is None:
            segments = self.curve_resolution
    
        try:
            cx = float(circle.get('cx', 0))
            cy = float(circle.get('cy', 0))
            r = float(circle.get('r', 0))
        
            coordinates = []
            for i in range(segments + 1):
                angle = 2 * math.pi * i / segments
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                coordinates.append([x, y])
        
            return coordinates
        except (ValueError, TypeError):
            return None
    
    def polygon_to_coordinates(self, polygon) -> Optional[List[List[float]]]:
        """Convert polygon element to coordinates"""
        try:
            points_attr = polygon.get('points', '')
            if not points_attr.strip():
                return None
            
            coords = self.parse_number_pairs(points_attr)
            if coords and coords[0] != coords[-1]:
                coords.append(coords[0])
            
            return coords
        except (ValueError, TypeError):
            return None
    
    def polyline_to_coordinates(self, polyline) -> Optional[List[List[float]]]:
        """Convert polyline element to coordinates (CRITICAL FOR SIGNMAKER!)"""
        try:
            points_attr = polyline.get('points', '')
            if not points_attr.strip():
                return None
            
            coords = self.parse_number_pairs(points_attr)
            # Polylines might be open or closed - close them if not already closed
            if coords and len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords.append(coords[0])  # Close the path
                return coords
            
            return None
        except (ValueError, TypeError):
            return None

# =====================================================
# CONFIGURATION MANAGER
# =====================================================

class ConfigurationManager:
    """
    JSON-DRIVEN CONFIGURATION MANAGER WITH FACTORY METHODS
    
    Enhanced with clean factory methods for different instantiation patterns.
    Main constructor now focuses on direct configuration loading.
    """
    
    def __init__(self, config_input, 
                 printer_config_map: Optional[Dict[str, str]] = None,
                 printer_registry: Optional[Any] = None):
        """
        LEGACY CONSTRUCTOR: Maintains backward compatibility
        
        For new code, prefer the factory methods:
        - ConfigurationManager.from_config_file(path)
        - ConfigurationManager.from_html(html_json) 
        - ConfigurationManager.from_printer_type(printer_type)
        """
        print("=== CONFIGURATION MANAGER INITIALIZATION (DIRECT) ===")
        
        # Simple direct initialization - no deleted functions
        if isinstance(config_input, dict):
            resolved_config = config_input
        elif isinstance(config_input, str):
            # Assume it's a file path
            import json
            with open(config_input, 'r') as f:
                resolved_config = json.load(f)
        else:
            raise ValueError("Config input must be dict or file path string")
        
        # Initialize with resolved configuration
        self._initialize_with_config(resolved_config)
    
    @classmethod
    def from_config_file(cls, config_file_path: str) -> 'ConfigurationManager':
        """
        CLEAN FACTORY METHOD - DIRECT CONFIG FILE LOADING
        
        Create ConfigurationManager directly from a configuration file path.
        This is the cleanest interface for file-based configuration loading.
        
        Args:
            config_file_path: Path to configuration JSON file
            
        Returns:
            ConfigurationManager instance
            
        Raises:
            FileNotFoundError: Configuration file not found
            ValueError: Invalid configuration format
        """
        print(f"=== CONFIGURATION MANAGER FROM CONFIG FILE: {config_file_path} ===")
        
        # Direct file loading - no deleted functions
        import json
        with open(config_file_path, 'r') as f:
            config = json.load(f)
        
        # Create instance and initialize
        instance = cls.__new__(cls)
        instance._initialize_with_config(config)
        
        print(f"✓ ConfigurationManager created from {config_file_path}")
        return instance
    
    @classmethod
    def from_html(cls, html_json: Dict[str, Any], 
                  printer_registry: Optional[Any] = None) -> 'ConfigurationManager':
        """
        CLEAN FACTORY METHOD - HTML-TO-CONFIG CONVERSION
        
        Create ConfigurationManager from HTML JSON with automatic conversion.
        This provides a clean interface for HTML-based configuration.
        
        Args:
            html_json: HTML-generated JSON configuration
            printer_registry: Optional printer registry (uses default if None)
            
        Returns:
            ConfigurationManager instance
            
        Raises:
            ValueError: Invalid HTML JSON or unknown printer type
            FileNotFoundError: Required printer configuration file not found
        """
        print("=== CONFIGURATION MANAGER FROM HTML JSON ===")
        
        raise NotImplementedError(
            "ConfigurationManager.from_html() is not supported. "
            "Load config file directly and merge HTML settings manually. "
            "See gcode_3mf.py generate_3mf_from_html_json() for example."
        )
    
    @classmethod  
    def from_printer_type(cls, printer_type: str,
                         printer_registry: Optional[Any] = None) -> 'ConfigurationManager':
        """
        CLEAN FACTORY METHOD - REGISTRY-BASED LOADING
        
        Create ConfigurationManager from printer type using registry lookup.
        This provides a clean interface for printer-type-based loading.
        
        Args:
            printer_type: Printer type identifier
            printer_registry: Optional printer registry (uses default if None)
            
        Returns:
            ConfigurationManager instance
            
        Raises:
            ValueError: Unknown printer type
            FileNotFoundError: Required printer configuration file not found
        """
        print(f"=== CONFIGURATION MANAGER FROM PRINTER TYPE: {printer_type} ===")
        
        raise NotImplementedError(
            "ConfigurationManager.from_printer_type() is not supported. "
            "Use ConfigurationManager.from_config_file('printer_name.json') instead."
        )
    
    def _initialize_with_config(self, config: Dict[str, Any]):
        """Initialize instance with validated configuration"""
        print("=== CONFIGURATION LOADING PHASE ===")
        
        self.config = config
        
        # Validate required sections exist
        self._validate_configuration()
        
        # Load printer-specific configuration data
        self._load_printer_config()
        
        print(f"✓ Configuration initialized: {self.config.get('name', 'Unknown')} ({self.config.get('id', 'unknown')})")
    
    def _validate_configuration(self):
        """Validate that required configuration sections exist"""
        print("=== VALIDATING CONFIGURATION STRUCTURE ===")
        
        required_sections = [
            'buildVolume', 'temperatureSettings', 'speedSettings', 
            'layerSettings', 'movementSettings',
            'endGcodeSettings', 'algorithmSettings'
        ]
        
        missing_sections = []
        for section in required_sections:
            if section not in self.config:
                missing_sections.append(section)
        
        if missing_sections:
            raise ValueError(f"Missing required configuration sections: {missing_sections}")
        
        # Validate critical subsections
        self._validate_subsections()
        print("✓ Configuration structure validation complete")
    
    def _validate_subsections(self):
        """Validate required fields within sections"""
        
        # Build volume validation
        build_vol = self.config.get('buildVolume', {})
        required_build_fields = ['x', 'y', 'z']
        missing_build = [field for field in required_build_fields if field not in build_vol]
        if missing_build:
            raise ValueError(f"buildVolume missing required fields: {missing_build}")
        
        # Temperature settings validation
        temp_settings = self.config.get('temperatureSettings', {})
        required_temp_fields = ['nozzleTemp', 'bedTemp', 'filamentDiameter']
        missing_temp = [field for field in required_temp_fields if field not in temp_settings]
        if missing_temp:
            raise ValueError(f"temperatureSettings missing required fields: {missing_temp}")
        
        # Speed settings validation
        speed_settings = self.config.get('speedSettings', {})
        required_speed_fields = ['travelSpeed', 'printSpeed']
        missing_speed = [field for field in required_speed_fields if field not in speed_settings]
        if missing_speed:
            raise ValueError(f"speedSettings missing required fields: {missing_speed}")
    
    def _load_printer_config(self):
        """Load printer-specific settings from validated configuration"""
        print("=== LOADING PRINTER CONFIGURATION DATA ===")
        
        self.printer_id = self.config['id']
        self.printer_name = self.config['name']
        self.manufacturer = self.config.get('manufacturer', 'Unknown')
        
        # Build volume - REQUIRED
        build_vol = self.config['buildVolume']
        self.bed_size_x = build_vol['x']
        self.bed_size_y = build_vol['y'] 
        self.bed_size_z = build_vol['z']
        
        # System type
        self.system_type = self.config.get('systemType', 'standard')
        self.is_multi_material = 'dual_nozzle' in self.system_type or 'ams' in self.system_type
        
        print(f"✓ Loaded printer config: {self.printer_name} ({self.printer_id})")
        print(f"  Build volume: {self.bed_size_x}x{self.bed_size_y}x{self.bed_size_z}mm")
        print(f"  System type: {self.system_type}")
    
    # ===== SETTINGS ACCESS METHODS =====
    
    def get_temperature_settings(self) -> Dict[str, Any]:
        """Get temperature configuration"""
        return self.config['temperatureSettings']
    
    def get_speed_settings(self) -> Dict[str, Any]:
        """Get speed configuration"""
        return self.config['speedSettings']
    
    def get_layer_settings(self) -> Dict[str, Any]:
        """Get layer configuration"""
        return self.config['layerSettings']
    
    def get_movement_settings(self) -> Dict[str, Any]:
        """Get movement configuration"""
        return self.config['movementSettings']
    
    def get_end_gcode_settings(self) -> Dict[str, Any]:
        """Get end G-code configuration"""
        return self.config['endGcodeSettings']
    
    def get_algorithm_settings(self) -> Dict[str, Any]:
        """Get algorithm configuration"""
        return self.config['algorithmSettings']
    
    def get_fan_settings(self) -> Dict[str, Any]:
        """Get fan control configuration"""
        return self.config.get('fanSettings', {})
    
    def get_infill_settings(self) -> Dict[str, Any]:
        """Get infill configuration"""
        return self.config.get('infillSettings', {})
    
    def get_wall_settings(self) -> Dict[str, Any]:
        """Get wall configuration"""
        return self.config.get('wallSettings', {})
    
    def get_foundation_settings(self) -> Dict[str, Any]:
        """Get foundation configuration"""
        return self.config.get('foundationSettings', {})
    
    def get_layers_configuration(self) -> List[Dict[str, Any]]:
        """Get layers configuration"""
        return self.config.get('layers', [])
    
    def get_filament_types(self) -> Dict[str, Any]:
        """Get filament types configuration"""
        return self.config.get('filamentTypes', {})
    
    def get_shape_settings(self) -> Dict[str, Any]:
        """Get shape settings configuration"""
        return self.config.get('shapeSettings', {})
    
    def get_path_processing_settings(self) -> Dict[str, Any]:
        """Get path processing configuration"""
        return self.config.get('pathProcessingSettings', {})

# =====================================================
# BOUNDARY INFORMATION CLASS
# =====================================================

class BoundaryInfo:
    """
    Information about a boundary (outer or inner)
    
    Pure geometric calculation class - printer-agnostic
    """
    
    def __init__(self, coordinates: List[List[float]], boundary_type: str, 
                 boundary_id: int = 0, parent_id: Optional[int] = None,
                 is_closed: bool = True):
        self.coordinates = coordinates
        self.boundary_type = boundary_type  # 'outer' or 'inner'
        self.boundary_id = boundary_id
        self.parent_id = parent_id  # For inner boundaries, ID of containing outer boundary
        self.is_closed = is_closed  # True for closed paths, False for open paths (lines)
        self.area = self._calculate_area() if coordinates and is_closed else 0.0
    
    def _calculate_area(self) -> float:
        """Calculate the area of the boundary using shoelace formula"""
        if len(self.coordinates) < 3:
            return 0.0
        
        area = 0.0
        n = len(self.coordinates)
        for i in range(n):
            j = (i + 1) % n
            area += self.coordinates[i][0] * self.coordinates[j][1]
            area -= self.coordinates[j][0] * self.coordinates[i][1]
        
        return abs(area) / 2.0
    
    def is_clockwise(self) -> bool:
        """Determine if the boundary is oriented clockwise"""
        if len(self.coordinates) < 3:
            return False
        
        area = 0.0
        n = len(self.coordinates)
        for i in range(n):
            j = (i + 1) % n
            area += (self.coordinates[j][0] - self.coordinates[i][0]) * (self.coordinates[j][1] + self.coordinates[i][1])
        
        return area > 0

# =====================================================
# GCODE_CORE_1.PY COMPLETE - FOUNDATION LAYER
# =====================================================

"""
GCODE_CORE_1.PY v4.2.0 SUMMARY - PART 1 OF 2 - DYNAMIC SVG SELECTION
============================================

FOUNDATION & CONFIGURATION LAYER

This module contains:
✓ CornerRounder - Geometric corner rounding
✓ PrinterRegistry - Printer discovery and mapping
✓ Configuration loading functions
✓ CompleteSVGPathParser - SVG parsing and path processing
✓ ConfigurationManager - Configuration management
✓ BoundaryInfo - Boundary information helper

NEW in v4.2.0:
✓ Dynamic SVG content selection based on layerFileMapping
✓ Respects HTML instructions for "return" vs "original" SVG content
✓ Single unified codebase - no more separate versions for offset/no-offset

NEXT: gcode_core_2.py will contain PathProcessor and processing layer
"""
# =====================================================
# PATH PROCESSOR WITH ZIGZAG SANDWICH PANEL SUPPORT
# =====================================================

class PathProcessor:
    """
    PATH PROCESSOR WITH INTEGRATED CORNER ROUNDING AND ZIGZAG
    
    Enhanced with:
    - Corner rounding support from CornerRounder class
    - Zigzag sandwich panel support for structural middle walls
    - All settings from JSON - no hardcoded values
    """
    
    def __init__(self, config_manager: ConfigurationManager):
        """
        Initialize PathProcessor with corner rounding and zigzag support
        """
        self.config = config_manager
        
        # Get ALL processing settings from config
        self.path_settings = self.config.get_path_processing_settings()
        self.wall_settings = self.config.get_wall_settings()
        self.shape_settings = self.config.get_shape_settings()
        
        print(f"PathProcessor (printer-agnostic) initialized:")
        print(f"  Path settings: {self.path_settings}")
        print(f"  Wall settings: {self.wall_settings}")
        print(f"  Shapely available: {HAS_SHAPELY}")
        print(f"  Winding handler available: {HAS_WINDING_HANDLER}")
        
        # Initialize corner rounding functionality
        self.corner_rounder = CornerRounder(config_manager)
        
        # Get zigzag settings from JSON - no hardcoded defaults
        self.zigzag_settings = self.config.config.get('zigzagSettings', {})
        print("=" * 80)
        print("🔍 DEBUG: ZIGZAG SETTINGS LOADED")
        print("=" * 80)
        for key, value in self.zigzag_settings.items():
            print(f"  {key}: {value}")
        print("=" * 80)
        
        if self.zigzag_settings.get('enabled', False):
            amp_start = self.zigzag_settings.get('amplitudeStart')
            amp_end = self.zigzag_settings.get('amplitudeEnd', amp_start)
            if amp_start == amp_end:
                print(f"  Zigzag enabled: wavelength={self.zigzag_settings.get('wavelength')}mm, "
                      f"amplitude={amp_start}mm (constant)")
            else:
                print(f"  Zigzag enabled: wavelength={self.zigzag_settings.get('wavelength')}mm, "
                      f"amplitude={amp_start}mm→{amp_end}mm (variable)")
        else:
            print("  ⚠️ Zigzag DISABLED in settings")
        
        # Initialize SVG parser with REQUIRED settings from JSON
        shapely_settings = self.config.config.get('shapelySettings', {})
        if 'resolution' not in shapely_settings or 'pixelToMm' not in shapely_settings:
            raise KeyError("shapelySettings must include 'resolution' and 'pixelToMm' in JSON configuration - no hardcoded defaults available")
        
        curve_resolution = shapely_settings['resolution']        # Required from JSON
        pixel_to_mm = shapely_settings['pixelToMm']             # Required from JSON
        
        self.svg_parser = CompleteSVGPathParser(
            curve_resolution=curve_resolution,
            pixel_to_mm=pixel_to_mm
        )
        
        self.svg_content = None
        self.parsed_paths = []
        
        # Boundary separation storage
        self.boundaries = []  # List of BoundaryInfo objects
        self.outer_boundaries = []  # List of outer boundary indices
        self.inner_boundaries = []  # List of inner boundary indices
        
        # Multi-boundary coordinate transformation
        self._unified_scale_params = None  # Cache for unified scaling parameters
        
        # Get shape configuration
        self.layers = self.config.get_layers_configuration()
        
        # Extract SVG content for processing
        self._extract_svg_content()
        
        # Separate boundaries for intra-object transitions
        self._separate_boundaries()
        
        # Apply corner rounding to existing boundaries if enabled
        if self.corner_rounder.is_rounded_corners_enabled():
            print("Applying corner rounding to existing boundaries...")
            self.boundaries = self.corner_rounder.apply_corner_rounding_to_boundaries(self.boundaries)
            print(f"Corner rounding applied to {len(self.boundaries)} boundaries")
        
        # Calculate shape dimensions
        self._calculate_shape_info()
        
        # Cache for wall coordinates - for performance
        self._wall_coordinates_cache = {}
        
        # Cache for base polygon - for Shapely operations
        self._base_polygon_cache = None
        
        # Seam selector integration - store base wall seam positions per boundary
        self._base_seam_start_positions = {}  # {boundary_id: [x, y]}
    
    @classmethod
    def from_config_file(cls, config_file_path: str) -> 'PathProcessor':
        """
        CLEAN FACTORY METHOD - DIRECT CONFIG FILE LOADING
        
        Create PathProcessor directly from a configuration file path.
        
        Args:
            config_file_path: Path to configuration JSON file
            
        Returns:
            PathProcessor instance
        """
        print(f"=== PATH PROCESSOR FROM CONFIG FILE: {config_file_path} ===")
        
        config_manager = ConfigurationManager.from_config_file(config_file_path)
        return cls(config_manager)
    
    @classmethod
    def from_html(cls, html_json: Dict[str, Any],
                  printer_registry: Optional[Any] = None) -> 'PathProcessor':
        """
        CLEAN FACTORY METHOD - HTML-BASED INSTANTIATION
        
        Create PathProcessor from HTML JSON with automatic conversion.
        
        Args:
            html_json: HTML-generated JSON configuration
            printer_registry: Optional printer registry
            
        Returns:
            PathProcessor instance
        """
        print("=== PATH PROCESSOR FROM HTML JSON ===")
        
        config_manager = ConfigurationManager.from_html(html_json, printer_registry)
        return cls(config_manager)
    
    def _extract_svg_content(self):
        """Extract SVG content from configuration"""
        # Try shape settings first
        if self.shape_settings and 'svgContent' in self.shape_settings:
            self.svg_content = self.shape_settings['svgContent']
            print("✓ SVG content found in shape settings")
        # Try files section as fallback
        elif hasattr(self.config, 'config') and 'files' in self.config.config and 'originalSvgContent' in self.config.config['files']:
            self.svg_content = self.config.config['files']['originalSvgContent']
            print("✓ SVG content found in files section (fallback)")
        else:
            print("No SVG content found - will fall back to rectangle if needed")
            return
        
        if self.svg_content:
            # Parse SVG with multi-sub-path support
            self.parsed_paths = self.svg_parser.parse_svg_to_coordinates(self.svg_content)
            print(f"✓ Parsed {len(self.parsed_paths)} paths from SVG with sub-path support")
    
    def _separate_boundaries(self):
        """Separate outer and inner boundaries for intra-object transition handling"""
        print("=== BOUNDARY SEPARATION START ===")
        
        if not self.parsed_paths:
            print("No parsed paths available for boundary separation")
            return
        
        # First, separate open and closed paths
        open_paths = []
        closed_paths = []
        
        for i, path_data in enumerate(self.parsed_paths):
            # Handle both old format (list) and new format (dict)
            if isinstance(path_data, dict):
                coords = path_data['coords']
                is_closed = path_data['is_closed']
            else:
                # Legacy format - assume closed if 3+ points
                coords = path_data
                is_closed = len(coords) >= 3
            
            if is_closed and len(coords) >= 3:
                closed_paths.append({'index': i, 'coords': coords, 'is_closed': True})
            elif len(coords) >= 2:
                open_paths.append({'index': i, 'coords': coords, 'is_closed': False})
                print(f"  Path {i}: OPEN PATH with {len(coords)} points (will be line, no infill)")
        
        print(f"  Found {len(closed_paths)} closed paths, {len(open_paths)} open paths")
        
        # Process open paths first - they are treated as 'outer' for processing but marked as not closed
        boundary_id = 0
        for path_data in open_paths:
            boundary = BoundaryInfo(path_data['coords'], 'outer', boundary_id, is_closed=False)
            self.boundaries.append(boundary)
            self.outer_boundaries.append(boundary_id)
            print(f"  Boundary {boundary_id}: OPEN PATH (line, {len(path_data['coords'])} points, no infill)")
            boundary_id += 1
        
        if not closed_paths:
            print(f"✓ Boundary separation complete:")
            print(f"  Total boundaries: {len(self.boundaries)}")
            print(f"  Open paths (lines): {len(open_paths)}")
            return
        
        if not HAS_SHAPELY:
            print("Shapely not available - treating all closed paths as outer boundaries")
            # Fallback: treat all closed paths as outer boundaries
            for path_data in closed_paths:
                boundary = BoundaryInfo(path_data['coords'], 'outer', boundary_id, is_closed=True)
                self.boundaries.append(boundary)
                self.outer_boundaries.append(boundary_id)
                boundary_id += 1
            return
        
        try:
            # Convert closed paths to Shapely polygons for boundary analysis
            polygons = []
            valid_path_data = []
            
            for path_data in closed_paths:
                coords = path_data['coords']
                if len(coords) >= 3:
                    try:
                        polygon = Polygon(coords)
                        if polygon.is_valid:
                            polygons.append(polygon)
                            valid_path_data.append(path_data)
                        else:
                            # Try to fix invalid polygon
                            fixed_polygon = polygon.buffer(0)
                            if fixed_polygon.is_valid:
                                polygons.append(fixed_polygon)
                                valid_path_data.append(path_data)
                                print(f"  Fixed invalid polygon {path_data['index']}")
                            else:
                                print(f"  Skipping invalid polygon {path_data['index']}")
                    except Exception as e:
                        print(f"  Error creating polygon {path_data['index']}: {e}")
            
            print(f"  Created {len(polygons)} valid polygons from {len(closed_paths)} closed paths")
            
            # 🛠️ THE MISSING LINK: Send polygons through the repair pipeline
            # This triggers the buffer(0) and simplify(0.02) logic
            if polygons and HAS_SHAPELY:
                print(f"🛠️ REPAIR: Sending {len(polygons)} polygons to Pipeline...")
                try:
                    polygons = PROCESSING_PIPELINE.process(polygons)
                    print(f"✓ Pipeline repair complete: {len(polygons)} repaired polygons")
                except Exception as e:
                    print(f"⚠️ Pipeline repair failed: {e}, continuing with original polygons")
            
            # Analyze containment relationships to identify outer vs inner boundaries
            containment_matrix = []
            for i, poly1 in enumerate(polygons):
                containment_row = []
                for j, poly2 in enumerate(polygons):
                    if i == j:
                        containment_row.append(False)
                    else:
                        # Check if poly1 is contained within poly2
                        try:
                            contained = poly2.contains(poly1.centroid) and poly1.area < poly2.area
                            containment_row.append(contained)
                        except Exception:
                            containment_row.append(False)
                containment_matrix.append(containment_row)
            
            # Classify boundaries based on containment
            for i, path_data in enumerate(valid_path_data):
                coords = path_data['coords']
                
                # Count how many polygons contain this one
                contained_by_count = sum(containment_matrix[i])
                
                if contained_by_count == 0:
                    # Not contained by any other polygon - this is an outer boundary
                    boundary = BoundaryInfo(coords, 'outer', boundary_id, is_closed=True)
                    self.boundaries.append(boundary)
                    self.outer_boundaries.append(boundary_id)
                    print(f"  Boundary {boundary_id}: OUTER (area: {boundary.area:.2f})")
                elif contained_by_count % 2 == 1:
                    # Contained by odd number of polygons - this is an inner boundary (hole)
                    boundary = BoundaryInfo(coords, 'inner', boundary_id, is_closed=True)
                    self.boundaries.append(boundary)
                    self.inner_boundaries.append(boundary_id)
                    print(f"  Boundary {boundary_id}: INNER (area: {boundary.area:.2f})")
                else:
                    # Contained by even number of polygons - this is an outer boundary (island within hole)
                    boundary = BoundaryInfo(coords, 'outer', boundary_id, is_closed=True)
                    self.boundaries.append(boundary)
                    self.outer_boundaries.append(boundary_id)
                    print(f"  Boundary {boundary_id}: OUTER within hole (area: {boundary.area:.2f})")
                
                boundary_id += 1
            
            print(f"✓ Boundary separation complete:")
            print(f"  Total boundaries: {len(self.boundaries)}")
            print(f"  Outer boundaries: {len(self.outer_boundaries)}")
            print(f"  Inner boundaries: {len(self.inner_boundaries)}")
            print(f"  Open paths (lines): {len(open_paths)}")
            
        except Exception as e:
            print(f"Error in boundary separation: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback: treat all paths as outer boundaries
            for i, path_data in enumerate(self.parsed_paths):
                # Handle both old format (list) and new format (dict)
                if isinstance(path_data, dict):
                    coords = path_data['coords']
                    is_closed = path_data.get('is_closed', True)
                else:
                    coords = path_data
                    is_closed = True
                boundary = BoundaryInfo(coords, 'outer', i, is_closed=is_closed)
                self.boundaries.append(boundary)
                self.outer_boundaries.append(i)
        
        print("=== BOUNDARY SEPARATION END ===")
    
    def _calculate_unified_scale_params(self):
        """Calculate unified scaling parameters for all boundaries combined"""
        if self._unified_scale_params is not None:
            return self._unified_scale_params
        
        print("CALCULATING UNIFIED SCALE PARAMETERS FOR ALL BOUNDARIES")
        
        if not self.boundaries:
            print("No boundaries available for unified scaling")
            self._unified_scale_params = {
                'scale': 1.0,
                'offset_x': 0.0,
                'offset_y': 0.0,
                'svg_width': 0.0,
                'svg_height': 0.0
            }
            return self._unified_scale_params
        
        # Collect ALL coordinates from ALL boundaries
        all_coords = []
        for boundary in self.boundaries:
            all_coords.extend(boundary.coordinates)
        
        if not all_coords:
            print("No coordinates available in boundaries")
            self._unified_scale_params = {
                'scale': 1.0,
                'offset_x': 0.0,
                'offset_y': 0.0,
                'svg_width': 0.0,
                'svg_height': 0.0
            }
            return self._unified_scale_params
        
        # Find bounding box of ALL boundaries combined
        min_x = min(coord[0] for coord in all_coords)
        max_x = max(coord[0] for coord in all_coords)
        min_y = min(coord[1] for coord in all_coords)
        max_y = max(coord[1] for coord in all_coords)
        
        svg_width = max_x - min_x
        svg_height = max_y - min_y
        
        print(f"  Combined bounding box: {min_x:.1f},{min_y:.1f} to {max_x:.1f},{max_y:.1f}")
        print(f"  Combined dimensions: {svg_width:.1f} x {svg_height:.1f} units")
        
        if svg_width == 0 or svg_height == 0:
            print("WARNING: Combined boundaries have zero dimensions")
            self._unified_scale_params = {
                'scale': 1.0,
                'offset_x': 0.0,
                'offset_y': 0.0,
                'svg_width': 0.0,
                'svg_height': 0.0
            }
            return self._unified_scale_params
        
        # Use natural SVG dimensions converted to mm
        target_width_mm = svg_width * self.svg_parser.pixel_to_mm
        target_height_mm = svg_height * self.svg_parser.pixel_to_mm
        
        # Calculate scale
        scale_x = target_width_mm / svg_width
        scale_y = target_height_mm / svg_height
        scale = (scale_x + scale_y) / 2  # Average for consistency
        
        # Calculate offset to center on bed
        scaled_width = svg_width * scale
        scaled_height = svg_height * scale
        
        center_x = getattr(self, 'center_x', self.config.bed_size_x / 2)
        center_y = getattr(self, 'center_y', self.config.bed_size_y / 2)
        
        offset_x = center_x - scaled_width / 2 - min_x * scale
        
        # Proper Y-axis conversion from SVG (Y-down) to 3D printer (Y-up)
        offset_y = center_y + scaled_height / 2 + min_y * scale
        
        self._unified_scale_params = {
            'scale': scale,
            'offset_x': offset_x,
            'offset_y': offset_y,
            'svg_width': svg_width,
            'svg_height': svg_height,
            'min_x': min_x,
            'min_y': min_y,
            'target_width_mm': target_width_mm,
            'target_height_mm': target_height_mm
        }
        
        print(f"  UNIFIED SCALE PARAMS:")
        print(f"    Scale: {scale:.4f}")
        print(f"    Offset X: {offset_x:.2f}mm")
        print(f"    Offset Y: {offset_y:.2f}mm")
        print(f"    Target size: {target_width_mm:.1f} x {target_height_mm:.1f}mm")
        
        return self._unified_scale_params
    
    def _apply_unified_scaling(self, coordinates: List[List[float]]) -> List[List[float]]:
        """Apply unified scaling to coordinates to preserve spatial relationships"""
        if not coordinates:
            return coordinates
        
        # Get unified scaling parameters
        params = self._calculate_unified_scale_params()
        
        # Apply unified scaling and centering with Y-flip
        scaled_coords = []
        for coord in coordinates:
            scaled_x = coord[0] * params['scale'] + params['offset_x']
            # Flip Y-axis for proper coordinate conversion
            scaled_y = params['offset_y'] - (coord[1] * params['scale'])
            scaled_coords.append([scaled_x, scaled_y])
        
        return scaled_coords
    
    def _convert_mm_to_svg_units(self, mm_distance: float) -> float:
        """
        Convert millimeter distance to SVG coordinate units
        This ensures wall offsets are applied correctly in SVG space before scaling
        """
        # Get unified scaling parameters
        params = self._calculate_unified_scale_params()
        
        # Convert mm back to SVG units using the scale factor
        # scale converts SVG units to mm, so we reverse it
        svg_units = mm_distance / params['scale']
        
        print(f"    Converting {mm_distance}mm to {svg_units:.4f} SVG units (scale={params['scale']:.4f})")
        return svg_units
    
    def _calculate_shape_info(self):
        """Calculate shape information (printer-agnostic)"""
        
        # Get desired height
        desired_height = None
        
        # Check shape settings for totalHeight first (direct control)
        if self.shape_settings and 'totalHeight' in self.shape_settings:
            desired_height = self.shape_settings['totalHeight']
            print(f"Using totalHeight from shape settings: {desired_height}mm")
        
        # Check config for direct height settings
        if hasattr(self.config, 'config'):
            if 'desiredPrintHeight' in self.config.config:
                desired_height = self.config.config['desiredPrintHeight']
                print(f"Using desiredPrintHeight from config: {desired_height}mm")
            elif 'totalHeight' in self.config.config:
                desired_height = self.config.config['totalHeight']
                print(f"Using totalHeight from config: {desired_height}mm")
        
        # Use SVG's natural dimensions
        if self.shape_settings and 'width' in self.shape_settings and 'height' in self.shape_settings:
            # Explicit dimensions provided
            self.shape_width = self.shape_settings['width']
            self.shape_height = self.shape_settings['height']
            print(f"Using explicit shape dimensions: {self.shape_width}x{self.shape_height}mm")
        elif self.svg_content:
            # Use SVG's natural dimensions instead of forcing bed size
            svg_width_mm, svg_height_mm = self.svg_parser.get_svg_dimensions(self.svg_content)
            if svg_width_mm > 0 and svg_height_mm > 0:
                self.shape_width = svg_width_mm
                self.shape_height = svg_height_mm
                print(f"✓ Using SVG natural dimensions: {self.shape_width:.1f}x{self.shape_height:.1f}mm")
                
                # Check if SVG exceeds bed size and warn
                if self.shape_width > self.config.bed_size_x or self.shape_height > self.config.bed_size_y:
                    print(f"WARNING: SVG ({self.shape_width:.1f}x{self.shape_height:.1f}mm) exceeds bed size ({self.config.bed_size_x}x{self.config.bed_size_y}mm)")
            else:
                # Fallback to bed dimensions only if SVG dimensions can't be determined
                bed_usage_percent = getattr(self.config, 'config', {}).get('bedUsagePercent', 50) / 100.0
                self.shape_width = self.config.bed_size_x * bed_usage_percent
                self.shape_height = self.config.bed_size_y * bed_usage_percent
                print(f"Fallback to bed dimensions: {self.shape_width:.1f}x{self.shape_height:.1f}mm ({bed_usage_percent*100:.0f}% bed usage)")
        else:
            # No SVG, use bed dimensions with reduced usage percentage
            bed_usage_percent = getattr(self.config, 'config', {}).get('bedUsagePercent', 50) / 100.0
            self.shape_width = self.config.bed_size_x * bed_usage_percent
            self.shape_height = self.config.bed_size_y * bed_usage_percent
            print(f"No SVG - using bed dimensions: {self.shape_width:.1f}x{self.shape_height:.1f}mm ({bed_usage_percent*100:.0f}% bed usage)")
        
        # If no direct height specified, calculate from layers
        if desired_height is None:
            if self.layers:
                enabled_layers = [layer for layer in self.layers if layer.get('enabled', False)]
                if enabled_layers:
                    desired_height = sum(layer.get('height', 0) for layer in enabled_layers)
                    print(f"Calculated height from enabled layers: {desired_height}mm")
        
        # Final fallback from JSON algorithm settings - no hardcoded defaults
        if desired_height is None or desired_height <= 0:
            algorithm_settings = self.config.get_algorithm_settings()
            if 'fallbackPrintHeight' not in algorithm_settings:
                raise KeyError("algorithmSettings missing 'fallbackPrintHeight' - required when no other height specified")
            desired_height = algorithm_settings['fallbackPrintHeight']
            print(f"Using JSON algorithm fallback height: {desired_height}mm")
        
        # Set final height
        self.total_height = desired_height
        
        # Set first layer height
        layer_settings = self.config.get_layer_settings()
        self.first_layer_height = layer_settings.get('firstLayerHeight', 0.5)
        
        # Center position
        center_settings = getattr(self.config, 'config', {}).get('centerSettings', {})
        self.center_x = center_settings.get('x', self.config.bed_size_x / 2)
        self.center_y = center_settings.get('y', self.config.bed_size_y / 2)
        
        print(f"FINAL DIMENSIONS: {self.shape_width:.1f}x{self.shape_height:.1f}x{self.total_height:.1f}mm")
    
    # =====================================================
    # ZIGZAG SANDWICH PANEL SUPPORT - ALL FROM JSON
    # =====================================================
    
    def _should_apply_zigzag_to_wall(self, wall_index: int, total_walls: int) -> bool:
        """
        Determine if zigzag should be applied to this wall based on JSON settings
        Applies wave to wall index 1 for 2, 3, and 4 wall configurations

        Args:
            wall_index: Current wall (0-based: 0=outermost, 1=second, etc.)
            total_walls: Total walls for this layer

        Returns:
            True if zigzag should be applied to this wall
        """
        print(f"🔍 DEBUG: _should_apply_zigzag_to_wall(wall_index={wall_index}, total_walls={total_walls})")
        
        # Check JSON settings - no hardcoded defaults
        enabled = self.zigzag_settings.get('enabled', False)
        print(f"    zigzag enabled: {enabled}")
        if not enabled:
            print(f"    ❌ Wave NOT applied: zigzag disabled")
            return False

        # Get strategy from JSON
        apply_to_middle = self.zigzag_settings.get('applyToMiddleWallsOnly', True)
        print(f"    applyToMiddleWallsOnly: {apply_to_middle}")

        if not apply_to_middle:
            print(f"    ✅ WAVE APPLIED: applyToMiddleWallsOnly=False -> Apply to ALL walls")
            return True  # Apply to ALL walls when this setting is False

        # Apply wave to wall index 1 for 2, 3, or 4 walls
        # OR apply to wall index 0 for 1 wall (the only wall)
        # 1 wall: only wall (0) with wave
        # 2 walls: outer (0) + inner with wave (1)
        # 3 walls: outer (0) + middle with wave (1) + inner (2)
        # 4 walls: outer (0) + second with wave (1) + third (2) + inner (3)
        if total_walls == 1:
            result = wall_index == 0
            print(f"    1 wall: wall_index {wall_index} {'✅ WAVE APPLIED' if result else '❌ NOT applied'}")
            return result
        if total_walls >= 2 and total_walls <= 4:
            result = wall_index == 1
            print(f"    {total_walls} walls: wall_index {wall_index} {'✅ WAVE APPLIED' if result else '❌ NOT applied'}")
            return result

        # For other wall counts: no wave
        print(f"    ❌ Wave NOT applied: {total_walls} walls not supported")
        return False
    
    def _apply_zigzag_to_coordinates(self, coords: List[List[float]], 
                                     current_z: Optional[float] = None,
                                     total_height: Optional[float] = None) -> List[List[float]]:
        """
        Apply WAVE (sine) pattern to coordinates - ALL SETTINGS FROM JSON
        
        Creates a smooth sine wave instead of sharp zigzag angles.
        Supports variable amplitude based on Z height (tapered waves).
        
        Args:
            coords: Original coordinates
            current_z: Current Z height (optional, for variable amplitude)
            total_height: Total print height (optional, for variable amplitude)
        
        Returns:
            Coordinates with wave pattern applied
        """
        if not coords or len(coords) < 2:
            return coords
        
        # Get parameters from JSON - no hardcoded defaults
        wavelength_mm = self.zigzag_settings.get('wavelength')
        
        # NEW: Variable amplitude settings
        variable_amplitude = self.zigzag_settings.get('variableAmplitude', False)
        amplitude_start = self.zigzag_settings.get('amplitudeStart')
        amplitude_end = self.zigzag_settings.get('amplitudeEnd')
        
        # NEW: Variable wave bias settings
        wave_bias_start = self.zigzag_settings.get('waveBiasStart', 0.0)
        wave_bias_end = self.zigzag_settings.get('waveBiasEnd', wave_bias_start)
        
        # Validation
        if wavelength_mm is None or amplitude_start is None:
            print("    ERROR: zigzagSettings missing wavelength or amplitudeStart")
            return coords
        
        # If amplitudeEnd not specified, use amplitudeStart (constant amplitude)
        if amplitude_end is None:
            amplitude_end = amplitude_start
        
        # Calculate amplitude based on Z height if variable amplitude enabled
        if variable_amplitude and current_z is not None and total_height is not None and total_height > 0:
            z_progress = current_z / total_height
            amplitude_mm = amplitude_start + (amplitude_end - amplitude_start) * z_progress
            wave_bias_mm = wave_bias_start + (wave_bias_end - wave_bias_start) * z_progress
            print(f"    🌊 Variable amplitude: Z={current_z:.1f}mm ({z_progress*100:.0f}%) → amplitude={amplitude_mm:.2f}mm, bias={wave_bias_mm:.2f}mm")
        else:
            # Use constant amplitude (amplitudeStart)
            amplitude_mm = amplitude_start
            wave_bias_mm = wave_bias_start
            if variable_amplitude:
                print(f"    ⚠️ Variable amplitude enabled but Z info missing - using constant amplitude={amplitude_mm}mm, bias={wave_bias_mm}mm")
        
        # Calculate total path length
        total_length = 0.0
        for i in range(len(coords) - 1):
            dx = coords[i+1][0] - coords[i][0]
            dy = coords[i+1][1] - coords[i][1]
            total_length += math.sqrt(dx*dx + dy*dy)
        
        # Check if path is closed (circle/polygon)
        is_closed = (len(coords) >= 3 and 
                    abs(coords[0][0] - coords[-1][0]) < 0.01 and 
                    abs(coords[0][1] - coords[-1][1]) < 0.01)
        
        # For closed paths: adjust wavelength to fit complete cycles (prevents seam hook)
        if is_closed and total_length > 0:
            num_cycles = round(total_length / wavelength_mm)
            if num_cycles < 1:
                num_cycles = 1
            adjusted_wavelength = total_length / num_cycles
            print(f"    Closed path: adjusting wavelength {wavelength_mm:.2f}mm → {adjusted_wavelength:.2f}mm ({num_cycles} complete cycles)")
            wavelength_mm = adjusted_wavelength
        
        # Get wave type
        wave_type = self.zigzag_settings.get('waveType', 'sine').lower()
        
        def calculate_wave_value(phase_radians):
            if wave_type == 'square':
                return 1.0 if (phase_radians % (2 * math.pi)) < math.pi else -1.0
            else:
                return math.sin(phase_radians)
        
        if wave_bias_mm != 0.0:
            print(f"    Applying wave ({wave_type}): wavelength={wavelength_mm}mm, amplitude={amplitude_mm}mm, bias={wave_bias_mm}mm")
        else:
            print(f"    Applying wave ({wave_type}): wavelength={wavelength_mm}mm, amplitude={amplitude_mm}mm")
        
        if total_length < wavelength_mm:
            print(f"    Path too short for wave ({total_length:.1f}mm < {wavelength_mm}mm)")
            return coords
        
        # Calculate wave segments - read from JSON settings
        points_per_wavelength = self.zigzag_settings.get('pointsPerWavelength')
        if points_per_wavelength is None:
            print("    ERROR: zigzagSettings missing pointsPerWavelength")
            return coords
        
        segment_length = wavelength_mm / points_per_wavelength
        num_segments = int(total_length / segment_length)
        
        if num_segments < 2:
            return coords
        
        wave_coords = []
        current_distance = 0.0
        
        # Start point - apply wave offset for seamless closed paths
        if len(coords) >= 2:
            # Calculate tangent at start
            dx = coords[1][0] - coords[0][0]
            dy = coords[1][1] - coords[0][1]
            seg_len = math.sqrt(dx*dx + dy*dy)
            tangent = [dx / seg_len, dy / seg_len] if seg_len > 0 else [1, 0]
            
            # Perpendicular vector (90° rotation)
            perp = [-tangent[1], tangent[0]]
            
            # Phase at distance 0
            phase = 0
            offset = amplitude_mm * calculate_wave_value(phase) + wave_bias_mm
            
            # Apply wave offset to first point
            first_point = [
                coords[0][0] + perp[0] * offset,
                coords[0][1] + perp[1] * offset
            ]
            wave_coords.append(first_point)
        else:
            wave_coords.append(coords[0])
        
        # Generate wave points
        while current_distance < total_length:
            current_distance += segment_length
            
            if current_distance > total_length:
                current_distance = total_length
            
            # Find point at current_distance along path
            accumulated = 0.0
            point = None
            tangent = None
            
            for i in range(len(coords) - 1):
                dx = coords[i+1][0] - coords[i][0]
                dy = coords[i+1][1] - coords[i][1]
                seg_len = math.sqrt(dx*dx + dy*dy)
                
                if accumulated + seg_len >= current_distance:
                    # Point is on this segment
                    t = (current_distance - accumulated) / seg_len if seg_len > 0 else 0
                    point = [
                        coords[i][0] + t * dx,
                        coords[i][1] + t * dy
                    ]
                    # Tangent direction (normalized)
                    tangent = [dx / seg_len, dy / seg_len] if seg_len > 0 else [1, 0]
                    break
                
                accumulated += seg_len
            
            if point is None:
                point = coords[-1]
                if len(coords) >= 2:
                    dx = coords[-1][0] - coords[-2][0]
                    dy = coords[-1][1] - coords[-2][1]
                    seg_len = math.sqrt(dx*dx + dy*dy)
                    tangent = [dx / seg_len, dy / seg_len] if seg_len > 0 else [1, 0]
                else:
                    tangent = [1, 0]
            
            # Perpendicular vector (90° rotation)
            perp = [-tangent[1], tangent[0]]
            
            # Apply WAVE offset using wave function with bias
            # Phase: how far along the wave cycle (0 to 2π per wavelength)
            # Bias: shift the wave inward (negative) or outward (positive)
            phase = (current_distance / wavelength_mm) * 2 * math.pi
            offset = amplitude_mm * calculate_wave_value(phase) + wave_bias_mm
            
            wave_point = [
                point[0] + perp[0] * offset,
                point[1] + perp[1] * offset
            ]
            
            wave_coords.append(wave_point)
        
        # Close the path if it was originally closed
        if is_closed and len(wave_coords) > 0:
            wave_coords.append(wave_coords[0])
        
        print(f"    Generated {len(wave_coords)} wave points from {len(coords)} original points")
        return wave_coords
    
    # =====================================================
    # MAIN COORDINATE GENERATION WITH ZIGZAG SUPPORT
    # =====================================================
    
    def get_shape_info(self) -> Dict[str, Any]:
        """Get shape information with boundary separation details and corner rounding info"""
        return {
            'shape_width': self.shape_width if hasattr(self, 'shape_width') else 0,
            'shape_height': self.shape_height if hasattr(self, 'shape_height') else 0,
            'total_height': self.total_height if hasattr(self, 'total_height') else 0,
            'center_x': self.center_x if hasattr(self, 'center_x') else 0,
            'center_y': self.center_y if hasattr(self, 'center_y') else 0,
            'first_layer_height': getattr(self, 'first_layer_height', self.config.get_layer_settings()['firstLayerHeight']),
            'svg_parsed': len(self.parsed_paths) > 0,
            'paths_count': len(self.parsed_paths),
            'shapely_integrated': HAS_SHAPELY,
            'direct_shapely': True,
            'buffer_direction_fixed': True,
            'winding_handler_integrated': HAS_WINDING_HANDLER,
            'boundary_separation': True,
            'total_boundaries': len(self.boundaries),
            'outer_boundaries': len(self.outer_boundaries),
            'inner_boundaries': len(self.inner_boundaries),
            'coordinate_transformation_fixed': True,
            'wall_offset_fixed': True,
            'infill_scaling_fixed': True,
            'printer_agnostic': True,
            'configurable_mappings': True,
            'discovery_separated': True,
            'external_registry': True,
            'clean_signatures': True,
            'json_driven': True,
            'step7_compat_fix': True,
            'corner_rounding_enabled': self.corner_rounder.is_rounded_corners_enabled(),
            'corner_radius': self.corner_rounder.corner_radius if self.corner_rounder.is_rounded_corners_enabled() else 0,
            'curve_resolution': self.corner_rounder.curve_resolution,
            'corner_rounding_source': 'json_configuration_no_hardcoded_values',
            'zigzag_enabled': self.zigzag_settings.get('enabled', False),
            'zigzag_sandwich_panel': self.zigzag_settings.get('applyToMiddleWallsOnly', False),
            'split_architecture': True,
            'architecture_version': 'v4.2.0_zigzag_sandwich_4wall_fixed'
        }
    
    def get_all_boundaries(self) -> List[BoundaryInfo]:
        """Get all boundaries (outer and inner) for multi-boundary printing"""
        return self.boundaries
    
    def get_boundary_coordinates(self, boundary_id: int) -> List[List[float]]:
        """Get coordinates for a specific boundary with unified scaling"""
        if 0 <= boundary_id < len(self.boundaries):
            boundary = self.boundaries[boundary_id]
            coords = boundary.coordinates
            
            # Apply unified scaling that preserves spatial relationships
            scaled_coords = self._apply_unified_scaling(coords)
            return scaled_coords
        
        print(f"WARNING: Invalid boundary ID {boundary_id}")
        return []
    
    def get_path_coordinates(self) -> List[List[float]]:
        """Get path coordinates from SVG - returns first outer boundary for backwards compatibility"""
        # For backwards compatibility, return the first outer boundary
        if self.outer_boundaries:
            return self.get_boundary_coordinates(self.outer_boundaries[0])
        
        # Fallback behavior
        if self.parsed_paths:
            print(f"✓ Using REAL SVG path with {len(self.parsed_paths)} paths")
            
            # Use the first path with unified scaling
            first_path_data = self.parsed_paths[0]
            # Handle both old format (list) and new format (dict)
            if isinstance(first_path_data, dict):
                first_path = first_path_data['coords']
            else:
                first_path = first_path_data
            scaled_coords = self._apply_unified_scaling(first_path)
            
            print(f"SUCCESS: Using SVG natural dimensions with coordinate transformation")
            return scaled_coords
        
        # FALLBACK: Only if no SVG data at all
        print("WARNING: No SVG paths available, using fallback rectangle")
        return self._get_fallback_rectangle()
    
    def get_offset_path_coordinates(self, wall_index: int = 1, layer_name: str = None, 
                                   boundary_id: Optional[int] = None,
                                   total_walls: int = 1,
                                   current_z: Optional[float] = None) -> List[List[float]]:
        """
        Generate wall offset path coordinates with ZIGZAG SANDWICH PANEL SUPPORT
        
        NEW in v4.2.0: Applies zigzag to middle walls based on JSON settings
        Creates sandwich structure: outer (straight) + middle (zigzag) + inner (straight)
        
        FIXED: 4 walls now use 0.4mm offset (only 3 walls use 1.5mm zigzag offset)
        
        Args:
            wall_index: Wall number (1-based, 1=outermost)
            layer_name: Layer name for context
            boundary_id: Specific boundary to process
            total_walls: Total number of walls for zigzag logic
            current_z: Current Z height (optional, for variable amplitude waves)
        
        Returns:
            List of [x, y] coordinates for this wall
        """
        # ✅ FIXED: Changed >= 3 to == 3
        # Choose wall offset based on zigzag requirements - ALL FROM JSON
        if total_walls == 3 and self.zigzag_settings.get('enabled', False):
            # Use wider offset for zigzag sandwich panels (ONLY for 3 walls)
            wall_offset = self.wall_settings.get('zigzagWallOffset')
            if wall_offset is None:
                # Fallback to wallOffset if zigzagWallOffset not defined
                wall_offset = self.wall_settings.get('wallOffset')
                if wall_offset is None:
                    raise KeyError("wallSettings missing 'zigzagWallOffset' or 'wallOffset' - required in JSON")
        else:
            # Use normal tight offset for 2 walls, 4 walls, or no zigzag
            wall_offset = self.wall_settings.get('normalWallOffset')
            if wall_offset is None:
                # Fallback to wallOffset if normalWallOffset not defined
                wall_offset = self.wall_settings.get('wallOffset')
                if wall_offset is None:
                    raise KeyError("wallSettings missing 'normalWallOffset' or 'wallOffset' - required in JSON")
        
        if boundary_id is not None:
            target_boundary_id = boundary_id
        else:
            if self.outer_boundaries:
                target_boundary_id = self.outer_boundaries[0]
            else:
                target_boundary_id = 0 if self.boundaries else None
        
        cache_key = f"wall_{wall_index}_offset_{wall_offset}_{layer_name or 'unknown'}_{target_boundary_id}_zigzag_{total_walls}_comp_{self.wall_settings.get('firstLayerCompensation', 0.0)}_z_{current_z}"
        if cache_key in self._wall_coordinates_cache:
            return self._wall_coordinates_cache[cache_key]
        
        # ⭐ CRITICAL: Get base polygon FIRST for compensation (before wall_index checks)
        base_polygon = None
        first_layer_compensation = self.wall_settings.get('firstLayerCompensation', 0.0)
        
        # Only get polygon if we have Shapely and either need compensation or wall offsets
        if HAS_SHAPELY and (first_layer_compensation != 0.0 or wall_index > 0):
            base_polygon = self._get_boundary_polygon(target_boundary_id)
            
            if base_polygon and base_polygon.is_valid:
                if HAS_WINDING_HANDLER:
                    # Handle MultiPolygon case - extract largest polygon before winding fix
                    if isinstance(base_polygon, MultiPolygon):
                        print(f"    MultiPolygon detected with {len(base_polygon.geoms)} parts - using largest")
                        base_polygon = max(base_polygon.geoms, key=lambda p: p.area)
                    base_polygon = fix_winding_for_format(base_polygon, "default")
                
                # ⭐ FIRST LAYER COMPENSATION - Apply base compensation to polygon BEFORE anything else
                # This compensation applies equally to ALL walls including wall 0 (not multiplied by wall_index)
                if first_layer_compensation != 0.0:
                    print(f"    🔧 PathProcessor: Applying compensation {first_layer_compensation}mm to base polygon (wall {wall_index})")
                    compensation_svg = self._convert_mm_to_svg_units(first_layer_compensation)
                    
                    # Determine boundary type for correct buffer direction
                    boundary_type = 'outer'
                    if target_boundary_id is not None and target_boundary_id < len(self.boundaries):
                        boundary_type = self.boundaries[target_boundary_id].boundary_type
                    
                    print(f"    🔧 Boundary type: {boundary_type}, compensation_svg: {compensation_svg}")
                    
                    # Apply compensation to base polygon
                    # For outer boundaries: negative buffer = shrink inward (positive compensation = smaller part)
                    # For inner boundaries: positive buffer = expand outward (positive compensation = larger hole)
                    if boundary_type == 'inner' or (layer_name and 'inside' in layer_name.lower()):
                        base_polygon = base_polygon.buffer(+compensation_svg, resolution=self.svg_parser.curve_resolution, join_style=1)
                    else:
                        base_polygon = base_polygon.buffer(-compensation_svg, resolution=self.svg_parser.curve_resolution, join_style=1)
                    
                    # Check if compensation made polygon invalid or empty
                    if base_polygon.is_empty or not base_polygon.is_valid:
                        print(f"    ⚠️  WARNING: First layer compensation {first_layer_compensation}mm made polygon invalid/empty")
                        base_polygon = None
        
        # Now handle wall_index == 0 with potentially compensated polygon
        if wall_index == 0:
            if base_polygon and base_polygon.is_valid:
                # Use compensated polygon for wall 0
                coords = self._extract_polygon_coordinates_with_unified_scaling(base_polygon)
                
                # ============================================================
                # SEAM SELECTOR INTEGRATION - Apply manual seam rotation to base wall
                # ============================================================
                seam_selections = self.config.config.get('seamSelections', {})
                if seam_selections and str(target_boundary_id) in seam_selections:
                    start_vertex = seam_selections[str(target_boundary_id)]
                    
                    # Simple: just the vertex index
                    print(f"  🎯 Manual seam: polygon {target_boundary_id}, wall 0, starting at vertex {start_vertex}")
                    
                    # Rotate coordinates to start at selected vertex
                    coords = self._rotate_coords_to_vertex(coords, start_vertex)
                    
                    # Store base wall start position for offset walls to reference
                    if coords:
                        self._base_seam_start_positions[target_boundary_id] = coords[0]
                        print(f"  📍 Stored base seam position: ({coords[0][0]:.2f}, {coords[0][1]:.2f})")

                self._wall_coordinates_cache[cache_key] = coords
                return coords
            else:
                # Fallback to original coordinates if no compensation or polygon failed
                if target_boundary_id is not None:
                    coords = self.get_boundary_coordinates(target_boundary_id)
                else:
                    coords = self.get_path_coordinates()
                self._wall_coordinates_cache[cache_key] = coords
                return coords
        
        # For wall_index > 0, we need to apply wall offsets
        if not HAS_SHAPELY or not base_polygon or not base_polygon.is_valid:
            if target_boundary_id is not None:
                coords = self.get_boundary_coordinates(target_boundary_id)
            else:
                coords = self.get_path_coordinates()
            self._wall_coordinates_cache[cache_key] = coords
            return coords
        
        # base_polygon is already compensated at this point if needed
        try:
            svg_offset_distance = self._convert_mm_to_svg_units(wall_offset * wall_index)
            
            boundary_type = 'outer'
            if target_boundary_id is not None and target_boundary_id < len(self.boundaries):
                boundary_type = self.boundaries[target_boundary_id].boundary_type
            
            if boundary_type == 'inner' or (layer_name and 'inside' in layer_name.lower()):
                offset_polygon = base_polygon.buffer(+svg_offset_distance, resolution=self.svg_parser.curve_resolution, join_style=1)
                offset_polygon = offset_polygon.simplify(tolerance=0.1, preserve_topology=True)
            else:
                offset_polygon = base_polygon.buffer(-svg_offset_distance, resolution=self.svg_parser.curve_resolution, join_style=1)
                offset_polygon = offset_polygon.simplify(tolerance=0.05, preserve_topology=True)
            
            if offset_polygon.is_empty:
                coords = []
            elif isinstance(offset_polygon, MultiPolygon):
                largest_polygon = max(offset_polygon.geoms, key=lambda p: p.area)
                coords = self._extract_polygon_coordinates_with_unified_scaling(largest_polygon)
            else:
                coords = self._extract_polygon_coordinates_with_unified_scaling(offset_polygon)
            
            # ============================================================
            # SEAM SELECTOR INTEGRATION - Apply manual seam rotation to offset walls
            # FIX: Use closest vertex to base wall start position (not same vertex index)
            # ============================================================
            if coords:
                seam_selections = self.config.config.get('seamSelections', {})
                
                if seam_selections and str(target_boundary_id) in seam_selections:
                    # Check if we have a base wall start position stored
                    if target_boundary_id in self._base_seam_start_positions:
                        base_start_pos = self._base_seam_start_positions[target_boundary_id]
                        
                        # Find vertex on offset wall closest to base wall start position
                        closest_vertex_idx = self._find_closest_vertex_to_point(coords, base_start_pos)
                        
                        print(f"  🎯 Manual seam: polygon {target_boundary_id}, wall {wall_index}, "
                              f"aligned to base position ({base_start_pos[0]:.2f}, {base_start_pos[1]:.2f}) "
                              f"using vertex {closest_vertex_idx}")
                        
                        # Rotate coordinates to start at closest vertex
                        coords = self._rotate_coords_to_vertex(coords, closest_vertex_idx)

            # NEW: Apply zigzag to middle walls for sandwich panel structure
            # BUT: Skip zigzag for inner boundaries (holes)
            is_inner_boundary = False
            if target_boundary_id is not None and target_boundary_id < len(self.boundaries):
                boundary_type = self.boundaries[target_boundary_id].boundary_type
                is_inner_boundary = (boundary_type == 'inner')
            
            if coords and self._should_apply_zigzag_to_wall(wall_index, total_walls) and not is_inner_boundary:
                print(f"  Applying zigzag to wall {wall_index}/{total_walls} (middle wall - sandwich panel)")
                # Pass current_z and total_height for variable amplitude support
                total_height = self.total_height if hasattr(self, 'total_height') else None
                coords = self._apply_zigzag_to_coordinates(coords, current_z, total_height)
            elif is_inner_boundary:
                print(f"  Skipping zigzag for inner boundary (hole) - wall {wall_index}/{total_walls}")
            
            if coords:
                self._wall_coordinates_cache[cache_key] = coords
                return coords
            else:
                if target_boundary_id is not None:
                    coords = self.get_boundary_coordinates(target_boundary_id)
                else:
                    coords = self.get_path_coordinates()
                return coords
                
        except Exception as e:
            print(f"Error generating offset path: {e}")
            if target_boundary_id is not None:
                coords = self.get_boundary_coordinates(target_boundary_id)
            else:
                coords = self.get_path_coordinates()
            self._wall_coordinates_cache[cache_key] = coords
            return coords
    
    def _get_boundary_polygon(self, boundary_id: Optional[int]) -> Optional[Polygon]:
        """Get Shapely polygon for a specific boundary"""
        if not HAS_SHAPELY:
            return None
        
        try:
            if boundary_id is not None and 0 <= boundary_id < len(self.boundaries):
                path_coords = self.boundaries[boundary_id].coordinates
            else:
                if self.boundaries:
                    path_coords = self.boundaries[0].coordinates
                else:
                    return None
            
            if len(path_coords) < 3:
                return None
            
            polygon = Polygon(path_coords)
            
            if not polygon.is_valid:
                fixed_polygon = polygon.buffer(0)
                if fixed_polygon.is_valid:
                    polygon = fixed_polygon
                else:
                    return None
            
            return polygon
            
        except Exception as e:
            return None
    
    def _get_base_polygon(self) -> Optional[Polygon]:
        """Get base polygon for Shapely operations with caching"""
        if self._base_polygon_cache is not None:
            return self._base_polygon_cache
        
        boundary_id = self.outer_boundaries[0] if self.outer_boundaries else 0
        polygon = self._get_boundary_polygon(boundary_id)
        
        self._base_polygon_cache = polygon
        return polygon
    
    def _extract_polygon_coordinates_with_unified_scaling(self, polygon) -> List[List[float]]:
        """Extract coordinates from Shapely polygon and apply unified scaling"""
        try:
            if polygon.is_empty:
                return []
            
            coords = list(polygon.exterior.coords)
            coordinate_list = [[float(x), float(y)] for x, y in coords]
            scaled_coords = self._apply_unified_scaling(coordinate_list)
            
            return scaled_coords
            
        except Exception as e:
            return []
    
    def _extract_polygon_coordinates(self, polygon) -> List[List[float]]:
        """Extract coordinates from Shapely polygon (legacy method)"""
        return self._extract_polygon_coordinates_with_unified_scaling(polygon)
    
    def get_base_polygon_for_infill(self):
        """Get base polygon for infill generation with holes properly subtracted
        
        DEPRECATED: This function unions all outer polygons into one.
        Use get_base_polygons_for_infill() to keep them separate for independent infill control.
        """
        if not HAS_SHAPELY:
            return None
        
        try:
            outer_polygons = []
            for boundary_id in self.outer_boundaries:
                if boundary_id < len(self.boundaries):
                    boundary = self.boundaries[boundary_id]
                    raw_coords = boundary.coordinates
                    
                    if len(raw_coords) >= 3:
                        polygon = Polygon(raw_coords)
                        if polygon.is_valid:
                            outer_polygons.append(polygon)
                        else:
                            fixed_polygon = polygon.buffer(0)
                            if fixed_polygon.is_valid:
                                outer_polygons.append(fixed_polygon)
            
            if not outer_polygons:
                return None
            
            if len(outer_polygons) == 1:
                base_polygon = outer_polygons[0]
            else:
                base_polygon = unary_union(outer_polygons)
            
            inner_polygons = []
            for boundary_id in self.inner_boundaries:
                if boundary_id < len(self.boundaries):
                    boundary = self.boundaries[boundary_id]
                    raw_coords = boundary.coordinates
                    
                    if len(raw_coords) >= 3:
                        polygon = Polygon(raw_coords)
                        if polygon.is_valid:
                            inner_polygons.append(polygon)
                        else:
                            fixed_polygon = polygon.buffer(0)
                            if fixed_polygon.is_valid:
                                inner_polygons.append(fixed_polygon)
            
            if inner_polygons:
                holes_union = unary_union(inner_polygons)
                polygon_with_holes = base_polygon.difference(holes_union)
                
                if polygon_with_holes.is_valid and not polygon_with_holes.is_empty:
                    return polygon_with_holes
                else:
                    return base_polygon
            else:
                return base_polygon
            
        except Exception as e:
            return None
    
    def get_base_polygons_for_infill(self):
        """Get list of separate base polygons for infill generation
        
        🎯 NEW: Returns polygons as SEPARATE list (no union!)
        This allows each shape to have independent infill settings.
        Each polygon can have different density, pattern, etc.
        
        Returns:
            List[Polygon]: List of separate polygons, each with holes subtracted
        """
        if not HAS_SHAPELY:
            return []
        
        try:
            outer_polygons = []
            for boundary_id in self.outer_boundaries:
                if boundary_id < len(self.boundaries):
                    boundary = self.boundaries[boundary_id]
                    raw_coords = boundary.coordinates
                    
                    if len(raw_coords) >= 3:
                        polygon = Polygon(raw_coords)
                        if polygon.is_valid:
                            outer_polygons.append(polygon)
                        else:
                            fixed_polygon = polygon.buffer(0)
                            if fixed_polygon.is_valid:
                                outer_polygons.append(fixed_polygon)
            
            if not outer_polygons:
                return []
            
            # 🎯 NEW: Collect holes to subtract from each outer polygon
            inner_polygons = []
            for boundary_id in self.inner_boundaries:
                if boundary_id < len(self.boundaries):
                    boundary = self.boundaries[boundary_id]
                    raw_coords = boundary.coordinates
                    
                    if len(raw_coords) >= 3:
                        polygon = Polygon(raw_coords)
                        if polygon.is_valid:
                            inner_polygons.append(polygon)
                        else:
                            fixed_polygon = polygon.buffer(0)
                            if fixed_polygon.is_valid:
                                inner_polygons.append(fixed_polygon)
            
            # 🎯 NEW: Subtract holes from each outer polygon separately
            result_polygons = []
            
            if inner_polygons:
                holes_union = unary_union(inner_polygons)
                
                for outer_polygon in outer_polygons:
                    try:
                        polygon_with_holes = outer_polygon.difference(holes_union)
                        
                        if polygon_with_holes.is_valid and not polygon_with_holes.is_empty:
                            result_polygons.append(polygon_with_holes)
                        else:
                            result_polygons.append(outer_polygon)
                    except Exception as e:
                        print(f"      Warning: Could not subtract holes from polygon: {e}")
                        result_polygons.append(outer_polygon)
            else:
                # No holes, just return outer polygons
                result_polygons = outer_polygons
            
            print(f"      🎯 Returning {len(result_polygons)} SEPARATE polygons (no union!)")
            return result_polygons
            
        except Exception as e:
            print(f"      Error getting separate polygons: {e}")
            return []
    
    def get_infill_coordinate_params(self):
        """Get coordinate transformation parameters for infill generator"""
        params = self._calculate_unified_scale_params()
        
        return {
            'scale': params['scale'],
            'offset_x': params['offset_x'],
            'offset_y': params['offset_y'],
            'pixel_to_mm': self.svg_parser.pixel_to_mm,
            'svg_width': params['svg_width'],
            'svg_height': params['svg_height']
        }
    
    def get_base_polygon(self):
        """Create base polygon for infill generation"""
        return self.get_base_polygon_for_infill()
    
    def _get_fallback_rectangle(self) -> List[List[float]]:
        """Generate fallback rectangle from JSON algorithm settings"""
        algorithm_settings = self.config.get_algorithm_settings()
        
        if 'fallbackShapeWidth' not in algorithm_settings:
            raise KeyError("algorithmSettings missing 'fallbackShapeWidth'")
        if 'fallbackShapeHeight' not in algorithm_settings:
            raise KeyError("algorithmSettings missing 'fallbackShapeHeight'")
        
        fallback_width = algorithm_settings['fallbackShapeWidth']
        fallback_height = algorithm_settings['fallbackShapeHeight']
        
        half_width = fallback_width / 2
        half_height = fallback_height / 2
        
        center_x = getattr(self, 'center_x', self.config.bed_size_x / 2)
        center_y = getattr(self, 'center_y', self.config.bed_size_y / 2)
        
        coords = [
            [center_x - half_width, center_y - half_height],
            [center_x + half_width, center_y - half_height],
            [center_x + half_width, center_y + half_height],
            [center_x - half_width, center_y + half_height],
            [center_x - half_width, center_y - half_height]
        ]
        
        self.shape_width = fallback_width
        self.shape_height = fallback_height
        
        return coords
    
    # ============================================================
    # SEAM SELECTOR INTEGRATION - Coordinate Rotation Helpers
    # ============================================================
    def _rotate_coords_to_vertex(self, coords: List[List[float]], 
                                 vertex_index: int) -> List[List[float]]:
        """
        Rotate coordinates to start at specified vertex index (for manual seam selection)
        Handles closed polygons properly
        
        Args:
            coords: List of [x, y] coordinates
            vertex_index: Index to start from (0-based) - P2 START point from seam selector
        
        Returns:
            Rotated coordinates starting at vertex_index
        """
        if not coords or len(coords) < 3:
            return coords
        
        # Check if closed polygon (last point equals first point)
        is_closed = (coords[0] == coords[-1])
        
        if is_closed:
            # Remove closing point temporarily
            working_coords = coords[:-1]
            
            # Clamp vertex index to valid range
            if vertex_index >= len(working_coords):
                vertex_index = vertex_index % len(working_coords)
            
            # Rotate to start at vertex_index
            rotated = working_coords[vertex_index:] + working_coords[:vertex_index]
            
            # Re-close polygon
            rotated.append(rotated[0])
        else:
            # Open path - just rotate
            if vertex_index >= len(coords):
                vertex_index = vertex_index % len(coords)
            rotated = coords[vertex_index:] + coords[:vertex_index]
        
        return rotated
    
    def _find_closest_vertex_to_point(self, coords: List[List[float]], 
                                      target_point: List[float]) -> int:
        """
        Find index of vertex closest to target XY point
        Used for aligning offset walls to same seam position
        
        Args:
            coords: List of [x, y] coordinates
            target_point: [x, y] target position
        
        Returns:
            Index of closest vertex
        """
        if not coords or not target_point:
            return 0
        
        min_dist = float('inf')
        closest_idx = 0
        
        # Check if closed polygon
        is_closed = len(coords) > 2 and (coords[0] == coords[-1])
        search_range = len(coords) - 1 if is_closed else len(coords)
        
        for i in range(search_range):
            dx = coords[i][0] - target_point[0]
            dy = coords[i][1] - target_point[1]
            dist = math.sqrt(dx*dx + dy*dy)
            
            if dist < min_dist:
                min_dist = dist
                closest_idx = i
        
        return closest_idx


# =====================================================
# LEGACY COMPATIBILITY FUNCTIONS
# =====================================================

def convert_html_json_to_full_config(html_json: Dict[str, Any], 
                                    printer_config_map: Optional[Dict[str, str]] = None,
                                    printer_registry: Optional[Any] = None) -> Dict[str, Any]:
    """
    Legacy compatibility wrapper with HTML settings override support
    
    Now properly handles:
    - zigzagSettings from HTML (wavelength, amplitude)
    - wallSettings from HTML (normalWallOffset, zigzagWallOffset)
    
    HTML values override JSON defaults when provided
    
    NOTE: This function previously called deleted code (PrinterRegistry, create_configuration_from_html).
    If you need HTML support, you must use PathProcessor.from_config_file() instead, or add back
    the deleted functions.
    """
    try:
        # TEMPORARY FIX: Return None since the original functions were deleted
        # This allows imports to work, but the function won't work if called
        print("WARNING: convert_html_json_to_full_config() called but original functions were deleted!")
        print("  This function needs PrinterRegistry and create_configuration_from_html to work.")
        print("  Use PathProcessor.from_config_file() instead, or add back deleted functions.")
        config = None
        
        if config is None:
            return None
        
        # Override zigzagSettings if provided in HTML
        if 'zigzagSettings' in html_json:
            html_zigzag = html_json['zigzagSettings']
            print(f"[HTML Override] Zigzag settings from HTML:")
            print(f"  wavelength: {html_zigzag.get('wavelength')}mm")
            print(f"  amplitude: {html_zigzag.get('amplitude')}mm")
            if 'waveBias' in html_zigzag:
                print(f"  waveBias: {html_zigzag.get('waveBias')}mm")
            
            # Update config with HTML values
            if 'zigzagSettings' not in config:
                config['zigzagSettings'] = {}
            
            config['zigzagSettings'].update({
                'wavelength': html_zigzag.get('wavelength', 5.0),
                'amplitude': html_zigzag.get('amplitude', 1.5),
                'waveBias': html_zigzag.get('waveBias', config['zigzagSettings'].get('waveBias', 0.0)),
                'enabled': html_zigzag.get('enabled', config['zigzagSettings'].get('enabled', True)),
                'applyToMiddleWallsOnly': html_zigzag.get('applyToMiddleWallsOnly', 
                                                         config['zigzagSettings'].get('applyToMiddleWallsOnly', True))
            })
        
        # Override wallSettings if provided in HTML
        if 'wallSettings' in html_json:
            html_walls = html_json['wallSettings']
            print(f"[HTML Override] Wall settings from HTML:")
            print(f"  normalWallOffset: {html_walls.get('normalWallOffset')}mm")
            print(f"  zigzagWallOffset: {html_walls.get('zigzagWallOffset')}mm")
            
            # Update config with HTML values
            if 'wallSettings' not in config:
                config['wallSettings'] = {}
            
            config['wallSettings'].update({
                'normalWallOffset': html_walls.get('normalWallOffset', 4.0),
                'zigzagWallOffset': html_walls.get('zigzagWallOffset', 1.5)
            })
        
        # ============================================================
        # SEAM SELECTOR INTEGRATION - Extract seamSelections from HTML
        # ============================================================
        if 'seamSelections' in html_json:
            seam_data = html_json['seamSelections']
            print(f'[HTML Override] Seam selections from HTML:')
            
            # Store in config for use during coordinate generation
            config['seamSelections'] = seam_data
            
            # Log what was received (simple format: {polygonIndex: vertexIndex})
            for poly_idx, vertex_idx in seam_data.items():
                print(f'  Polygon {poly_idx}: Seam at vertex {vertex_idx}')
            
            print(f'  Total polygons with seam selections: {len(seam_data)}')

        return config
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None
