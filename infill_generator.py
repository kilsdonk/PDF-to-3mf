#!/usr/bin/env python3
"""
Integrated Infill Generator - PART OF PATHPROCESSOR SYSTEM
Version: v3.3.0 - INTEGRATED LIKE WALL SYSTEM - STEP_6
- INTEGRATED: Works inside PathProcessor like walls do
- UNIFIED: Uses same coordinate transformation methods as walls
- DIRECT: Calls _convert_mm_to_svg_units() and _apply_unified_scaling() directly
- CONSISTENT: Same SVG→Shapely→coordinates pipeline as walls
- REMOVED: External coordinate parameter system
- ARCHITECTURE: Same pattern that fixed the wall system
- STEP_1: Added JSON configuration access with fallbacks
- STEP_2: Replace basic thresholds with JSON values
- STEP_3: Replace infill offset settings with JSON values
- STEP_4: Replace line spacing with JSON-calculated values
- STEP_5: Replace infill angles with JSON pattern settings
- STEP_6: Add layer-specific support from JSON layers array
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import Polygon, Point, LineString, box


class InfillGenerator:
    """
    INTEGRATED infill generator that works inside PathProcessor like the wall system
    Uses the same coordinate transformation pipeline that fixed the walls
    STEP_6: Now supports layer-specific infill settings from JSON layers array
    """
    
    def __init__(self, path_processor, line_spacing: float = 0.8, zhop_threshold: float = 5.0, 
                 infill_offset: float = 0.6, generate_outline: bool = False, 
                 printer_config: Dict[str, Any] = None):
        """
        Initialize INTEGRATED infill generator - STEP_6: Supports layer-specific settings
        
        Args:
            path_processor: PathProcessor instance (same one used for walls)
            line_spacing: Space between infill lines (mm) - FALLBACK if not in JSON
            zhop_threshold: Distance threshold for Z-hop travels (mm) - FALLBACK if not in JSON
            infill_offset: Distance to offset infill from walls (mm) - FALLBACK if not in JSON
            generate_outline: Whether to generate outline perimeter (usually False)
            printer_config: Full JSON printer configuration
        """
        self.path_processor = path_processor  # Direct access to PathProcessor methods
        
        # STEP_6: Store JSON configuration and extract layer-specific settings
        self.printer_config = printer_config or {}
        
        # STEP_2: Read zhop_threshold from JSON with fallback
        movement_settings = self.printer_config.get('movementSettings', {})
        self.zhop_threshold = movement_settings.get('zhopThreshold', zhop_threshold)
        
        # STEP_2: Read travel optimization thresholds from JSON with fallbacks
        algorithm_settings = self.printer_config.get('algorithmSettings', {})
        self.nearby_threshold = algorithm_settings.get('curveDetectionMaxSegmentLength', 2.0)
        self.area_jump_threshold = algorithm_settings.get('curveDetectionMaxSegmentLength', 2.0) * 5.0  # 5x curve length = jump threshold
        
        # STEP_3: Read infill offset settings from JSON with fallbacks
        infill_settings = self.printer_config.get('infillSettings', {})
        self.infill_offset = infill_settings.get('infillOffset', infill_offset)
        self.first_layer_infill_offset = infill_settings.get('firstLayerInfillOffset', self.infill_offset)
        
        # STEP_4: Calculate line spacing from JSON density and line width
        self.default_density = infill_settings.get('defaultDensity', 15)  # percentage
        self.default_line_width = infill_settings.get('defaultLineWidth', 0.45)  # mm
        self.default_pattern = infill_settings.get('defaultPattern', 'grid')
        
        # Calculate line spacing: spacing = line_width / (density / 100)
        if self.default_density > 0:
            self.line_spacing = self.default_line_width / (self.default_density / 100.0)
        else:
            self.line_spacing = line_spacing  # fallback if density is 0
        
        # STEP_5: Read infill angle settings from JSON with fallbacks
        self.default_base_angle = infill_settings.get('defaultBaseAngle', 45)  # degrees
        
        # STEP_6: Process layer-specific settings from JSON
        self.layers_config = self.printer_config.get('layers', [])
        self.layer_specific_enabled = self.printer_config.get('layerSettings', {}).get('layerSpecificEnabled', False)
        
        # Keep other parameters as fallbacks
        self.generate_outline = generate_outline
        
        print(f"INTEGRATED InfillGenerator initialized - SAME SYSTEM AS WALLS - STEP_6")
        
        # STEP_4: Show line spacing calculation
        if infill_settings.get('defaultDensity') is not None and infill_settings.get('defaultLineWidth') is not None:
            print(f"   STEP_4: Line spacing calculated from JSON:")
            print(f"     Density: {self.default_density}%")
            print(f"     Line width: {self.default_line_width}mm")
            print(f"     Calculated spacing: {self.line_spacing:.3f}mm ({self.default_line_width:.3f} / {self.default_density/100:.2f})")
        else:
            print(f"   Line spacing: {self.line_spacing}mm (fallback - JSON density/lineWidth not available)")
        
        # STEP_5: Show infill angle and pattern settings
        if infill_settings.get('defaultBaseAngle') is not None and infill_settings.get('defaultPattern') is not None:
            print(f"   STEP_5: Infill angles from JSON:")
            print(f"     Pattern: {self.default_pattern}")
            print(f"     Base angle: {self.default_base_angle}°")
            print(f"     Alternating angles: {self.default_base_angle}° / {self.default_base_angle + 90}°")
        else:
            print(f"   Infill angles: 0° / 90° (fallback - JSON pattern/angle not available)")
        
        # STEP_6: Show layer-specific configuration status
        if self.layers_config:
            enabled_layers = [layer for layer in self.layers_config if layer.get('enabled', True)]
            disabled_layers = [layer for layer in self.layers_config if not layer.get('enabled', True)]
            print(f"   STEP_6: Layer-specific support:")
            print(f"     Total layers defined: {len(self.layers_config)}")
            print(f"     Enabled layers: {len(enabled_layers)}")
            print(f"     Disabled layers: {len(disabled_layers)}")
            print(f"     Layer-specific processing: {self.layer_specific_enabled}")
            
            if enabled_layers:
                print(f"     Enabled layer names: {[layer.get('name', f'Layer{layer.get('index', 'Unknown')}') for layer in enabled_layers]}")
            if disabled_layers:
                print(f"     Disabled layer names: {[layer.get('name', f'Layer{layer.get('index', 'Unknown')}') for layer in disabled_layers]}")
        else:
            print(f"   STEP_6: No layer-specific configuration - using defaults for all layers")
        
        # STEP_2: Show which thresholds come from JSON vs fallback
        if movement_settings.get('zhopThreshold') is not None:
            print(f"   Z-hop threshold: {self.zhop_threshold}mm (from JSON movementSettings)")
        else:
            print(f"   Z-hop threshold: {self.zhop_threshold}mm (fallback - JSON not available)")
            
        if algorithm_settings.get('curveDetectionMaxSegmentLength') is not None:
            print(f"   Nearby threshold: {self.nearby_threshold}mm (from JSON algorithmSettings.curveDetectionMaxSegmentLength)")
            print(f"   Area jump threshold: {self.area_jump_threshold}mm (calculated: 5x curveDetectionMaxSegmentLength)")
        else:
            print(f"   Nearby threshold: {self.nearby_threshold}mm (fallback)")
            print(f"   Area jump threshold: {self.area_jump_threshold}mm (fallback)")
        
        # STEP_3: Show which infill offsets come from JSON vs fallback
        if infill_settings.get('infillOffset') is not None:
            print(f"   Infill offset: {self.infill_offset}mm (from JSON infillSettings.infillOffset)")
        else:
            print(f"   Infill offset: {self.infill_offset}mm (fallback - JSON not available)")
            
        if infill_settings.get('firstLayerInfillOffset') is not None:
            print(f"   First layer infill offset: {self.first_layer_infill_offset}mm (from JSON infillSettings.firstLayerInfillOffset)")
        else:
            print(f"   First layer infill offset: {self.first_layer_infill_offset}mm (fallback - using same as regular infill offset)")
        
        print(f"   Generate outline: {self.generate_outline}")
        print(f"   INTEGRATED: Uses PathProcessor coordinate methods directly")
        
        # STEP_6: Report JSON configuration status
        if self.printer_config:
            movement_available = 'movementSettings' in self.printer_config
            algorithm_available = 'algorithmSettings' in self.printer_config
            infill_available = 'infillSettings' in self.printer_config
            layers_available = 'layers' in self.printer_config
            infill_complete = all(key in infill_settings for key in ['defaultDensity', 'defaultLineWidth', 'defaultPattern'])
            angle_complete = all(key in infill_settings for key in ['defaultBaseAngle', 'defaultPattern'])
            print(f"   JSON CONFIG: movementSettings available: {movement_available}")
            print(f"   JSON CONFIG: algorithmSettings available: {algorithm_available}")
            print(f"   JSON CONFIG: infillSettings available: {infill_available}")
            print(f"   JSON CONFIG: layers configuration available: {layers_available}")
            print(f"   JSON CONFIG: infill calculation complete: {infill_complete}")
            print(f"   JSON CONFIG: angle configuration complete: {angle_complete}")
        else:
            print(f"   JSON CONFIG: No configuration provided - using hardcoded fallbacks")
    
    def get_layer_config(self, layer_num: int) -> Optional[Dict[str, Any]]:
        """
        STEP_6: Get layer-specific configuration from JSON layers array
        
        Args:
            layer_num: Current layer number (1-based)
            
        Returns:
            Layer configuration dict or None if not found
        """
        if not self.layers_config:
            return None
        
        # Try to find layer by index (layer_num - 1 for 0-based indexing)
        layer_index = layer_num - 1
        
        # First try to find by exact index match
        for layer_config in self.layers_config:
            if layer_config.get('index') == layer_index:
                return layer_config
        
        # Fallback: try to find by sequential position in array
        if 0 <= layer_index < len(self.layers_config):
            return self.layers_config[layer_index]
        
        return None
    
    def is_layer_enabled(self, layer_num: int) -> bool:
        """
        STEP_6: Check if a layer is enabled according to JSON configuration
        
        Args:
            layer_num: Current layer number (1-based)
            
        Returns:
            True if layer is enabled, False if disabled
        """
        layer_config = self.get_layer_config(layer_num)
        
        if layer_config is None:
            # No specific config found - assume enabled
            return True
        
        # Check enabled flag (default to True if not specified)
        return layer_config.get('enabled', True)
    
    def get_layer_angle(self, layer_num: int) -> float:
        """
        STEP_5: Get infill angle for layer using JSON-based pattern
        STEP_6: Now supports layer-specific angle overrides
        
        Args:
            layer_num: Current layer number
            
        Returns:
            Infill angle in degrees
        """
        # STEP_6: Check for layer-specific angle settings first
        layer_config = self.get_layer_config(layer_num)
        if layer_config and 'infillAngle' in layer_config:
            return layer_config['infillAngle']
        
        # Check if we have JSON configuration for angles
        infill_settings = self.printer_config.get('infillSettings', {})
        
        if infill_settings.get('defaultBaseAngle') is not None and infill_settings.get('defaultPattern') == 'grid':
            # STEP_5: Use JSON-based alternating pattern
            base_angle = self.default_base_angle
            
            if layer_num % 2 == 1:
                angle = base_angle  # Odd layers: base angle (45°)
            else:
                angle = base_angle + 90  # Even layers: base angle + 90° (135°)
            
            # Normalize angle to 0-180 range
            while angle >= 180:
                angle -= 180
            while angle < 0:
                angle += 180
                
            return angle
        else:
            # Fallback to original hardcoded pattern
            if layer_num % 2 == 1:
                return 0.0    # Odd layers: horizontal (0°)
            else:
                return 90.0   # Even layers: vertical (90°)
    
    def calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calculate distance between two points"""
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    
    def get_layer_line_spacing(self, layer_num: int, passed_line_spacing: float = None) -> float:
        """
        STEP_4: Get line spacing for specific layer - uses JSON calculated value or override
        STEP_6: Now supports layer-specific line spacing overrides
        
        Args:
            layer_num: Current layer number
            passed_line_spacing: Override spacing if provided
            
        Returns:
            Line spacing in mm
        """
        if passed_line_spacing is not None:
            print(f"         STEP_4: Using override line spacing: {passed_line_spacing}mm")
            return passed_line_spacing
        
        # STEP_6: Check for layer-specific line spacing first
        layer_config = self.get_layer_config(layer_num)
        if layer_config and 'lineSpacing' in layer_config:
            print(f"         STEP_6: Using layer-specific line spacing: {layer_config['lineSpacing']}mm")
            return layer_config['lineSpacing']
        
        # STEP_4: Use JSON-calculated line spacing
        print(f"         STEP_4: Using JSON-calculated line spacing: {self.line_spacing:.3f}mm (density {self.default_density}%)")
        return self.line_spacing
    
    def get_layer_infill_offsets(self, layer_num: int) -> Tuple[float, float]:
        """
        STEP_6: Get layer-specific infill offsets
        
        Args:
            layer_num: Current layer number
            
        Returns:
            Tuple of (regular_offset, first_layer_offset) in mm
        """
        # STEP_6: Check for layer-specific infill offset first
        layer_config = self.get_layer_config(layer_num)
        if layer_config:
            layer_offset = layer_config.get('infillOffset')
            layer_first_offset = layer_config.get('firstLayerInfillOffset')
            
            if layer_offset is not None or layer_first_offset is not None:
                regular = layer_offset if layer_offset is not None else self.infill_offset
                first = layer_first_offset if layer_first_offset is not None else self.first_layer_infill_offset
                print(f"         STEP_6: Using layer-specific infill offsets: regular={regular}mm, first={first}mm")
                return regular, first
        
        # Use default JSON-based settings
        return self.infill_offset, self.first_layer_infill_offset
    
    def find_best_connection(self, current_end: List[float], segments: List[List[List[float]]]) -> Tuple[int, bool]:
        """Find the best next segment to print based on minimum travel distance"""
        if not segments:
            return -1, False
        
        best_index = 0
        best_distance = float('inf')
        best_reverse = False
        
        for i, segment in enumerate(segments):
            if len(segment) < 2:
                continue
            
            # Calculate distance to start and end of segment
            dist_to_start = self.calculate_distance(
                current_end[0], current_end[1], segment[0][0], segment[0][1]
            )
            dist_to_end = self.calculate_distance(
                current_end[0], current_end[1], segment[-1][0], segment[-1][1]
            )
            
            # Choose the closer connection
            if dist_to_start <= dist_to_end:
                if dist_to_start < best_distance:
                    best_distance = dist_to_start
                    best_index = i
                    best_reverse = False
            else:
                if dist_to_end < best_distance:
                    best_distance = dist_to_end
                    best_index = i
                    best_reverse = True
        
        return best_index, best_reverse
    
    def optimize_infill_path(self, segments: List[List[List[float]]]) -> List[Tuple[str, List[List[float]]]]:
        """
        Optimize infill segments for minimal travel using nearest neighbor algorithm
        STEP_2: Now uses JSON-based thresholds
        """
        if not segments:
            return []
        
        print(f"         Optimizing {len(segments)} infill segments for minimal travel (STEP_2: using JSON thresholds)")
        
        unprinted_segments = segments.copy()
        optimized_paths = []
        
        # Start with the first segment
        current_segment = unprinted_segments.pop(0)
        current_end = current_segment[-1] if current_segment else [0, 0]
        optimized_paths.append(('linear_segment', current_segment))
        
        total_travel_distance = 0
        jump_count = 0
        
        # Process remaining segments using nearest neighbor
        while unprinted_segments:
            best_index, should_reverse = self.find_best_connection(current_end, unprinted_segments)
            
            if best_index == -1:
                break
            
            next_segment = unprinted_segments.pop(best_index)
            
            if should_reverse:
                next_segment = list(reversed(next_segment))
            
            # Calculate travel distance
            travel_distance = self.calculate_distance(
                current_end[0], current_end[1], 
                next_segment[0][0], next_segment[0][1]
            )
            total_travel_distance += travel_distance
            
            # STEP_2: Use JSON-based area_jump_threshold
            if travel_distance > self.area_jump_threshold:
                jump_count += 1
        
            optimized_paths.append(('linear_segment', next_segment))
            current_end = next_segment[-1]
        
        print(f"         Path optimization completed (STEP_2):")
        print(f"           Total travel distance: {total_travel_distance:.1f} units")
        print(f"           Long jumps (>{self.area_jump_threshold:.1f}): {jump_count}")
        
        return optimized_paths
    
    def create_infill_polygon_like_walls(self, base_polygon: Polygon, infill_offset_mm: float) -> Polygon:
        """
        INTEGRATED: Create infill polygon using the same method as walls
        Uses PathProcessor._convert_mm_to_svg_units() like the wall system does
        """
        try:
            # INTEGRATED: Use the same conversion method as walls
            svg_offset = self.path_processor._convert_mm_to_svg_units(infill_offset_mm)
            
            print(f"         INTEGRATED: Converting {infill_offset_mm}mm to {svg_offset:.4f} SVG units")
            
            # Use same Shapely buffer operation as walls
            infill_polygon = base_polygon.buffer(-svg_offset)
            
            if infill_polygon.is_empty:
                print(f"         Warning: Infill offset {infill_offset_mm}mm too large - no infill area")
                return None
            
            print(f"         INTEGRATED: Created infill polygon with {infill_offset_mm}mm clearance")
            return infill_polygon
            
        except Exception as e:
            print(f"         Error creating infill polygon: {e}")
            return base_polygon
    
    def generate_linear_infill_like_walls(self, polygon: Polygon, line_spacing_mm: float, 
                                         layer_angle: float) -> List[List[List[float]]]:
        """
        INTEGRATED: Generate linear infill using the same coordinate system as walls
        Uses PathProcessor._convert_mm_to_svg_units() like the wall system does
        STEP_5: Now supports JSON-based angles including diagonal patterns
        """
        if not polygon or polygon.is_empty:
            return []
        
        try:
            # INTEGRATED: Use the same conversion method as walls
            line_spacing_svg = self.path_processor._convert_mm_to_svg_units(line_spacing_mm)
            
            print(f"         INTEGRATED: Converting {line_spacing_mm:.3f}mm line spacing to {line_spacing_svg:.4f} SVG units")
            print(f"         STEP_5: Generating infill at {layer_angle}° angle")
            
            bounds = polygon.bounds
            min_x, min_y, max_x, max_y = bounds
            segments = []
            
            # STEP_5: Handle different angles more flexibly
            angle_rad = math.radians(layer_angle)
            
            # Determine if we should use horizontal, vertical, or diagonal pattern
            if abs(layer_angle) < 15 or abs(layer_angle - 180) < 15:
                # Nearly horizontal lines (0° or 180°)
                if max_y - min_y < line_spacing_svg * 0.5:
                    return []
                
                y = min_y + line_spacing_svg / 2
                while y <= max_y:
                    intersection = polygon.intersection(LineString([(min_x - 1, y), (max_x + 1, y)]))
                    
                    if hasattr(intersection, 'geoms'):
                        for geom in intersection.geoms:
                            if hasattr(geom, 'coords') and len(list(geom.coords)) >= 2:
                                coords = list(geom.coords)
                                if len(coords) >= 2:
                                    line_coords = [[coords[0][0], y], [coords[-1][0], y]]
                                    segments.append(line_coords)
                    elif hasattr(intersection, 'coords') and len(list(intersection.coords)) >= 2:
                        coords = list(intersection.coords)
                        if len(coords) >= 2:
                            line_coords = [[coords[0][0], y], [coords[-1][0], y]]
                            segments.append(line_coords)
                    
                    y += line_spacing_svg
            
            elif abs(layer_angle - 90) < 15:
                # Nearly vertical lines (90°)
                if max_x - min_x < line_spacing_svg * 0.5:
                    return []
                
                x = min_x + line_spacing_svg / 2
                while x <= max_x:
                    intersection = polygon.intersection(LineString([(x, min_y - 1), (x, max_y + 1)]))
                    
                    if hasattr(intersection, 'geoms'):
                        for geom in intersection.geoms:
                            if hasattr(geom, 'coords') and len(list(geom.coords)) >= 2:
                                coords = list(geom.coords)
                                if len(coords) >= 2:
                                    line_coords = [[x, coords[0][1]], [x, coords[-1][1]]]
                                    segments.append(line_coords)
                    elif hasattr(intersection, 'coords') and len(list(intersection.coords)) >= 2:
                        coords = list(intersection.coords)
                        if len(coords) >= 2:
                            line_coords = [[x, coords[0][1]], [x, coords[-1][1]]]
                            segments.append(line_coords)
                    
                    x += line_spacing_svg
            
            else:
                # STEP_5: Diagonal lines (like 45° and 135°)
                # Create diagonal lines by stepping through one axis and calculating intersections
                diagonal_distance = line_spacing_svg / abs(math.sin(angle_rad))
                
                # Extend bounds for diagonal calculation
                width = max_x - min_x
                height = max_y - min_y
                diagonal_extent = math.sqrt(width*width + height*height)
                
                # For 45° and 135° angles, use a simplified approach
                if abs(layer_angle - 45) < 5 or abs(layer_angle - 135) < 5:
                    # Step along the x-axis and create diagonal lines
                    step_distance = line_spacing_svg / abs(math.cos(angle_rad))
                    
                    x_start = min_x - diagonal_extent
                    x_end = max_x + diagonal_extent
                    
                    x = x_start
                    while x <= x_end:
                        if abs(layer_angle - 45) < 5:
                            # 45° line: y = x + offset
                            offset = min_y - x
                            line_start = [x, min_y - diagonal_extent]
                            line_end = [x + diagonal_extent, min_y]
                        else:
                            # 135° line: y = -x + offset  
                            offset = min_y + x
                            line_start = [x, min_y + diagonal_extent]
                            line_end = [x + diagonal_extent, min_y]
                        
                        # Create intersection line
                        intersection = polygon.intersection(
                            LineString([
                                [line_start[0], line_start[1]],
                                [line_end[0], line_end[1]]
                            ])
                        )
                        
                        if hasattr(intersection, 'geoms'):
                            for geom in intersection.geoms:
                                if hasattr(geom, 'coords') and len(list(geom.coords)) >= 2:
                                    coords = list(geom.coords)
                                    if len(coords) >= 2:
                                        line_coords = [[coords[0][0], coords[0][1]], [coords[-1][0], coords[-1][1]]]
                                        segments.append(line_coords)
                        elif hasattr(intersection, 'coords') and len(list(intersection.coords)) >= 2:
                            coords = list(intersection.coords)
                            if len(coords) >= 2:
                                line_coords = [[coords[0][0], coords[0][1]], [coords[-1][0], coords[-1][1]]]
                                segments.append(line_coords)
                        
                        x += step_distance
            
            print(f"         INTEGRATED: Generated {len(segments)} infill segments at {layer_angle}° angle")
            return segments
            
        except Exception as e:
            print(f"Error generating integrated linear infill: {e}")
            return []
    
    def generate_complete_infill(self, base_polygon: Polygon, hole_polygons: List[Polygon],
                               layer_num: int, wall_loops: int, line_spacing: float,
                               infill_settings: Dict[str, Any] = None) -> List[Tuple[str, List[List[float]]]]:
        """
        INTEGRATED: Generate complete infill using the same system as walls
        Works in SVG coordinate space like walls do
        STEP_6: Now supports layer-specific settings and layer enable/disable
        """
        
        # STEP_6: Check if layer is enabled
        if not self.is_layer_enabled(layer_num):
            layer_config = self.get_layer_config(layer_num)
            layer_name = layer_config.get('name', f'Layer{layer_num}') if layer_config else f'Layer{layer_num}'
            print(f"      STEP_6: Skipping infill for layer {layer_num} ({layer_name}) - layer disabled in JSON")
            return []
        
        # STEP_6: Get layer-specific infill offsets
        infill_offset, first_layer_offset = self.get_layer_infill_offsets(layer_num)
        
        # Override with passed settings if provided
        if infill_settings:
            infill_offset = infill_settings.get('infillOffset', infill_offset)
            first_layer_offset = infill_settings.get('firstLayerInfillOffset', first_layer_offset)
        
        # Select appropriate offset based on layer
        current_offset = first_layer_offset if layer_num == 1 else infill_offset
        
        # STEP_6: Get layer-specific line spacing
        current_line_spacing = self.get_layer_line_spacing(layer_num, line_spacing)
        
        # STEP_6: Get layer-specific angle
        layer_angle = self.get_layer_angle(layer_num)
        
        # STEP_6: Get layer info for logging
        layer_config = self.get_layer_config(layer_num)
        layer_name = layer_config.get('name', f'Layer{layer_num}') if layer_config else f'Layer{layer_num}'
        
        print(f"      Generating INTEGRATED infill for layer {layer_num} ({layer_name}) (angle {layer_angle}°) - STEP_6")
        print(f"         INTEGRATED: Using PathProcessor coordinate system (same as walls)")
        print(f"         STEP_6: Layer-specific processing enabled - layer is active")
        print(f"         STEP_5: Using JSON-based infill angles: {layer_angle}° (pattern: {self.default_pattern})")
        print(f"         STEP_4: Using line spacing: {current_line_spacing:.3f}mm")
        print(f"         STEP_3: Using infill offsets")
        
        if layer_num == 1:
            print(f"         WALL CLEARANCE: {current_offset}mm first layer offset")
        else:
            print(f"         WALL CLEARANCE: {current_offset}mm regular offset")
        
        print(f"         STEP_2: Using JSON thresholds - zhop: {self.zhop_threshold}mm, jumps: >{self.area_jump_threshold:.1f}mm")
        
        all_optimized_paths = []
        
        # Step 1: Create working polygon with hole exclusions
        working_polygon = base_polygon
        
        if hole_polygons:
            print(f"         Processing {len(hole_polygons)} holes for exclusion")
            for i, hole_polygon in enumerate(hole_polygons):
                try:
                    working_polygon = working_polygon.difference(hole_polygon)
                    print(f"         Excluded hole {i}: area = {hole_polygon.area:.2f}")
                except Exception as e:
                    print(f"         Warning: Could not exclude hole {i}: {e}")
        
        # Step 2: Apply wall offset using INTEGRATED method (same as walls)
        infill_polygon = self.create_infill_polygon_like_walls(working_polygon, current_offset)
        
        if not infill_polygon or infill_polygon.is_empty:
            print(f"         No infill area after {current_offset}mm offset")
            return all_optimized_paths
        
        # Step 3: Generate infill lines using INTEGRATED method (same as walls)
        all_segments = self.generate_linear_infill_like_walls(infill_polygon, current_line_spacing, layer_angle)
        
        if not all_segments:
            print(f"         No infill segments generated")
            return all_optimized_paths
        
        print(f"         Generated {len(all_segments)} infill segments with {current_offset}mm clearance and {current_line_spacing:.3f}mm spacing at {layer_angle}°")
        
        # Step 4: Optimize path for minimal travel (STEP_2: now uses JSON thresholds)
        optimized_paths = self.optimize_infill_path(all_segments)
        all_optimized_paths.extend(optimized_paths)
        
        print(f"      Generated {len(all_optimized_paths)} INTEGRATED infill paths for layer {layer_num} ({layer_name}) - STEP_6")
        return all_optimized_paths


