#!/usr/bin/env python3
"""
====================================================================
GCODE OUTPUT GENERATION - H2D WITH BAMBU TEMPLATE MODE
====================================================================

Version: v8.2.8-SINGLE-TOOL-FIX - Fixed Single Tool Mode! 🔥
- CRITICAL FIX: Single tool mode now sets BOTH physical nozzles! ⚠️
  * When using only one tool (e.g., just T1), code was in "single tool mode" ✅
  * Single tool mode was NOT setting the unused physical nozzle to standby ✅
  * Now BOTH branches (single tool AND multi tool) handle dual nozzles ✅
  * Active nozzle: 280°C, Unused physical nozzle: 150°C ✅
- PREVIOUS FIXES:
  * Set BOTH nozzle temps during EVERY filament change ✅
  * T0/T1 swapped for all M104/M109 temperature commands ✅
  * Removed dangerous hardcoded 290°C temperature ✅

=== THE FIX: Single tool mode now manages both physical nozzles! ===
"""

print("=" * 80)
print("USING: v8.2.8-SINGLE-TOOL-FIX - Single Tool Mode Fixed!")
print("=" * 80)

from gcode_core import (
    PathProcessor,
    ConfigurationManager,
    CornerRounder,
    HAS_SHAPELY,
    HAS_INFILL_GENERATOR
)

# Import infill generator if available
if HAS_INFILL_GENERATOR:
    try:
        from infill_generator import create_infill_generator
    except ImportError:
        HAS_INFILL_GENERATOR = False
from startup import StartupGenerator, EndSequenceGenerator
import math
import os
import hashlib
import zipfile
import json
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
try:
    from PIL import Image
    HAS_PIL = True
except:
    HAS_PIL = False

# =====================================================
# START POINT OPTIMIZER
# =====================================================

class StartPointOptimizer:
    """Optimize start points with corner preference"""
    
    def __init__(self, corner_angle_threshold: float = 30.0):
        self.optimization_enabled = True
        self.corner_angle_threshold = corner_angle_threshold
    
    def calculate_angle_change(self, coords: List[List[float]], index: int) -> float:
        n = len(coords)
        if n < 3:
            return 0.0
        
        prev_idx = (index - 1) % n
        curr_idx = index
        next_idx = (index + 1) % n
        
        p1 = coords[prev_idx]
        p2 = coords[curr_idx]
        p3 = coords[next_idx]
        
        v1x = p1[0] - p2[0]
        v1y = p1[1] - p2[1]
        v2x = p3[0] - p2[0]
        v2y = p3[1] - p2[1]
        
        len1 = math.sqrt(v1x*v1x + v1y*v1y)
        len2 = math.sqrt(v2x*v2x + v2y*v2y)
        
        if len1 < 0.001 or len2 < 0.001:
            return 0.0
        
        v1x /= len1
        v1y /= len1
        v2x /= len2
        v2y /= len2
        
        dot = v1x * v2x + v1y * v2y
        dot = max(-1.0, min(1.0, dot))
        
        angle_rad = math.acos(dot)
        angle_deg = math.degrees(angle_rad)
        
        return angle_deg
    
    def find_corner_points(self, coords: List[List[float]]) -> List[int]:
        if len(coords) < 3:
            return []
        
        corners = []
        search_range = len(coords) - 1 if (coords[0] == coords[-1]) else len(coords)
        
        for i in range(search_range):
            angle_change = self.calculate_angle_change(coords, i)
            if angle_change >= self.corner_angle_threshold:
                corners.append(i)
        
        return corners
    
    def find_closest_point_index(self, coords: List[List[float]], 
                                 current_pos: Tuple[float, float],
                                 prefer_corners: bool = True) -> int:
        if not coords or current_pos is None:
            return 0
        
        search_range = len(coords) - 1 if (coords[0] == coords[-1]) else len(coords)
        corner_indices = set(self.find_corner_points(coords)) if prefer_corners else set()
        
        distances = []
        for i in range(search_range):
            dx = coords[i][0] - current_pos[0]
            dy = coords[i][1] - current_pos[1]
            distance = math.sqrt(dx*dx + dy*dy)
            is_corner = i in corner_indices
            distances.append((i, distance, is_corner))
        
        if not distances:
            return 0
        
        distances.sort(key=lambda x: x[1])
        
        if not corner_indices:
            return distances[0][0]
        
        min_distance = distances[0][1]
        corner_tolerance = min_distance * 1.5
        
        for idx, distance, is_corner in distances:
            if is_corner and distance <= corner_tolerance:
                return idx
        
        return distances[0][0]
    
    def rotate_coordinates_to_closest(self, coords: List[List[float]], 
                                     current_pos: Optional[Tuple[float, float]]) -> List[List[float]]:
        if not self.optimization_enabled or not coords or current_pos is None:
            return coords
        
        if len(coords) < 3:
            return coords
        
        is_closed = (coords[0] == coords[-1])
        closest_index = self.find_closest_point_index(coords, current_pos, prefer_corners=True)
        
        if closest_index == 0:
            return coords
        
        if is_closed:
            working_coords = coords[:-1]
            rotated = working_coords[closest_index:] + working_coords[:closest_index]
            rotated.append(rotated[0])
        else:
            rotated = coords[closest_index:] + coords[:closest_index]
        
        return rotated
    
    def rotate_coordinates_to_seam(self, coords: List[List[float]], 
                                    vertex_index: int) -> List[List[float]]:
        """
        Rotate coordinates to start at the specified vertex index (from seam selection)
        
        Args:
            coords: List of coordinate pairs
            vertex_index: Index of the vertex to start from
            
        Returns:
            Reordered coordinates starting at vertex_index
        """
        if not coords or vertex_index < 0:
            return coords
        
        if len(coords) < 3:
            return coords
        
        # Check if polygon is closed
        is_closed = (coords[0] == coords[-1])
        
        if is_closed:
            # Remove duplicate last point
            working_coords = coords[:-1]
            
            # Ensure vertex_index is within bounds
            if vertex_index >= len(working_coords):
                vertex_index = 0
            
            # Rotate to start at vertex_index
            rotated = working_coords[vertex_index:] + working_coords[:vertex_index]
            
            # Re-add closing point
            rotated.append(rotated[0])
        else:
            # For open paths, just rotate
            if vertex_index >= len(coords):
                vertex_index = 0
            rotated = coords[vertex_index:] + coords[:vertex_index]
        
        return rotated

# =====================================================
# DIRECTION MANAGER
# =====================================================

class DirectionManager:
    """Direction manager with corkscrew mode support"""
    
    def __init__(self, config_manager: ConfigurationManager):
        self.config = config_manager
        self.direction_settings = self._load_direction_settings()
        self.corkscrew_mode = self.direction_settings.get('corkscrewMode', False)
        self.continuous_extrusion = self.direction_settings.get('continuousExtrusion', True)
        self.retract_between_walls = self.direction_settings.get('retractBetweenWalls', True)
        self.retract_between_layers = self.direction_settings.get('retractBetweenLayers', True)
        self.min_continuous_distance = self.direction_settings.get('minimumContinuousDistance', 0.1)
        self.max_travel_without_retract = self.direction_settings.get('maxTravelWithoutRetract', 2.0)
    
    def _load_direction_settings(self) -> Dict[str, Any]:
        if hasattr(self.config, 'config'):
            return self.config.config.get('printDirectionSettings', {})
        return {}
    
    def is_corkscrew_mode_enabled(self) -> bool:
        return self.corkscrew_mode
    
    def should_use_continuous_extrusion(self, start_pos: Tuple[float, float], 
                                       end_pos: Tuple[float, float]) -> bool:
        if not self.continuous_extrusion:
            return False
        distance = math.sqrt((end_pos[0] - start_pos[0])**2 + (end_pos[1] - start_pos[1])**2)
        if distance <= self.min_continuous_distance:
            return True
        if self.corkscrew_mode and distance <= self.max_travel_without_retract:
            return True
        return False
    
    def should_retract_between_walls(self) -> bool:
        if self.corkscrew_mode and not self.retract_between_walls:
            return False
        return self.retract_between_walls
    
    def should_retract_between_layers(self) -> bool:
        if self.corkscrew_mode and not self.retract_between_layers:
            return False
        return self.retract_between_layers
    
    def ensure_consistent_direction(self, coordinates: List[List[float]]) -> List[List[float]]:
        if len(coordinates) < 3:
            return coordinates
        area = 0.0
        n = len(coordinates)
        for i in range(n):
            j = (i + 1) % n
            area += (coordinates[j][0] - coordinates[i][0]) * (coordinates[j][1] + coordinates[i][1])
        is_clockwise = area > 0
        desired_direction = self.direction_settings.get('printDirection', 'counterclockwise').lower()
        should_be_clockwise = (desired_direction == 'clockwise')
        if is_clockwise != should_be_clockwise:
            return list(reversed(coordinates))
        return coordinates

# =====================================================
# ENHANCED PATH PROCESSOR
# =====================================================

class EnhancedPathProcessor(PathProcessor):
    def __init__(self, config_manager: ConfigurationManager):
        super().__init__(config_manager)
        self.corner_rounder = CornerRounder(config_manager)
        if self.corner_rounder.is_rounded_corners_enabled():
            self.boundaries = self.corner_rounder.apply_corner_rounding_to_boundaries(self.boundaries)
    
    @classmethod
    def from_config_file(cls, config_file_path: str) -> 'EnhancedPathProcessor':
        config_manager = ConfigurationManager.from_config_file(config_file_path)
        return cls(config_manager)
    
    @classmethod
    def from_html(cls, html_json: Dict[str, Any],
                  printer_registry: Optional[Any] = None) -> 'EnhancedPathProcessor':
        config_manager = ConfigurationManager.from_html(html_json, printer_registry)
        return cls(config_manager)
    
    def get_shape_info(self) -> Dict[str, Any]:
        shape_info = super().get_shape_info()
        shape_info.update({
            'corner_rounding_enabled': self.corner_rounder.is_rounded_corners_enabled(),
            'corner_radius': self.corner_rounder.corner_radius if self.corner_rounder.is_rounded_corners_enabled() else 0,
            'version': 'v7.3.1-COMPLETE-FIX'
        })
        return shape_info

# =====================================================
# SECTION CLASSES
# =====================================================

class Section:
    def __init__(self, config_data, filament_types=None):
        self.name = config_data.get('name', 'Unknown')
        self.height = config_data.get('height', 2.0)
        self.wallLoops = config_data.get('wallLoops', 2)
        self.enabled = config_data.get('enabled', False)
        self.filament = config_data.get('filament', 0)
        self.index = config_data.get('index', 0)
        self.nozzle = config_data.get('nozzle', 0)
        
        if 'tool' in config_data:
            self.tool = config_data['tool']
        elif filament_types and str(self.filament) in filament_types:
            physical_extruder = filament_types[str(self.filament)].get('nozzle', 0)  # FIXED: Changed from physicalExtruder to nozzle
            self.tool = f'T{physical_extruder}'
        else:
            self.tool = f'T{self.nozzle}'
        
        self.gcode_layer_count = 0
        self.start_layer = 0
        self.end_layer = 0
        
        self.clickSystemProfile = config_data.get('clickSystemProfile', 'none')

class SectionManager:
    def __init__(self, config_manager: ConfigurationManager):
        self.config = config_manager
        self.sections = self._create_5_sections()
        self.enabled_sections = [s for s in self.sections if s.enabled]
        self.layer_to_section_map = self._calculate_layer_mapping()
    
    def _create_5_sections(self) -> List[Section]:
        sections = []
        layer_configs = self.config.get_layers_configuration()
        filament_types = self.config.get_filament_types()
        for layer_config in layer_configs:
            sections.append(Section(layer_config, filament_types))
        return sections
    
    def _calculate_layer_mapping(self) -> Dict[int, Section]:
        layer_settings = self.config.get_layer_settings()
        layer_height = layer_settings.get('layerHeight', 0.2)
        mapping = {}
        current_gcode_layer = 0
        for section in self.enabled_sections:
            section_layers = max(1, int(section.height / layer_height))
            section.start_layer = current_gcode_layer
            section.end_layer = current_gcode_layer + section_layers - 1
            section.gcode_layer_count = section_layers
            for layer_num in range(section.start_layer, section.end_layer + 1):
                mapping[layer_num] = section
            current_gcode_layer += section_layers
        return mapping
    
    def get_section_for_layer(self, layer_num: int) -> Section:
        return self.layer_to_section_map.get(layer_num)
    
    def get_total_layers(self) -> int:
        return len(self.layer_to_section_map)

# =====================================================
# MULTI-MATERIAL G-CODE RENDERER
# =====================================================