def create_infill_generator(path_processor, line_spacing: float = 0.8, zhop_threshold: float = 5.0, 
                          infill_offset: float = 0.6, generate_outline: bool = False,
                          printer_config: Dict[str, Any] = None) -> InfillGenerator:
    """
    Factory function to create INTEGRATED infill generator - STEP_6: Layer-specific support
    
    Args:
        path_processor: PathProcessor instance (same one used for walls)
        line_spacing: Space between infill lines (mm) - FALLBACK if not in JSON
        zhop_threshold: Distance threshold for Z-hop travels (mm) - FALLBACK if not in JSON  
        infill_offset: Distance to offset infill from walls (mm) - FALLBACK if not in JSON
        generate_outline: Whether to generate outline perimeter (usually False)
        printer_config: Full JSON printer configuration
    """
    return InfillGenerator(path_processor, line_spacing, zhop_threshold, infill_offset, 
                          generate_outline, printer_config)


# Test function
def main():
    """Test INTEGRATED infill generator - STEP_6"""
    print("INTEGRATED InfillGenerator Test - SAME SYSTEM AS WALLS - STEP_6")
    print("NOTE: This requires a PathProcessor instance to work properly")
    print("The infill generator is now integrated into the PathProcessor system")
    print("like the wall system, using the same coordinate transformation methods.")
    print("STEP_6: Now supports layer-specific settings and layer enable/disable")


if __name__ == "__main__":
    main()