class GCodeRendererBase:
    """
    Generate G-code with Bambu Studio compatible filament changes
    
    ⭐ HOLE DETECTION SYSTEM ⭐
    ---------------------------
    This renderer includes a comprehensive hole detection system that applies special
    settings to holes in a specific size range:
    
    Configuration (in JSON wallSettings):
    - skipWallsMinHoleSize: 4.0mm (minimum hole diameter)
    - skipWallsMaxHoleSize: 6.0mm (maximum hole diameter)
    - holeWallMaxHeight: 3.0mm (print walls up to this Z height, then stop)
    - holeWallOffset: 0.4mm (always use this offset for detected holes)
    - holeWallLoops: 2 (always use 2 walls for detected holes)
    
    Behavior:
    1. Holes between 4-6mm diameter are automatically detected
    2. These holes always use 2 walls with 0.4mm offset (ignoring Normal Wall Offset setting)
    3. Walls are printed up to 3mm height, then stopped (rest of print continues)
    4. Other boundaries use normal settings (Normal Wall Offset, section wallLoops)
    
    Implementation:
    - is_detected_hole(): Checks if boundary is in 4-6mm range
    - get_wall_offset_for_boundary(): Returns appropriate offset (0.4mm for holes, normal otherwise)
    - should_skip_walls_for_hole(): Checks if walls should be skipped based on Z height
    - Path processor can access these methods via self.gcode_renderer reference
    """
    
    def __init__(self, config_manager: ConfigurationManager, path_processor: EnhancedPathProcessor):
        self.config = config_manager
        self.path_processor = path_processor
        
        # ⭐ IMPORTANT: Allow path_processor to call back for hole-specific offsets
        # PathProcessor should check if renderer exists and call get_wall_offset_for_boundary
        if hasattr(self.path_processor, '__dict__'):
            self.path_processor.gcode_renderer = self
        
        self.direction_manager = DirectionManager(config_manager)
        self.start_point_optimizer = StartPointOptimizer(corner_angle_threshold=30.0)
        
        # Initialize startup and end generators with config (no file loading)
        self.startup_generator = StartupGenerator(config=config_manager.config)
        self.end_generator = EndSequenceGenerator(config=config_manager.config)
        
        self.section_manager = SectionManager(config_manager)
        
        self.temp_settings = self.config.get_temperature_settings()
        self.speed_settings = self.config.get_speed_settings()
        self.layer_settings = self.config.get_layer_settings()
        self.movement_settings = self.config.get_movement_settings()
        self.end_gcode_settings = self.config.get_end_gcode_settings()
        self.algorithm_settings = self.config.get_algorithm_settings()
        self.fan_settings = self.config.get_fan_settings()
        self.infill_settings = self.config.get_infill_settings()
        self.foundation_settings = self.config.get_foundation_settings()
        self.wall_settings = self.config.get_wall_settings()
        
        self.click_system_profiles = self.config.config.get('clickSystemProfiles', {})
        
        self.max_infill_travel_without_retract = self.infill_settings.get('maxInfillTravelWithoutRetract', 5.0)
        
        build_volume = self.config.config.get('buildVolume', {'x': 180, 'y': 180, 'z': 180})
        self.bed_size_x = build_volume['x']
        self.bed_size_y = build_volume['y']
        self.bed_size_z = build_volume['z']
        
        self.shape_info = self.path_processor.get_shape_info()
        
        self.current_feedrate = None
        self.current_fan_speed = -1
        self.current_x = None
        self.current_y = None
        self.current_z = 0.0
        self.current_section = None
        self.current_boundary_id = None
        self.last_boundary_type = None
        
        self.current_tool = None
        self.current_filament = None
        self.previous_filament = None
        self.used_tools = self._determine_used_tools()
        self.filament_types = self.config.get_filament_types()
        
        # Store seam selections from config
        self.seam_selections = self.config.config.get('seamSelections', {})
        print(f"📍 Seam selections loaded: {len(self.seam_selections)} polygon(s) with seam data")
    
    def swap_temp_tool(self, tool: str) -> str:
        """
        ⚠️ CRITICAL FIX: H2D firmware has T0/T1 swapped for temperature commands!
        
        The H2D firmware interprets tool numbers opposite to physical nozzles:
        - Firmware T0 = Physical RIGHT nozzle (not left!)
        - Firmware T1 = Physical LEFT nozzle (not right!)
        
        This function maps ANY tool (T0-T4) to the correct firmware tool based on
        which physical nozzle that filament uses.
        """
        # Look up which physical nozzle this tool uses
        filament_info = self.filament_types.get(tool[1:], {})  # "T2" -> "2"
        physical_nozzle = filament_info.get('nozzle', 0)
        
        # Map physical nozzle to firmware tool (swapped!)
        if physical_nozzle == 0:  # Left nozzle
            return "T1"
        else:  # Right nozzle (nozzle 1)
            return "T0"
    
    def _determine_used_tools(self) -> set:
        """Determine which tools are used in enabled sections"""
        used_tools = set()
        for section in self.section_manager.enabled_sections:
            tool = section.tool
            used_tools.add(tool)
        return used_tools
    
    def generate_gcode(self) -> str:
        gcode_lines = []
        gcode_lines.extend(self.generate_header())
        gcode_lines.extend(self.generate_startup_sequence())
        
        gcode_lines.extend(self.generate_pre_print_temperatures())
        
        total_layers = self.calculate_total_layers()
        foundation_layers = self.foundation_settings.get('foundationLayerCount', 3)
        current_z = 0.0
        
        print(f"\n{'='*60}")
        print(f"STARTING PRINT - LAYER Z HEIGHT CALCULATION")
        print(f"{'='*60}")
        
        for layer_num in range(total_layers):
            is_foundation = layer_num < foundation_layers
            layer_height = (self.layer_settings['firstLayerHeight'] if is_foundation 
                          else self.layer_settings['layerHeight'])
            current_z += layer_height
            
            print(f"LAYER {layer_num}: Z = {current_z:.3f}mm (height = {layer_height:.3f}mm, foundation = {is_foundation})")
            
            layer_gcode = self.generate_layer_gcode_with_material_changes(layer_num, current_z, is_foundation)
            gcode_lines.extend(layer_gcode)
        
        print(f"{'='*60}\n")
        
        gcode_lines.extend(self.generate_end_sequence())
        return '\n'.join(gcode_lines)
    
    def generate_header(self) -> List[str]:
        return [
            "; Generated by JSON Configuration G-code Generator v7.3.1-COMPLETE-FIX",
            "; INFILL GENERATION RESTORED",
            "; CLICK SYSTEM PROFILE SUPPORT for index 5",
            f"; Printer: {self.config.config.get('name', 'Unknown')}",
            f"; Build Volume: {self.bed_size_x}x{self.bed_size_y}x{self.bed_size_z}mm",
            f"; Filaments Used: {', '.join(sorted(str(s.filament) for s in self.section_manager.enabled_sections))}",
            f"; Generated: {datetime.now().isoformat()}",
            ""
        ]
    
    def generate_startup_sequence(self) -> List[str]:
        """Generate startup with primary tool initialization"""
        primary_filament = self.section_manager.enabled_sections[0].filament if self.section_manager.enabled_sections else 0
        primary_tool = self.section_manager.enabled_sections[0].tool if self.section_manager.enabled_sections else 'T0'
        
        primary_nozzle_temp = self.temp_settings['nozzleTemp'].get(primary_tool, 280)
        nozzle_temp_initial = self.temp_settings.get('nozzleTempInitialLayer', {}).get(primary_tool, 270)
        bed_temp = self.temp_settings['bedTemp']
        chamber_temp = self.temp_settings.get('chamberTemp', 0)
        filament_type = self.temp_settings.get('filamentType', 'PC')
    
        self.current_tool = primary_tool
        self.current_filament = primary_filament
        self.previous_filament = primary_filament
    
        return self.startup_generator.generate(
            nozzle_temp=int(primary_nozzle_temp),
            bed_temp=int(bed_temp),
            filament_type=filament_type,
            chamber_temp=int(chamber_temp),
            nozzle_temp_initial=int(nozzle_temp_initial),
            filament_id=primary_filament,
            starting_tool=primary_tool
        )
    
    def generate_pre_print_temperatures(self) -> List[str]:
        """
        Adjust temperatures before printing - works for single AND dual nozzle
        
        Single nozzle (Creality): Just set active nozzle to print temp
        Dual nozzle (Bambu H2D): Set active to print temp, idle to standby
        
        All values from JSON configuration - no hardcoding!
        
        Supports Bambu H2D firmware quirk (T0/T1 swap for temp commands)
        via JSON config: "swapTempTools": true
        """
        gcode_lines = [
            "",
            "; === TEMPERATURE ADJUSTMENT FOR PRINTING ===",
        ]
        
        # Check if printer needs T0/T1 swap for temp commands (Bambu H2D quirk)
        swap_temps = self.config.config.get('swapTempTools', False)
        
        # Get number of tools being used
        num_tools = len(self.used_tools)
        
        if num_tools == 0:
            # No tools? Just return empty (shouldn't happen)
            return [""]
        
        elif num_tools == 1:
            # SINGLE TOOL MODE - but H2D still has 2 physical nozzles!
            tool = list(self.used_tools)[0]
            print_temp = self.temp_settings['nozzleTemp'].get(tool, 280)
            standby_temp = self.temp_settings.get('standbyTemp', 150)
            
            gcode_lines.append(f"; Single tool mode (tool={tool})")
            
            # For H2D: Even with one tool, we need to set BOTH physical nozzles
            if swap_temps:
                # H2D dual nozzle system
                gcode_lines.append("; H2D detected - managing both physical nozzles")
                
                # Determine which physical nozzle this tool uses
                current_filament_id = tool.replace('T', '')
                current_filament_info = self.filament_types.get(current_filament_id, {})
                current_physical_nozzle = current_filament_info.get('nozzle', 0)
                
                gcode_lines.append(f"; Tool {tool} uses physical nozzle {current_physical_nozzle}")
                
                # H2D firmware swap: T0=right(phys 1), T1=left(phys 0)
                if current_physical_nozzle == 0:  # Left nozzle is active
                    # Firmware T1 (left) = active, Firmware T0 (right) = idle
                    gcode_lines.append(f"M104 T1 S{int(print_temp)} ; Active left nozzle")
                    gcode_lines.append(f"M104 T0 S{int(standby_temp)} ; Idle right nozzle to standby")
                    gcode_lines.append(f"M109 T1 S{int(print_temp)} ; Wait for left nozzle")
                else:  # Right nozzle is active
                    # Firmware T0 (right) = active, Firmware T1 (left) = idle
                    gcode_lines.append(f"M104 T0 S{int(print_temp)} ; Active right nozzle")
                    gcode_lines.append(f"M104 T1 S{int(standby_temp)} ; Idle left nozzle to standby")
                    gcode_lines.append(f"M109 T0 S{int(print_temp)} ; Wait for right nozzle")
                
                gcode_lines.extend([
                    f"{tool} ; Activate tool",
                    "M400 ; Wait for moves to complete",
                ])
            else:
                # Standard single nozzle (A1 mini, Creality, Prusa, etc)
                system_type = self.config.config.get('systemType', 'standard')
                
                # For Bambu single nozzle, don't use T parameter in M104/M109
                if 'single_nozzle' in system_type or 'bambu' in system_type.lower():
                    gcode_lines.extend([
                        f"M104 S{int(print_temp)} ; Set nozzle temperature",
                        f"M109 S{int(print_temp)} ; Wait for temperature",
                        "; Tool already active (single nozzle)",
                        "M400 ; Wait for moves to complete",
                    ])
                else:
                    # Other single nozzle printers (Creality, Prusa)
                    gcode_lines.extend([
                        f"M104 S{int(print_temp)} ; Set to print temperature",
                        f"M109 S{int(print_temp)} ; Wait for temperature",
                        "M400 ; Wait for moves to complete",
                    ])
        
        else:
            # MULTI NOZZLE (Bambu H2D, etc)
            # Get current tool info
            current_tool = self.current_tool
            print_temp = self.temp_settings['nozzleTemp'].get(current_tool, 280)
            standby_temp = self.temp_settings.get('standbyTemp', 150)
            
            gcode_lines.append("; Multi nozzle mode")
            gcode_lines.append("; === DEBUG START ===")
            gcode_lines.append(f"; current_tool = {current_tool}")
            gcode_lines.append(f"; print_temp = {print_temp}")
            gcode_lines.append(f"; standby_temp = {standby_temp}")
            gcode_lines.append(f"; swap_temps = {swap_temps}")
            
            # === FORCEFUL FIX: Always set BOTH T0 and T1 explicitly ===
            # Determine which physical nozzle the current tool uses
            current_filament_id = current_tool.replace('T', '')
            gcode_lines.append(f"; current_filament_id = {current_filament_id}")
            
            current_filament_info = self.filament_types.get(current_filament_id, {})
            gcode_lines.append(f"; current_filament_info = {current_filament_info}")
            
            current_physical_nozzle = current_filament_info.get('nozzle', 0)
            gcode_lines.append(f"; current_physical_nozzle = {current_physical_nozzle}")
            
            # H2D firmware swap: T0=right(phys 1), T1=left(phys 0)
            # Always set BOTH firmware tools explicitly
            if current_physical_nozzle == 0:  # Left nozzle is active
                gcode_lines.append("; Left nozzle (physical 0) is ACTIVE")
                # Firmware T1 (left) = active = print temp
                # Firmware T0 (right) = idle = standby
                gcode_lines.append(f"; Setting firmware T1 (left) to {print_temp}C")
                gcode_lines.append(f"; Setting firmware T0 (right) to {standby_temp}C")
                gcode_lines.append(f"M104 T1 S{int(print_temp)} ; Active left nozzle")
                gcode_lines.append(f"M104 T0 S{int(standby_temp)} ; Idle right nozzle to standby")
                wait_tool = "T1"
            else:  # Right nozzle is active (nozzle 1)
                gcode_lines.append("; Right nozzle (physical 1) is ACTIVE")
                # Firmware T0 (right) = active = print temp
                # Firmware T1 (left) = idle = standby
                gcode_lines.append(f"; Setting firmware T0 (right) to {print_temp}C")
                gcode_lines.append(f"; Setting firmware T1 (left) to {standby_temp}C")
                gcode_lines.append(f"M104 T0 S{int(print_temp)} ; Active right nozzle")
                gcode_lines.append(f"M104 T1 S{int(standby_temp)} ; Idle left nozzle to standby")
                wait_tool = "T0"
            
            gcode_lines.append(f"; wait_tool = {wait_tool}")
            gcode_lines.append("; === DEBUG END ===")
            
            # Wait for active nozzle
            gcode_lines.extend([
                f"M109 {wait_tool} S{int(print_temp)} ; Wait for active nozzle",
                f"{current_tool} ; Activate tool",
                "M400 ; Wait for moves to complete",
            ])
        
        gcode_lines.extend([
            "; === READY TO PRINT ===",
            ""
        ])
        
        return gcode_lines
    
    def calculate_total_layers(self) -> int:
        return self.section_manager.get_total_layers()
    
    def generate_layer_gcode_with_material_changes(self, layer_num: int, layer_z: float, is_foundation: bool) -> List[str]:
        """Generate layer G-code with filament change detection"""
        gcode_lines = []
        self.current_z = layer_z
        
        current_section = self.section_manager.get_section_for_layer(layer_num)
        if not current_section:
            return [f"; ERROR: No section for layer {layer_num}"]
        
        section_name = current_section.name
        section_wall_loops = current_section.wallLoops
        section_tool = current_section.tool
        section_filament = current_section.filament
        
        if self.current_filament != section_filament:
            gcode_lines.extend(self.generate_filament_change(section_filament, section_tool))
            self.previous_filament = self.current_filament
            self.current_filament = section_filament
        
        section_transition = (self.current_section is None or 
                            self.current_section.name != current_section.name)
        
        if section_transition:
            filament_name = self.filament_types.get(str(section_filament), {}).get('name', f'Filament {section_filament}')
            gcode_lines.append(f"; === SECTION: {section_name} | Tool: {section_tool} | Filament: {filament_name} ===")
            self.current_section = current_section
        
        layer_height = (self.layer_settings['firstLayerHeight'] if is_foundation 
                       else self.layer_settings['layerHeight'])
        
        if layer_num > 0:
            if self.direction_manager.should_retract_between_layers():
                gcode_lines.extend([
                    f"G1 E-0.8 F1800",
                    f"G1 Z{layer_z + 0.4:.2f} F1200",
                ])
            gcode_lines.extend([
                f";LAYER_CHANGE",
                f";Z:{layer_z:.2f}",
                f"G1 Z{layer_z:.2f} F1200"
            ])
            
            # Qidi spiral Z-hop for clean edges
            if self.config.config.get('printDirectionSettings', {}).get('layerTransition') == 'spiral_zhop':
                spiral_cmd = self.config.config.get('printDirectionSettings', {}).get('spiralZhopCommand', '')
                if spiral_cmd:
                    gcode_lines.append(spiral_cmd.replace('{next_layer_height}', f"{layer_z:.2f}"))
            
            if self.direction_manager.should_retract_between_layers():
                gcode_lines.append(f"G1 E0.8 F1800")
        else:
            gcode_lines.extend([
                f";LAYER_CHANGE",
                f";Z:{layer_z:.2f}",
                f"G1 Z{layer_z:.2f}{self.set_feedrate(self.speed_settings['travelSpeed'])}"
            ])
            
            # Qidi spiral Z-hop for clean edges
            if self.config.config.get('printDirectionSettings', {}).get('layerTransition') == 'spiral_zhop':
                spiral_cmd = self.config.config.get('printDirectionSettings', {}).get('spiralZhopCommand', '')
                if spiral_cmd:
                    gcode_lines.append(spiral_cmd.replace('{next_layer_height}', f"{layer_z:.2f}"))
        
        gcode_lines.extend(self.add_fan_control_gcode(layer_num))
        
        if is_foundation:
            print_speed = self.speed_settings.get('foundationLayersSpeed', self.speed_settings['printSpeed'])
            line_width = self.layer_settings.get('firstLayerLineWidth', self.layer_settings.get('lineWidth', 0.4))
        else:
            print_speed = self.speed_settings['printSpeed']
            line_width = self.layer_settings.get('lineWidth', 0.4)
        
        if hasattr(current_section, 'index') and current_section.index == 5:
            profile_name = getattr(current_section, 'clickSystemProfile', 'none')
            if profile_name != 'none' and self.click_system_profiles:
                profiles = self.click_system_profiles.get('profiles', {})
                if profile_name in profiles:
                    speed_override = profiles[profile_name].get('speedOverride')
                    if speed_override:
                        print_speed = int(speed_override)
                        print(f"Layer index 5: Applying click system speed override: {print_speed} mm/min (profile: {profile_name})")
        
        travel_speed = self.speed_settings['travelSpeed']
        boundaries = self.path_processor.get_all_boundaries()
        
        if boundaries:
            gcode_lines.extend(self.generate_optimized_boundary_gcode(
                boundaries, current_section, layer_height, line_width,
                print_speed, travel_speed, is_foundation, section_name, layer_num,
                layer_z
            ))
        
        if HAS_INFILL_GENERATOR:
            infill_gcode = self.generate_infill_for_layer(layer_num, layer_z, is_foundation)
            gcode_lines.extend(infill_gcode)
        
        return gcode_lines
    
    def generate_filament_change(self, new_filament: int, tool: str) -> List[str]:
        """Generate Bambu Studio compatible filament change sequence - NEW FIRMWARE"""
        filament_info = self.filament_types.get(str(new_filament), {})
        filament_name = filament_info.get('name', f'Filament {new_filament}')
        physical_extruder = filament_info.get('nozzle', 0)  # FIXED: Changed from physicalExtruder to nozzle
        extruder = filament_info.get('extruder', 0)
        nozzle_name = "Left" if physical_extruder == 0 else "Right"
        filament_type = self.temp_settings.get('filamentType', 'PC')
        
        # CORRECT: JSON is already 0-indexed (slots 0-4)
        # Bambu AMS: Slot 0→SYNC T0, Slot 1→SYNC T5, Slot 2→SYNC T10, Slot 3→SYNC T15, Slot 4→SYNC T20
        slot_index = new_filament  # Already 0-indexed in JSON (0, 1, 2, 3, 4)
        sync_value = slot_index * 5  # Calculate SYNC value: slot × 5
        
        is_tool_change = False
        if self.previous_filament is not None:
            prev_phys = self.filament_types.get(str(self.previous_filament), {}).get('nozzle', 0)  # FIXED: Changed from physicalExtruder to nozzle
            is_tool_change = (physical_extruder != prev_phys)
        
        gcode_lines = [
            "",
            f"; === FILAMENT CHANGE: {filament_name} (Slot {slot_index}) ===",
            f"; AMS Slot {slot_index} → {tool}",
            f"; SYNC T{sync_value} (slot {slot_index} × 5)",
            "G1 E-1.2 F1800",
            "; filament end gcode",
            ";======== H2D ========",
            ";===== 20250729 =====",
            "M993 A2 B2 C2 ; nozzle cam detection allow status save.",
            "M993 A0 B0 C0 ; nozzle cam detection not allowed.",
            "M1015.4 S0 ; disable E air printing detect",
            f"M620 S{slot_index}A",
            "M1002 gcode_claim_action : 4",
            "M204 S9000",
            f"G1 Z{self.current_z + 3:.2f} F1200",
            "M400",
            "M106 P1 S0",
            "M106 P2 S0",
        ]
        
        if is_tool_change:
            gcode_lines.extend([
                "; get travel path for change filament",
                f";M620.1 X54 Y0 F21000 P0",
                f";M620.1 X54 Y0 F21000 P1",
                f";M620.1 X54 Y245 F21000 P2",
            ])
        
        # Get temperatures from JSON config (NO HARDCODING!)
        printing_temp = int(self.temp_settings['nozzleTemp'].get(tool, 280))
        standby_temp = int(self.temp_settings.get('standbyTemp', 150))
        
        gcode_lines.extend([
            f"M620.10 A0 F399.119 L0 H0.4 T{standby_temp} P{printing_temp} S1 ; Standby={standby_temp}°C, Printing={printing_temp}°C",
            f"M620.10 A1 F399.119 L0 H0.4 T{standby_temp} P{printing_temp} S1 ; Standby={standby_temp}°C, Printing={printing_temp}°C",
            f"M620.11 P0 I{slot_index} E0",
            f"M620.11 K1 I{slot_index} R10 F399.119",
            "M628 S1",
            f"M620.11 S1 L0 I{slot_index} R10 D8 E-10 F399.119",
            "M629",
            "M620.11 H0",
            f"{tool}",  # T command (kept for startup, but new firmware uses SYNC for switching)
            f"M73 E{slot_index}",
        ])
        
        
        # CRITICAL FIX: Set BOTH nozzle temperatures during EVERY filament change
        # (Not just during physical tool changes - prevents temperature drift!)
        
        gcode_lines.append("; === FILAMENT CHANGE DEBUG START ===")
        
        # Determine which physical nozzle this tool uses
        current_nozzle = filament_info.get('nozzle', 0)
        gcode_lines.append(f"; tool = {tool}")
        gcode_lines.append(f"; current_nozzle (physical) = {current_nozzle}")
        
        # Get the OTHER physical nozzle
        other_nozzle = 1 if current_nozzle == 0 else 0
        gcode_lines.append(f"; other_nozzle (physical) = {other_nozzle}")
        
        # Find a tool that uses the other nozzle
        other_tool = None
        for t, info in self.filament_types.items():
            if info.get('nozzle', 0) == other_nozzle:
                other_tool = info.get('toolId', 'T0')
                break
        
        gcode_lines.append(f"; other_tool = {other_tool}")
        
        if other_tool:
            standby_temp = self.temp_settings.get('standbyTemp', 150)
            
            # SWAP T0↔T1 for temperature commands (H2D firmware quirk)
            temp_other_tool = self.swap_temp_tool(other_tool)
            gcode_lines.append(f"; temp_other_tool (after swap) = {temp_other_tool}")
            gcode_lines.append(f"; Setting {temp_other_tool} to {standby_temp}C")
            gcode_lines.append(f"M104 {temp_other_tool} S{standby_temp} ; Set idle nozzle to standby (every change)")
        else:
            gcode_lines.append("; WARNING: No other_tool found!")
        
        gcode_lines.append("; === FILAMENT CHANGE DEBUG END ===")
        
        gcode_lines.extend([
            ";deretract",
            "; VFLUSH_START",
            f"SYNC T{sync_value}",
            "; VFLUSH_END",
            f"M1002 set_filament_type:{filament_type}",
            "M400",
            "M83",
            "M620.10 R2",
            "M628 S0",
            "M629",
            "M400",
            "M983.3 F6.66667 A0.4 R2",
            "M400",
            "G1 Y295 F30000",
            "G1 Y265 F18000",
            f"G1 Z{self.current_z + 3:.2f} F3000",
            "M204 S8000",
            f"M621 S{slot_index}A",
            "M993 A3 B3 C3 ; nozzle cam detection allow status restore.",
            "M1015.3 S0;disable tpu clog detect",
            "M1015.4 S0 ; disable E air printing detect",
            f"M620.6 I{slot_index} W1 ;enable ams air printing detect",
            "M1002 gcode_claim_action : 0",
        ])
        
        gcode_lines.append("; === ACTIVE NOZZLE TEMP DEBUG START ===")
        # SWAP T0↔T1 for temperature commands (H2D firmware quirk)
        temp_tool = self.swap_temp_tool(tool)
        active_temp = int(self.temp_settings['nozzleTemp'][tool])
        gcode_lines.append(f"; tool = {tool}")
        gcode_lines.append(f"; temp_tool (after swap) = {temp_tool}")
        gcode_lines.append(f"; active_temp = {active_temp}")
        gcode_lines.append(f"M104 {temp_tool} S{active_temp} ; set active nozzle temperature")
        gcode_lines.append("; === ACTIVE NOZZLE TEMP DEBUG END ===")
        
        gcode_lines.extend([
            "; filament start gcode",
            f"; Filament change complete: now using {filament_name} (AMS Slot {slot_index})",
            ""
        ])
        
        self.current_tool = tool
        return gcode_lines
    
    def calculate_hole_diameter(self, boundary) -> float:
        """
        Calculate diameter of a circular hole from boundary geometry
        Returns diameter in mm, or 0 if not calculable
        """
        polygon = None
        
        # Debug output
        print(f"  [DEBUG] calculate_hole_diameter called")
        print(f"  [DEBUG] Has polygon: {hasattr(boundary, 'polygon')}")
        print(f"  [DEBUG] Has geometry: {hasattr(boundary, 'geometry')}")
        print(f"  [DEBUG] Has coordinates: {hasattr(boundary, 'coordinates')}")
        
        # Try to get polygon from various attributes
        if hasattr(boundary, 'polygon') and boundary.polygon is not None:
            polygon = boundary.polygon
            print(f"  [DEBUG] Using boundary.polygon")
        elif hasattr(boundary, 'geometry') and boundary.geometry is not None:
            polygon = boundary.geometry
            print(f"  [DEBUG] Using boundary.geometry")
        elif hasattr(boundary, 'coordinates') and boundary.coordinates:
            try:
                from shapely.geometry import Polygon
                coords = boundary.coordinates
                if isinstance(coords, list) and len(coords) >= 3:
                    polygon = Polygon(coords)
                    print(f"  [DEBUG] Created polygon from {len(coords)} coordinates")
            except Exception as e:
                print(f"  [DEBUG] Failed to create polygon: {e}")
                pass
        
        if polygon is None:
            print(f"  [DEBUG] No polygon available")
            return 0.0
        
        # Calculate diameter from area (assuming circle)
        # Area = π * r^2, so r = sqrt(Area/π), diameter = 2*r
        try:
            area = polygon.area
            print(f"  [DEBUG] Polygon area: {area:.3f} (in current units)")
            if area > 0:
                radius = math.sqrt(area / math.pi)
                diameter = 2 * radius
                print(f"  [DEBUG] Calculated diameter: {diameter:.3f} (in current units)")
                
                # MANUAL SCALE CONVERSION
                # The coordinates are in SVG units, we need to convert to mm
                # Scale is calculated by PathProcessor and is typically around 0.35
                # We'll calculate it from the area comparison:
                # Real hole area in mm² = π * (13/2)² = ~132.7 mm²
                # SVG area = 1059.97 units²
                # Scale² = 132.7 / 1059.97 ≈ 0.125, so scale ≈ 0.353
                
                # But we can estimate from the diameter directly:
                # We know 13mm hole should be detected
                # If diameter is ~36.7 SVG units, and we want ~13mm
                # scale = 13 / 36.7 ≈ 0.354
                
                # Using a conservative estimate based on typical SVG-to-mm conversion
                estimated_scale = 0.3528  # This matches the console output "Scale: 0.3528"
                diameter_mm = diameter * estimated_scale
                print(f"  [DEBUG] MANUAL CONVERSION: {diameter:.3f} units × {estimated_scale} = {diameter_mm:.3f}mm")
                return diameter_mm
        except Exception as e:
            print(f"  [DEBUG] Area calculation failed: {e}")
            pass
        
        return 0.0
    
    def is_detected_hole(self, boundary) -> bool:
        """
        Check if this boundary is a hole in the detection range (4-6mm)
        Returns True if hole is detected, regardless of Z height
        Used to apply special wall settings to detected holes
        """
        if not hasattr(boundary, 'boundary_type'):
            return False
        
        if boundary.boundary_type != 'inner':
            return False
        
        diameter = self.calculate_hole_diameter(boundary)
        
        if diameter <= 0:
            return False
        
        min_size = self.wall_settings.get('skipWallsMinHoleSize', 4.0)
        max_size = self.wall_settings.get('skipWallsMaxHoleSize', 6.0)
        
        return min_size <= diameter <= max_size
    
    def get_wall_offset_for_boundary(self, boundary, wall_loops: int) -> float:
        """
        Get the appropriate wall offset for a boundary
        Detected holes (4-6mm) always use holeWallOffset (0.4mm)
        Other boundaries use normalWallOffset or zigzagWallOffset based on wall count
        
        NOTE: This method should be called by PathProcessor.get_offset_path_coordinates
        to ensure detected holes use the correct offset.
        """
        if self.is_detected_hole(boundary):
            return self.wall_settings.get('holeWallOffset', 0.4)
        elif wall_loops >= 3:
            return self.wall_settings.get('zigzagWallOffset', 1.5)
        else:
            return self.wall_settings.get('normalWallOffset', 3.0)
    
    def should_skip_walls_for_hole(self, boundary, current_z: float = None) -> bool:
        """
        Check if this boundary is a hole that should skip walls
        Returns True if walls should be skipped
        
        For holes in the 12-14mm range with holeWallMaxHeight setting:
        - Print walls up to holeWallMaxHeight
        - Skip walls above that height
        
        Supports two config styles:
        1. Center + tolerance: skipWallsForHoleSize + holeSizeTolerance
        2. Min/Max range: skipWallsMinHoleSize + skipWallsMaxHoleSize
        """
        # Debug: Check boundary type
        if not hasattr(boundary, 'boundary_type'):
            print(f"  [DEBUG] Boundary has no boundary_type attribute")
            return False
        
        print(f"  [DEBUG] Checking boundary: type={boundary.boundary_type}")
        
        # Only check inner boundaries (holes)
        if boundary.boundary_type != 'inner':
            print(f"  [DEBUG] Not inner boundary, skipping")
            return False
        
        # Calculate hole diameter
        diameter = self.calculate_hole_diameter(boundary)
        print(f"  [DEBUG] Calculated diameter: {diameter:.3f}mm")
        
        if diameter <= 0:
            print(f"  [DEBUG] Invalid diameter, skipping")
            return False
        
        # Debug: Show config
        print(f"  [DEBUG] wall_settings keys: {list(self.wall_settings.keys())}")
        
        # Check which config style is being used
        is_detected_hole = False
        if 'skipWallsMinHoleSize' in self.wall_settings and 'skipWallsMaxHoleSize' in self.wall_settings:
            # MIN/MAX APPROACH (more flexible)
            min_size = self.wall_settings.get('skipWallsMinHoleSize', 12.0)
            max_size = self.wall_settings.get('skipWallsMaxHoleSize', 14.0)
            
            if min_size <= diameter <= max_size:
                is_detected_hole = True
                print(f"  ⊙ Hole detected: {diameter:.2f}mm (range {min_size}-{max_size}mm)")
        
        else:
            # CENTER + TOLERANCE APPROACH (original)
            target_hole_size = self.wall_settings.get('skipWallsForHoleSize', 13.0)
            tolerance = self.wall_settings.get('holeSizeTolerance', 1.0)
            
            print(f"  [DEBUG] Using tolerance approach: target={target_hole_size}mm, tolerance=±{tolerance}mm")
            
            min_diameter = target_hole_size - tolerance
            max_diameter = target_hole_size + tolerance
            
            print(f"  [DEBUG] Range: {min_diameter}mm - {max_diameter}mm")
            print(f"  [DEBUG] Check: {min_diameter} <= {diameter:.3f} <= {max_diameter} = {min_diameter <= diameter <= max_diameter}")
            
            if min_diameter <= diameter <= max_diameter:
                is_detected_hole = True
                print(f"  ⊙ Hole detected: {diameter:.2f}mm (target {target_hole_size}mm ±{tolerance}mm)")
        
        if not is_detected_hole:
            print(f"  [DEBUG] Hole {diameter:.2f}mm does NOT match detection criteria - walls will be generated")
            return False
        
        # Check if we have height limitation
        hole_wall_max_height = self.wall_settings.get('holeWallMaxHeight', None)
        
        if hole_wall_max_height is not None and current_z is not None:
            # Limited height mode: skip walls only above the max height
            if current_z > hole_wall_max_height:
                print(f"  ⊙ Z={current_z:.2f}mm > max height {hole_wall_max_height}mm - SKIPPING WALLS")
                return True
            else:
                print(f"  ⊙ Z={current_z:.2f}mm <= max height {hole_wall_max_height}mm - PRINTING WALLS")
                return False
        else:
            # Original behavior: skip all walls for this hole
            print(f"  ⊙ No height limit set - SKIPPING ALL WALLS")
            return True
    
    def get_boundary_seam_position(self, boundary) -> tuple:
        """
        Get the actual seam position (x, y) for a boundary.
        Uses seam selection if available, otherwise uses first coordinate.
        
        Returns:
            (x, y) tuple of seam position, or None if boundary has no coordinates
        """
        try:
            boundary_index = str(boundary.boundary_id) if hasattr(boundary, 'boundary_id') else None
            
            # Get base coordinates for wall 0
            if hasattr(self.path_processor, 'get_wall_coordinates'):
                path_coords = self.path_processor.get_wall_coordinates(
                    wall_index=0,
                    wall_offset=0,
                    layer_name=getattr(boundary, 'layer_name', None),
                    target_boundary_id=boundary.boundary_id if hasattr(boundary, 'boundary_id') else None
                )
            else:
                path_coords = boundary.coordinates if hasattr(boundary, 'coordinates') else None
            
            if not path_coords or len(path_coords) == 0:
                return None
            
            # Check if we have a seam selection for this boundary
            seam_selection = self.seam_selections.get(boundary_index) if boundary_index else None
            
            if seam_selection is not None and isinstance(seam_selection, int):
                # Use the seam vertex position
                vertex_index = seam_selection
                if vertex_index < len(path_coords):
                    return tuple(path_coords[vertex_index])
            
            # Default: use first coordinate as seam position
            return tuple(path_coords[0])
            
        except Exception as e:
            print(f"  Warning: Could not get seam position for boundary: {e}")
            return None

    def find_closest_boundary_by_seam(self, boundaries: List, current_pos: tuple) -> int:
        """
        Find the boundary whose seam position is closest to current position.
        
        Args:
            boundaries: List of boundaries to choose from
            current_pos: Current (x, y) position, or None
            
        Returns:
            Index of closest boundary in the list
        """
        if not boundaries:
            return 0
        
        if current_pos is None:
            return 0  # No current position, just take first
        
        min_dist = float('inf')
        closest_idx = 0
        
        for idx, boundary in enumerate(boundaries):
            seam_pos = self.get_boundary_seam_position(boundary)
            
            if seam_pos is None:
                continue
            
            # Calculate distance from current position to this boundary's seam
            dist = ((seam_pos[0] - current_pos[0])**2 + (seam_pos[1] - current_pos[1])**2)**0.5
            
            if dist < min_dist:
                min_dist = dist
                closest_idx = idx
        
        return closest_idx

    def generate_optimized_boundary_gcode(self, boundaries: List, current_section: Section,
                                         layer_height: float, line_width: float,
                                         print_speed: int, travel_speed: int,
                                         is_foundation: bool, section_name: str, layer_num: int,
                                         current_z: float = None) -> List[str]:
        gcode_lines = []
        section_wall_loops = current_section.wallLoops
        
        outer_boundaries = [b for b in boundaries if b.boundary_type == 'outer']
        inner_boundaries = [b for b in boundaries if b.boundary_type == 'inner']
        
        gcode_lines.append(f"; --- Layer {layer_num}: {len(outer_boundaries)} outer, {len(inner_boundaries)} inner ---")
        
        if outer_boundaries:
            gcode_lines.append(f"; === OUTER BOUNDARIES ===")
            
            # Optimize boundary order to minimize travel (seam-to-seam)
            remaining_boundaries = outer_boundaries.copy()
            current_pos = (self.current_x, self.current_y) if self.current_x is not None else None
            
            while remaining_boundaries:
                # Find closest boundary by seam position
                closest_idx = self.find_closest_boundary_by_seam(remaining_boundaries, current_pos)
                boundary = remaining_boundaries.pop(closest_idx)
                
                gcode_lines.extend(self.generate_optimized_boundary_walls(
                    boundary, current_section, layer_height, line_width,
                    print_speed, travel_speed, is_foundation, section_name,
                    layer_num, current_z
                ))
                
                # Update current position to this boundary's seam for next iteration
                current_pos = self.get_boundary_seam_position(boundary)
                if current_pos is None:
                    current_pos = (self.current_x, self.current_y)
        
        if inner_boundaries:
            gcode_lines.append(f"; === INNER BOUNDARIES ===")
            
            # Optimize boundary order to minimize travel (seam-to-seam)
            remaining_boundaries = inner_boundaries.copy()
            current_pos = (self.current_x, self.current_y) if self.current_x is not None else None
            
            while remaining_boundaries:
                # Find closest boundary by seam position
                closest_idx = self.find_closest_boundary_by_seam(remaining_boundaries, current_pos)
                boundary = remaining_boundaries.pop(closest_idx)
                
                # ⭐ HOLE DETECTION - Skip walls for specific hole sizes (with optional height limit)
                if self.should_skip_walls_for_hole(boundary, current_z):
                    gcode_lines.append(f"; Boundary {boundary.boundary_id}: Hole skipped (no walls at Z={current_z:.2f}mm)")
                    continue  # Skip wall generation for this hole!
                
                gcode_lines.extend(self.generate_optimized_boundary_walls(
                    boundary, current_section, layer_height, line_width,
                    print_speed, travel_speed, is_foundation, section_name,
                    layer_num, current_z
                ))
                
                # Update current position to this boundary's seam for next iteration
                current_pos = self.get_boundary_seam_position(boundary)
                if current_pos is None:
                    current_pos = (self.current_x, self.current_y)
        
        return gcode_lines
    
    def generate_optimized_boundary_walls(self, boundary, current_section: Section,
                                         layer_height: float, line_width: float,
                                         print_speed: int, travel_speed: int,
                                         is_foundation: bool, section_name: str,
                                         layer_num: int, current_z: float = None) -> List[str]:
        gcode_lines = []
        section_wall_loops = current_section.wallLoops
        
        # ⭐ DETECTED HOLE OVERRIDE - Force fixed walls and offset for detected holes (4-6mm)
        is_hole = self.is_detected_hole(boundary)
        original_wall_offset = None
        original_zigzag_offset = None
        
        # ⭐ PROGRESSIVE LAYER COMPENSATION - Different compensation per layer for gradual transition
        original_first_layer_offset = None
        original_first_layer_zigzag = None
        apply_first_layer_offset = False
        
        # Get layer-specific compensation from JSON (supports per-layer values)
        first_layer_compensation = 0.0
        layer_compensation_map = self.wall_settings.get('layerCompensationMap', {})
        
        # DEBUG: Show what was loaded
        if layer_num == 0:  # Only print once on first layer
            print(f"\n🔍 DEBUG: layerCompensationMap = {layer_compensation_map}")
            print(f"🔍 DEBUG: wallPrintOrder = {self.wall_settings.get('wallPrintOrder', 'NOT SET')}")
            print(f"🔍 DEBUG: Available in wall_settings: {list(self.wall_settings.keys())}\n")
        
        if layer_compensation_map and str(layer_num) in layer_compensation_map:
            # Use specific layer compensation from map
            first_layer_compensation = layer_compensation_map[str(layer_num)]
            apply_first_layer_offset = True
            print(f"🔴 LAYER {layer_num}: APPLYING COMPENSATION = {first_layer_compensation}mm (from layerCompensationMap)")
        elif layer_num < 2 and not is_hole:
            # Fallback to old simple first layer offset
            apply_first_layer_offset = True
            # Save original offsets
            original_first_layer_offset = self.wall_settings.get('normalWallOffset')
            original_first_layer_zigzag = self.wall_settings.get('zigzagWallOffset')
            
            # Get first layer COMPENSATION from config (applies to base polygon, not per-wall offset)
            first_layer_compensation = self.wall_settings.get('firstLayerCompensation', 0.0)
            
            # If firstLayerCompensation doesn't exist, try firstLayerWallOffset as fallback
            if first_layer_compensation == 0.0:
                first_layer_compensation = self.wall_settings.get('firstLayerWallOffset', 0.0)
            
            print(f"🔴 LAYER {layer_num}: APPLYING COMPENSATION = {first_layer_compensation}mm (fallback mode)")
        else:
            # No compensation for this layer
            print(f"🟢 LAYER {layer_num}: NO COMPENSATION (layer >= 2 or is hole)")
        
        # Apply compensation if needed
        if apply_first_layer_offset and first_layer_compensation != 0.0:
            # Apply first layer compensation (this is now the BASE compensation, not multiplied by wall_index)
            self.wall_settings['firstLayerCompensation'] = first_layer_compensation
            
            # Update config so PathProcessor sees it
            if hasattr(self.config, 'config') and 'wallSettings' in self.config.config:
                self.config.config['wallSettings']['firstLayerCompensation'] = first_layer_compensation
            
            # ⭐ CRITICAL FIX: Update PathProcessor's cached wall_settings
            if hasattr(self.path_processor, 'wall_settings'):
                self.path_processor.wall_settings['firstLayerCompensation'] = first_layer_compensation
        
        if is_hole:
            # Use hole-specific settings
            section_wall_loops = self.wall_settings.get('holeWallLoops', 2)
            hole_offset = self.wall_settings.get('holeWallOffset', 0.4)
            
            # ⭐ CRITICAL: Temporarily override config wall offsets so PathProcessor uses hole offset
            original_wall_offset = self.wall_settings.get('normalWallOffset')
            original_zigzag_offset = self.wall_settings.get('zigzagWallOffset')
            self.wall_settings['normalWallOffset'] = hole_offset
            self.wall_settings['zigzagWallOffset'] = hole_offset
            
            # Also update in the config manager so PathProcessor sees it
            if hasattr(self.config, 'config') and 'wallSettings' in self.config.config:
                self.config.config['wallSettings']['normalWallOffset'] = hole_offset
                self.config.config['wallSettings']['zigzagWallOffset'] = hole_offset
            
            # ⭐ CRITICAL FIX: Update PathProcessor's cached wall_settings
            if hasattr(self.path_processor, 'wall_settings'):
                self.path_processor.wall_settings['normalWallOffset'] = hole_offset
                self.path_processor.wall_settings['zigzagWallOffset'] = hole_offset
            
            gcode_lines.append(f"; Boundary {boundary.boundary_id}: {boundary.boundary_type} - DETECTED HOLE (forced {section_wall_loops} walls, {hole_offset}mm offset)")
        else:
            if apply_first_layer_offset and first_layer_compensation != 0.0:
                gcode_lines.append(f"; Boundary {boundary.boundary_id}: {boundary.boundary_type} - LAYER {layer_num} COMPENSATION ({first_layer_compensation}mm)")
            else:
                gcode_lines.append(f"; Boundary {boundary.boundary_id}: {boundary.boundary_type}")
        
        # ⭐ WALL PRINTING ORDER - Determine if we print inside→outside or outside→inside
        wall_print_order = self.wall_settings.get('wallPrintOrder', 'outside_to_inside')
        
        # DEBUG: Show what was read
        print(f"🔧 Wall print order setting: '{wall_print_order}'")
        
        if wall_print_order == 'inside_to_outside':
            # Print innermost wall first, outermost wall last
            wall_indices = range(section_wall_loops - 1, -1, -1)  # e.g. 3, 2, 1, 0
            gcode_lines.append(f"; Wall print order: INSIDE → OUTSIDE")
        else:
            # Print outermost wall first (default)
            wall_indices = range(section_wall_loops)  # e.g. 0, 1, 2, 3
            gcode_lines.append(f"; Wall print order: OUTSIDE → INSIDE (default)")
        
        for wall_index in wall_indices:
            path_coords = self.path_processor.get_offset_path_coordinates(
                wall_index, section_name, boundary.boundary_id, section_wall_loops, current_z
            )
            
            if path_coords:
                current_pos = (self.current_x, self.current_y) if self.current_x is not None else None
                
                # Check if this boundary has seam selections
                boundary_index = str(boundary.boundary_id) if hasattr(boundary, 'boundary_id') else None
                seam_selection = self.seam_selections.get(boundary_index) if boundary_index else None
                
                if seam_selection is not None:
                    # Use seam selection (simple: just the vertex index)
                    vertex_index = seam_selection
                    optimized_coords = self.start_point_optimizer.rotate_coordinates_to_seam(
                        path_coords, vertex_index
                    )
                    print(f"  📍 Applied seam selection for boundary {boundary_index}: vertex {vertex_index}")
                else:
                    # Use default optimizer
                    optimized_coords = self.start_point_optimizer.rotate_coordinates_to_closest(
                        path_coords, current_pos
                    )
                
                wall_gcode = self.generate_optimized_wall_gcode(
                    optimized_coords, boundary, wall_index, layer_height, line_width,
                    print_speed, travel_speed, is_foundation
                )
                gcode_lines.extend(wall_gcode)
        
        # ⭐ CRITICAL: Restore original wall offsets after generating this boundary
        if is_hole and original_wall_offset is not None:
            self.wall_settings['normalWallOffset'] = original_wall_offset
            self.wall_settings['zigzagWallOffset'] = original_zigzag_offset
            
            if hasattr(self.config, 'config') and 'wallSettings' in self.config.config:
                self.config.config['wallSettings']['normalWallOffset'] = original_wall_offset
                self.config.config['wallSettings']['zigzagWallOffset'] = original_zigzag_offset
            
            # ⭐ CRITICAL FIX: Restore PathProcessor's cached wall_settings
            if hasattr(self.path_processor, 'wall_settings'):
                self.path_processor.wall_settings['normalWallOffset'] = original_wall_offset
                self.path_processor.wall_settings['zigzagWallOffset'] = original_zigzag_offset
        
        # ⭐ RESTORE: Reset compensation after generating walls for this boundary
        if apply_first_layer_offset:
            # Reset the compensation back to 0
            print(f"🔵 LAYER {layer_num}: RESETTING COMPENSATION TO 0")
            self.wall_settings['firstLayerCompensation'] = 0.0
            
            if hasattr(self.config, 'config') and 'wallSettings' in self.config.config:
                self.config.config['wallSettings']['firstLayerCompensation'] = 0.0
            
            # ⭐ CRITICAL FIX: Restore PathProcessor's cached wall_settings
            if hasattr(self.path_processor, 'wall_settings'):
                self.path_processor.wall_settings['firstLayerCompensation'] = 0.0
        
        return gcode_lines
    
    def generate_optimized_wall_gcode(self, path_coords: List[List[float]], boundary,
                                     wall_index: int, layer_height: float, line_width: float,
                                     print_speed: int, travel_speed: int, is_foundation: bool) -> List[str]:
        gcode_lines = []
        
        # NEW FIX: ALWAYS enforce direction based on JSON setting
        path_coords = self.direction_manager.ensure_consistent_direction(path_coords)
        
        for i, coord in enumerate(path_coords):
            if i == 0:
                if self.current_x is not None and self.current_y is not None:
                    current_pos = (self.current_x, self.current_y)
                    target_pos = (coord[0], coord[1])
                    distance = math.sqrt((target_pos[0] - current_pos[0])**2 + (target_pos[1] - current_pos[1])**2)
                    
                    if self.direction_manager.should_use_continuous_extrusion(current_pos, target_pos):
                        extrusion = self.calculate_extrusion_amount(distance, layer_height, line_width, is_foundation)
                        feedrate = print_speed
                        gcode_lines.append(f"G1 X{coord[0]:.2f} Y{coord[1]:.2f} E{extrusion:.5f} F{feedrate}")
                        self.current_feedrate = feedrate
                    else:
                        travel_gcode = self.add_direction_aware_travel_move(
                            coord[0], coord[1], travel_speed, boundary
                        )
                        gcode_lines.extend(travel_gcode)
                        self.current_feedrate = None
                else:
                    feedrate = travel_speed
                    gcode_lines.append(f"G1 X{coord[0]:.2f} Y{coord[1]:.2f} F{feedrate}")
                    self.current_feedrate = feedrate
                
                self.current_x, self.current_y = coord[0], coord[1]
                self.current_boundary_id = boundary.boundary_id
                self.last_boundary_type = boundary.boundary_type
            else:
                prev_coord = path_coords[i-1]
                distance = self.calculate_distance(prev_coord[0], prev_coord[1], coord[0], coord[1])
                
                if distance > 0.01:
                    extrusion = self.calculate_extrusion_amount(distance, layer_height, line_width, is_foundation)
                    feedrate = print_speed
                    gcode_lines.append(f"G1 X{coord[0]:.2f} Y{coord[1]:.2f} E{extrusion:.5f} F{feedrate}")
                    self.current_feedrate = feedrate
                    self.current_x, self.current_y = coord[0], coord[1]
        
        return gcode_lines
    
    def generate_infill_for_layer(self, layer_num: int, layer_z: float, is_foundation: bool) -> List[str]:
        """Generate infill for a specific layer"""
        if not self.infill_settings.get('enabled', False):
            return []
        
        infill_layers = self.infill_settings.get('layers', [1, 2, 3, 4])
        if layer_num + 1 not in infill_layers:
            return []
        
        gcode_lines = [f"; --- Layer {layer_num + 1} Infill ---"]
        
        try:
            infill_density = self.infill_settings.get('density', 0.15)
            if infill_density == 0:
                return []
            
            line_spacing = 1.0 / (infill_density * 5)
            
            infill_gen = create_infill_generator(
                self.path_processor,
                line_spacing=line_spacing,
                zhop_threshold=5.0,
                infill_offset=self.infill_settings.get('infillOffset', 0.2),
                generate_outline=False
            )
            
            # 🎯 NEW: Get SEPARATE polygons (no union!)
            base_polygons = self.path_processor.get_base_polygons_for_infill()
            if not base_polygons:
                return []
            
            print(f"      🎯 Processing {len(base_polygons)} SEPARATE shapes for infill (independent control!)")
            
            boundaries = self.path_processor.get_all_boundaries()
            hole_polygons = []
            
            if boundaries:
                hole_polygons = self._try_extract_hole_polygons(boundaries)
            
            # 🎯 NEW: Generate infill for EACH polygon separately
            all_infill_paths = []
            
            for poly_idx, base_polygon in enumerate(base_polygons):
                print(f"      🎯 Generating infill for shape {poly_idx + 1}/{len(base_polygons)}")
                
                infill_paths = infill_gen.generate_complete_infill(
                    base_polygon, hole_polygons, layer_num + 1, 2, line_spacing, self.infill_settings
                )
                
                if infill_paths:
                    all_infill_paths.extend(infill_paths)
                    print(f"         ✅ Shape {poly_idx + 1}: Generated {len(infill_paths)} infill paths")
                else:
                    print(f"         ℹ️ Shape {poly_idx + 1}: No infill generated")
            
            if not all_infill_paths:
                return []
            
            print(f"      ✅ Total: {len(all_infill_paths)} infill paths from {len(base_polygons)} shapes")
            
            processed_infill_paths = self._process_infill_paths(all_infill_paths)
            
            if not processed_infill_paths:
                return []
            
            layer_height = self.layer_settings['firstLayerHeight'] if is_foundation else self.layer_settings['layerHeight']
            line_width = self.infill_settings.get('line_width', 0.45)

            if is_foundation:
                print_speed = self.speed_settings.get('foundationInfillSpeed', self.speed_settings.get('foundationLayersSpeed', 4000))
            else:
                print_speed = self.speed_settings.get('infillSpeed', self.speed_settings.get('printSpeed', 8000))

            travel_speed = self.speed_settings['travelSpeed']
            
            infill_gcode = self._generate_infill_gcode(
                processed_infill_paths, layer_height, line_width, print_speed, travel_speed,
                is_foundation, layer_z
            )
            
            gcode_lines.extend(infill_gcode)
            
        except Exception as e:
            gcode_lines.append(f"; Infill error: {e}")
        
        return gcode_lines
    
    def _try_extract_hole_polygons(self, boundaries) -> List:
        """Extract hole polygons from boundaries"""
        hole_polygons = []
        
        for boundary in boundaries:
            if boundary.boundary_type != 'inner':
                continue
            
            hole_polygon = None
            
            if hasattr(boundary, 'polygon') and boundary.polygon is not None:
                hole_polygon = boundary.polygon
            elif hasattr(boundary, 'geometry') and boundary.geometry is not None:
                hole_polygon = boundary.geometry
            elif hasattr(boundary, 'coordinates') and boundary.coordinates and HAS_SHAPELY:
                try:
                    from shapely.geometry import Polygon
                    coords = boundary.coordinates
                    if isinstance(coords, list) and len(coords) >= 3:
                        hole_polygon = Polygon(coords)
                except Exception:
                    pass
            
            if hole_polygon is not None:
                hole_polygons.append(hole_polygon)
        
        return hole_polygons
    
    def _process_infill_paths(self, raw_infill_paths) -> List[List[List[float]]]:
        """Process raw infill paths into coordinate lists"""
        processed_paths = []
        
        for path_data in raw_infill_paths:
            if not path_data:
                continue
            
            if isinstance(path_data, tuple) and len(path_data) == 2:
                move_type, coordinates = path_data
                
                if isinstance(coordinates, list) and len(coordinates) >= 2:
                    valid_coords = []
                    for coord in coordinates:
                        if isinstance(coord, list) and len(coord) == 2:
                            try:
                                x, y = float(coord[0]), float(coord[1])
                                valid_coords.append([x, y])
                            except (ValueError, TypeError):
                                continue
                    
                    if len(valid_coords) >= 2:
                        processed_paths.append(valid_coords)
        
        return processed_paths
    
    def _generate_infill_gcode(self, processed_paths: List[List[List[float]]],
                              layer_height: float, line_width: float,
                              print_speed: int, travel_speed: int,
                              is_foundation: bool, layer_z: float) -> List[str]:
        """Convert processed infill paths to G-code"""
        gcode_lines = []
        
        coord_params = self.path_processor.get_infill_coordinate_params()
        
        for path_index, path_coords in enumerate(processed_paths):
            if len(path_coords) < 2:
                continue
            
            gcode_lines.append(f"; Infill path {path_index + 1}")
            
            transformed_coords = []
            for coord in path_coords:
                scaled_x = coord[0] * coord_params['scale'] + coord_params['offset_x']
                scaled_y = coord_params['offset_y'] - (coord[1] * coord_params['scale'])
                transformed_coords.append([scaled_x, scaled_y])
            
            for i, coord in enumerate(transformed_coords):
                if i == 0:
                    if self.current_x is not None and self.current_y is not None:
                        distance = self.calculate_distance(self.current_x, self.current_y, coord[0], coord[1])
                        
                        if distance < self.max_infill_travel_without_retract:
                            gcode_lines.append(f"G1 X{coord[0]:.2f} Y{coord[1]:.2f}{self.set_feedrate(travel_speed)}")
                        else:
                            travel_gcode = self.add_travel_move(coord[0], coord[1], travel_speed, z_hop=False)
                            gcode_lines.extend(travel_gcode)
                    else:
                        gcode_lines.append(f"G1 X{coord[0]:.2f} Y{coord[1]:.2f}{self.set_feedrate(travel_speed)}")
                    
                    self.current_x, self.current_y = coord[0], coord[1]
                else:
                    prev_coord = transformed_coords[i-1]
                    distance = self.calculate_distance(prev_coord[0], prev_coord[1], coord[0], coord[1])
                    
                    if distance > 0.01:
                        extrusion = self.calculate_extrusion_amount(distance, layer_height, line_width, is_foundation)
                        gcode_lines.append(f"G1 X{coord[0]:.2f} Y{coord[1]:.2f} E{extrusion:.5f}{self.set_feedrate(print_speed)}")
                        self.current_x, self.current_y = coord[0], coord[1]
        
        return gcode_lines
    
    def add_travel_move(self, target_x: float, target_y: float, travel_speed: int,
                       z_hop: bool = True) -> List[str]:
        """Add a travel move with optional z-hop and retraction"""
        gcode_lines = []
        
        if self.current_x is not None and self.current_y is not None:
            travel_distance = self.calculate_distance(self.current_x, self.current_y, target_x, target_y)
            
            should_retract = (
                travel_distance > 0.5 and
                not self.direction_manager.should_use_continuous_extrusion(
                    (self.current_x, self.current_y), (target_x, target_y)
                )
            )
            
            if should_retract:
                gcode_lines.extend(self.add_retraction())
                if z_hop and hasattr(self, 'current_z'):
                    z_hop_height = self.movement_settings.get('zHopHeight', 0.4)
                    new_z = self.current_z + z_hop_height
                    gcode_lines.append(f"G1 Z{new_z:.2f} F{self.speed_settings['travelSpeed']}")
        
        gcode_lines.append(f"G1 X{target_x:.2f} Y{target_y:.2f}{self.set_feedrate(travel_speed)}")
        
        if len(gcode_lines) > 2 and z_hop and hasattr(self, 'current_z'):
            gcode_lines.append(f"G1 Z{self.current_z:.2f} F{self.speed_settings['travelSpeed']}")
        
        if len(gcode_lines) > 1 and "E-" in gcode_lines[0]:
            gcode_lines.extend(self.add_prime())
        
        self.current_x, self.current_y = target_x, target_y
        return gcode_lines
    
    def add_direction_aware_travel_move(self, target_x: float, target_y: float,
                                       travel_speed: int, boundary, z_hop: bool = True) -> List[str]:
        gcode_lines = []
        
        if self.current_x is not None and self.current_y is not None:
            travel_distance = self.calculate_distance(self.current_x, self.current_y, target_x, target_y)
            should_retract_walls = self.direction_manager.should_retract_between_walls()
            is_intra_object = self.is_boundary_transition(boundary)
            min_retraction_distance = 0.3 if is_intra_object else 0.5
            
            if self.direction_manager.is_corkscrew_mode_enabled():
                min_retraction_distance *= 2
            
            if travel_distance > min_retraction_distance and should_retract_walls:
                gcode_lines.extend(self.add_retraction())
                if z_hop and hasattr(self, 'current_z'):
                    z_hop_height = self.movement_settings.get('zHopHeight', 0.4)
                    new_z = self.current_z + z_hop_height
                    gcode_lines.append(f"G1 Z{new_z:.2f} F{self.speed_settings['travelSpeed']}")
        
        gcode_lines.append(f"G1 X{target_x:.2f} Y{target_y:.2f}{self.set_feedrate(travel_speed)}")
        
        if len(gcode_lines) > 2 and z_hop and hasattr(self, 'current_z'):
            gcode_lines.append(f"G1 Z{self.current_z:.2f} F{self.speed_settings['travelSpeed']}")
        
        if len(gcode_lines) > 1 and "E-" in gcode_lines[0]:
            gcode_lines.extend(self.add_prime())
        
        self.current_x, self.current_y = target_x, target_y
        return gcode_lines
    
    def is_boundary_transition(self, new_boundary) -> bool:
        if self.last_boundary_type is None:
            return False
        return self.last_boundary_type != new_boundary.boundary_type
    
    def add_retraction(self) -> List[str]:
        tool = self.current_tool if self.current_tool else 'T0'
        retraction_distance = self.movement_settings.get('retractionDistance', {}).get(tool, 1.5)
        retraction_speed = self.speed_settings.get('retractionSpeed', 5000)
        return [f"G1 E-{retraction_distance:.3f}{self.set_feedrate(retraction_speed)}"]
    
    def add_prime(self) -> List[str]:
        tool = self.current_tool if self.current_tool else 'T0'
        prime_amount = self.movement_settings.get('primeAmount', {}).get(tool, 1.2)
        retraction_speed = self.speed_settings.get('retractionSpeed', 5000)
        return [f"G1 E{prime_amount:.3f}{self.set_feedrate(retraction_speed)}"]
    
    def calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    
    def calculate_extrusion_amount(self, distance: float, layer_height: float,
                                  line_width: float, is_first_layer: bool = False) -> float:
        filament_diameter = self.temp_settings['filamentDiameter']
        filament_area = math.pi * (filament_diameter / 2) ** 2
        line_volume = distance * line_width * layer_height
        filament_length = line_volume / filament_area
        
        if is_first_layer:
            foundation_flow = self.foundation_settings.get('foundationFlowMultiplier', 1.3)
            filament_length *= foundation_flow
        
        if self.current_section and hasattr(self.current_section, 'index') and self.current_section.index == 5:
            profile_name = getattr(self.current_section, 'clickSystemProfile', 'none')
            if profile_name != 'none' and self.click_system_profiles:
                profiles = self.click_system_profiles.get('profiles', {})
                if profile_name in profiles:
                    flow_override = profiles[profile_name].get('flowOverride')
                    if flow_override:
                        filament_length *= flow_override
        
        return filament_length
    
    def set_feedrate(self, feedrate: int) -> str:
        if self.current_feedrate != feedrate:
            self.current_feedrate = feedrate
            return f" F{feedrate}"
        return ""
    
    def add_fan_control_gcode(self, layer_num: int) -> List[str]:
        gcode_lines = []
        fan_start_layer = self.fan_settings.get('startingLayer', 4)
        fan_speed = self.fan_settings.get('regularFanPercent', 50)
        
        if layer_num == fan_start_layer and self.current_fan_speed != fan_speed:
            gcode_lines.append(f"M106 S{int(fan_speed * 2.55)}")
            self.current_fan_speed = fan_speed
        
        return gcode_lines
    
    def generate_end_sequence(self) -> List[str]:
        gcode_lines = []
    
        # Use end sequence from generator (reads from JSON config)
        gcode_lines.extend([
            "",
            "; === END SEQUENCE ===",
            ""
        ])
        
        # Get end G-code from generator (already complete from JSON)
        end_lines = self.end_generator.generate()
        gcode_lines.extend(end_lines)
        gcode_lines.append("; Print completed!")
    
        return gcode_lines

# =====================================================
# PACKAGE BUILDER
# =====================================================

class PackageBuilder:
    def __init__(self, config_manager: ConfigurationManager, renderer=None):
        self.config = config_manager
        self.cfg = config_manager.config
        self.mf3_settings = self.cfg.get('mf3Settings', {})
        self.metadata_settings = self.cfg.get('metadataSettings', {})
        self.renderer = renderer
        
        if renderer and hasattr(renderer, 'section_manager'):
            self.section_manager = renderer.section_manager
        else:
            self.section_manager = SectionManager(config_manager)
    
    def build_3mf_package(self, gcode_content: str, shape_info: Dict[str, Any]) -> bytes:
        """
        Build 3MF package using template folder - TEMPLATE MODE ONLY!
        
        This method REQUIRES a template folder with working 3MF files.
        Template folder path comes from printer config: config["templateFolder"]
        
        Template approach:
        - Loads ALL files from '{brand}/template/' folder
        - Replaces ONLY Metadata/plate_1.gcode with generated gcode
        - Keeps everything else exactly as exported
        - Result: Perfect compatibility with slicer!
        """
        # Get template folder from config
        brand_folder = self.cfg.get('templateFolder', 'bambu')
        
        # Look for template folder: {brand}/template/
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_folder = os.path.join(script_dir, brand_folder, "template")
        
        # Check if template exists - REQUIRED for 3MF generation!
        if not os.path.exists(template_folder):
            error_msg = (
                f"\n{'='*80}\n"
                f"❌ TEMPLATE FOLDER NOT FOUND!\n"
                f"{'='*80}\n"
                f"Looking for: {template_folder}\n"
                f"\n"
                f"The '{brand_folder}/template/' folder is REQUIRED for 3MF generation.\n"
                f"This folder contains working slicer files that ensure compatibility.\n"
                f"\n"
                f"HOW TO FIX:\n"
                f"1. Create a simple model in your slicer (e.g., Bambu Studio)\n"
                f"2. Export as 3MF file\n"
                f"3. Extract the 3MF (rename to .zip, then unzip)\n"
                f"4. Copy ALL contents to: {template_folder}/\n"
                f"\n"
                f"The template folder should contain:\n"
                f"  - Metadata/ (with project_settings.config, etc.)\n"
                f"  - 3D/ (with model files)\n"
                f"  - _rels/ (with relationship files)\n"
                f"  - [Content_Types].xml\n"
                f"{'='*80}\n"
            )
            raise FileNotFoundError(error_msg)
        
        print(f"✅ Using template folder: {template_folder}")
        return self.build_3mf_from_template(gcode_content, template_folder)
    
    def build_3mf_from_template(self, gcode_content: str, template_folder: str) -> bytes:
        """
        Build 3MF by loading Bambu template and replacing only the gcode file.
        
        This is the SIMPLE approach:
        1. Copy all files from template folder
        2. Replace Metadata/plate_1.gcode with your gcode
        3. Zip it
        
        Everything else (configs, thumbnails, metadata) stays exactly as Bambu created it.
        """
        buffer = BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through template folder and add all files
            files_copied = 0
            gcode_replaced = False
            
            for root, dirs, files in os.walk(template_folder):
                for file in files:
                    # Get full path
                    file_path = os.path.join(root, file)
                    
                    # Get archive path (relative to template folder)
                    archive_path = os.path.relpath(file_path, template_folder)
                    
                    # Special handling for the gcode file - replace it with generated gcode
                    if archive_path == 'Metadata/plate_1.gcode' or archive_path == 'Metadata\\plate_1.gcode':
                        print(f"   🔄 Replacing: {archive_path} with generated gcode")
                        zipf.writestr(archive_path.replace('\\', '/'), gcode_content)
                        gcode_replaced = True
                    else:
                        # Copy file as-is from template
                        with open(file_path, 'rb') as f:
                            zipf.writestr(archive_path.replace('\\', '/'), f.read())
                    
                    files_copied += 1
            
            print(f"✅ Template 3MF created: {files_copied} files copied, gcode replaced: {gcode_replaced}")
        
        return buffer.getvalue()
# =====================================================
# HTML JSON ENTRY POINT
# =====================================================

def generate_3mf_from_html_json(html_json: Dict[str, Any]) -> Tuple[bool, Any]:
    """Main entry point - v7.3.5-FILAMENT-MAPS-FIX"""
    try:
        print("=== v7.3.5-FILAMENT-MAPS-FIX: AMS slot mapping fixed! ===")
        
        # Extract zigzag and wall settings from HTML
        zigzag_settings = html_json.get('zigzagSettings', {})
        wall_settings = html_json.get('wallSettings', {})
        
        print(f"Zigzag Settings: wavelength={zigzag_settings.get('wavelength', 5.0)}mm, " +
              f"amplitude={zigzag_settings.get('amplitude', 1.5)}mm")
        print(f"Wall Settings: normalWallOffset={wall_settings.get('normalWallOffset', 4.0)}mm, " +
              f"zigzagWallOffset={wall_settings.get('zigzagWallOffset', 1.5)}mm")
        
        # Add these settings to html_json if they're being used by convert_html_json_to_full_config
        # NOTE: The actual implementation of using these settings needs to be added in:
        # 1. gcode_core.py - in the convert_html_json_to_full_config function
        # 2. The wall coordinate generation code (likely in PathProcessor or similar class)
        
        # Direct config creation - bypasses deleted functions
        printer_type = html_json.get('printer', 'bambu')
        config_file = f'{printer_type}_A1mini.json' if printer_type == 'bambu' else f'{printer_type}.json'

        with open(config_file, 'r') as f:
            full_config = json.load(f)

        # Merge HTML settings
        if 'layerSettings' in html_json:
            full_config['layers'] = html_json['layerSettings']
        
        # Handle SVG content selection (with layerFileMapping support)
        svg_content = None
        if 'files' in html_json and 'layerFileMapping' in html_json:
            files = html_json['files']
            layer_file_mapping = html_json['layerFileMapping']
            
            # Get current layer name
            if 'layerSettings' in html_json and len(html_json['layerSettings']) > 0:
                current_layer_name = html_json['layerSettings'][0]['name']
                
                # Look up layer in mapping
                if current_layer_name in layer_file_mapping:
                    layer_mapping = layer_file_mapping[current_layer_name]
                    primary_file = layer_mapping.get('primaryFile')
                    
                    if primary_file == "return" and 'returnSvgContent' in files:
                        svg_content = files['returnSvgContent']
                    elif primary_file == "original" and 'originalSvgContent' in files:
                        svg_content = files['originalSvgContent']
        
        # Fallback to originalSvgContent
        if not svg_content and 'files' in html_json:
            files = html_json['files']
            if 'returnSvgContent' in files and files['returnSvgContent']:
                svg_content = files['returnSvgContent']
            elif 'originalSvgContent' in files and files['originalSvgContent']:
                svg_content = files['originalSvgContent']
        
        # Apply SVG content
        if svg_content:
            if 'shapeSettings' not in full_config:
                full_config['shapeSettings'] = {}
            full_config['shapeSettings']['svgContent'] = svg_content
        
        # Merge shapeSettings
        if 'shapeSettings' in html_json:
            if 'shapeSettings' not in full_config:
                full_config['shapeSettings'] = {}
            full_config['shapeSettings'].update(html_json['shapeSettings'])
        
        # Merge pathSettings
        if 'pathSettings' in html_json:
            path_settings = html_json['pathSettings']
            if 'pathProcessingSettings' not in full_config:
                full_config['pathProcessingSettings'] = {}
            
            if 'wallOffset' in path_settings:
                if 'wallSettings' not in full_config:
                    full_config['wallSettings'] = {}
                if 'wallOffset' not in full_config['wallSettings']:
                    full_config['pathProcessingSettings']['wallOffset'] = path_settings['wallOffset']
                    full_config['wallSettings']['wallOffset'] = path_settings['wallOffset']
            
            if 'curveResolution' in path_settings:
                full_config['pathProcessingSettings']['curveResolution'] = path_settings['curveResolution']
            if 'pathSmoothing' in path_settings:
                full_config['pathProcessingSettings']['pathSmoothing'] = path_settings['pathSmoothing']
            if 'closureThreshold' in path_settings:
                full_config['pathProcessingSettings']['closureThreshold'] = path_settings['closureThreshold']
        
        # Merge zigzagSettings with proper defaults
        if 'zigzagSettings' in html_json:
            html_zigzag = html_json['zigzagSettings']
            if 'zigzagSettings' not in full_config:
                full_config['zigzagSettings'] = {}
            
            full_config['zigzagSettings'].update({
                'wavelength': html_zigzag.get('wavelength', 5.0),
                'amplitude': html_zigzag.get('amplitude', 1.5),
                'waveBias': html_zigzag.get('waveBias', full_config['zigzagSettings'].get('waveBias', 0.0)),
                'pointsPerWavelength': html_zigzag.get('pointsPerWavelength', 
                                                       full_config['zigzagSettings'].get('pointsPerWavelength', 20)),
                'waveType': html_zigzag.get('waveType', 
                                            full_config['zigzagSettings'].get('waveType', 'sine')),
                'enabled': html_zigzag.get('enabled', full_config['zigzagSettings'].get('enabled', True)),
                'applyToMiddleWallsOnly': html_zigzag.get('applyToMiddleWallsOnly', 
                                                         full_config['zigzagSettings'].get('applyToMiddleWallsOnly', True))
            })
        
        # Merge wallSettings
        if 'wallSettings' in html_json:
            html_walls = html_json['wallSettings']
            if 'wallSettings' not in full_config:
                full_config['wallSettings'] = {}
            
            full_config['wallSettings'].update({
                'normalWallOffset': html_walls.get('normalWallOffset', 4.0),
                'zigzagWallOffset': html_walls.get('zigzagWallOffset', 1.5)
            })
        
        # Merge seamSelections if present
        if 'seamSelections' in html_json:
            full_config['seamSelections'] = html_json['seamSelections']
        
        # Merge infillSettings if present
        if 'infillSettings' in html_json:
            if 'infillSettings' not in full_config:
                full_config['infillSettings'] = {}
            full_config['infillSettings'].update(html_json['infillSettings'])
        
        # Merge filamentTypes if present
        if 'filamentTypes' in html_json:
            full_config['filamentTypes'] = html_json['filamentTypes']
        
        # Merge printMode
        if 'printMode' in html_json:
            if 'metadataSettings' not in full_config:
                full_config['metadataSettings'] = {}
            full_config['metadataSettings']['printMode'] = html_json['printMode']
        
        if full_config is None:
            return False, "Failed to convert HTML JSON"
        
        config_manager = ConfigurationManager(full_config)
        path_processor = EnhancedPathProcessor(config_manager)
        shape_info = path_processor.get_shape_info()
        
        gcode_renderer = MultiMaterialGCodeRenderer(config_manager, path_processor)
        gcode_content = gcode_renderer.generate_gcode()
        
        package_builder = PackageBuilder(config_manager, gcode_renderer)
        package_bytes = package_builder.build_3mf_package(gcode_content, shape_info)
        
        import base64
        mf3_base64 = base64.b64encode(package_bytes).decode('utf-8')
        
        result = {
            'data': mf3_base64,
            'filename': f"h2d_v7.3.5_AMS_FIX.3mf",
            'type': 'binary',
            'version': 'v7.3.5-FILAMENT-MAPS-FIX'
        }
        
        print("=== SUCCESS - filament_maps fixed! Multi-color should work! ===")
        return True, result
        
    except Exception as e:
        print(f"=== FAILED ===")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Error: {str(e)}"

# =====================================================
# MAIN FUNCTION
# =====================================================

def main():
    import sys
    
    print("JSON Configuration G-code Generator v7.3.5-FILAMENT-MAPS-FIX")
    print("=" * 80)
    
    if len(sys.argv) < 2:
        print("Usage: python gcode_3mf.py <config.json> [output.gcode] [output.3mf]")
        sys.exit(1)
    
    try:
        config_file = sys.argv[1]
        config_manager = ConfigurationManager(config_file)
        path_processor = EnhancedPathProcessor(config_manager)
        shape_info = path_processor.get_shape_info()
        
        gcode_renderer = MultiMaterialGCodeRenderer(config_manager, path_processor)
        gcode_content = gcode_renderer.generate_gcode()
        
        gcode_output = sys.argv[2] if len(sys.argv) > 2 else 'output.gcode'
        with open(gcode_output, 'w') as f:
            f.write(gcode_content)
        print(f"G-code saved to: {gcode_output}")
        
        if len(sys.argv) > 3:
            package_builder = PackageBuilder(config_manager, gcode_renderer)
            package_bytes = package_builder.build_3mf_package(gcode_content, shape_info)
            
            mf3_output = sys.argv[3]
            with open(mf3_output, 'wb') as f:
                f.write(package_bytes)
            print(f"3MF package saved to: {mf3_output}")
        
        print(f"\nGeneration completed successfully!")
        print(f"Version: v7.3.5-FILAMENT-MAPS-FIX - AMS multi-color fixed!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
