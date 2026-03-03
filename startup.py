#!/usr/bin/env python3
"""
GENERIC STARTUP/END GCODE GENERATOR
Reads startup and end G-code from printer JSON configuration
No hardcoded printer names or file paths
"""

import json
import os
from typing import List, Dict, Any

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class StartupGenerator:
    """Generic startup G-code generator - reads from printer JSON config"""
    
    def __init__(self, config: Dict[str, Any] = None, config_path: str = None):
        """
        Initialize with either a config dict or path to config file
        
        Args:
            config: Full printer configuration dict (preferred)
            config_path: Path to printer JSON file (fallback)
        """
        if config is not None:
            self.config = config
        elif config_path is not None:
            # Load from file path
            if not os.path.exists(config_path):
                config_path = os.path.join(SCRIPT_DIR, config_path)
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            raise ValueError("Must provide either config dict or config_path")
        
        # Read startup G-code from JSON or external file
        if 'startupGcodeFile' in self.config:
            # Load from external file
            startup_file = self.config['startupGcodeFile']
            brand_folder = self.config.get('templateFolder', '')
            
            # Try brand folder first: qidi/qidi_startup.txt
            if brand_folder:
                startup_path = os.path.join(SCRIPT_DIR, brand_folder, startup_file)
                if os.path.exists(startup_path):
                    with open(startup_path, 'r') as f:
                        self.startup_gcode = f.read()
                    print(f"✅ Loaded startup from: {brand_folder}/{startup_file}")
                else:
                    # Try root: qidi_startup.txt
                    startup_path = os.path.join(SCRIPT_DIR, startup_file)
                    if os.path.exists(startup_path):
                        with open(startup_path, 'r') as f:
                            self.startup_gcode = f.read()
                        print(f"✅ Loaded startup from: {startup_file}")
                    else:
                        print(f"⚠️ Startup file not found: {startup_file}")
                        self.startup_gcode = ''
            else:
                startup_path = os.path.join(SCRIPT_DIR, startup_file)
                if os.path.exists(startup_path):
                    with open(startup_path, 'r') as f:
                        self.startup_gcode = f.read()
                else:
                    self.startup_gcode = ''
        else:
            # Read from JSON (old way)
            self.startup_gcode = self.config.get('startupGcode', '')
        
        # If no startup G-code in JSON, try legacy field or use minimal fallback
        if not self.startup_gcode:
            self.startup_gcode = self.config.get('startGcodeSettings', {}).get('customStartGcode', '')
        
        if not self.startup_gcode:
            print("WARNING: No startup G-code found in config, using minimal startup")
            self.startup_gcode = self._get_minimal_startup()
    
    def _get_minimal_startup(self) -> str:
        """Minimal generic startup sequence as fallback"""
        return """; === GENERIC MINIMAL STARTUP ===
G90 ; Absolute positioning
M83 ; Relative extrusion
M220 S100 ; Reset feedrate
M221 S100 ; Reset flow rate

M140 S60 ; Set bed temp
M104 S200 ; Set nozzle temp
G28 ; Home all axes
M190 S60 ; Wait for bed
M109 S200 ; Wait for nozzle

G92 E0 ; Reset extruder
; === STARTUP COMPLETE ===
"""
    
    def generate(self, nozzle_temp: int = None, bed_temp: int = None, 
                 filament_type: str = None, chamber_temp: int = None,
                 nozzle_temp_initial: int = None, 
                 filament_id: int = 0,
                 starting_tool: str = "T0",
                 printer_name: str = None) -> List[str]:
        """
        Generate startup G-code with temperature substitutions
        
        Replaces placeholder values in startup G-code template with actual values
        from JSON config or parameters
        """
        temps = self.config.get('temperatureSettings', {})
        
        # Use parameters if provided, otherwise fall back to JSON config
        if nozzle_temp is None:
            nozzle_temp = temps.get('nozzleTemp', {}).get(starting_tool, 200)
        if nozzle_temp_initial is None:
            nozzle_temp_initial = temps.get('nozzleTempInitialLayer', {}).get(starting_tool, nozzle_temp)
        if bed_temp is None:
            bed_temp = temps.get('bedTemp', 60)
        if chamber_temp is None:
            chamber_temp = temps.get('chamberTemp', 0)
        if filament_type is None:
            filament_type = temps.get('filamentType', 'PLA')
        
        # Start with template from JSON
        gcode = self.startup_gcode
        
        # Replace common temperature placeholders
        # Support multiple temperature values that might be in templates
        
        # Nozzle temperatures - try common values
        for temp_value in [270, 255, 240, 230, 220, 210, 200, 190, 180, 170, 160, 150, 140]:
            gcode = gcode.replace(f'M104 S{temp_value}', f'M104 S{nozzle_temp}')
            gcode = gcode.replace(f'M109 S{temp_value}', f'M109 S{nozzle_temp}')
        
        # Bed temperatures - try common values
        for temp_value in [110, 100, 90, 80, 70, 60, 50, 40]:
            gcode = gcode.replace(f'M140 S{temp_value}', f'M140 S{bed_temp}')
            gcode = gcode.replace(f'M190 S{temp_value}', f'M190 S{bed_temp}')
        
        # Chamber temperature (if applicable)
        gcode = gcode.replace('M141 S60', f'M141 S{chamber_temp}')
        gcode = gcode.replace('M141 S50', f'M141 S{chamber_temp}')
        
        # Replace Bambu-specific filament type commands (if present)
        gcode = gcode.replace('M1002 set_filament_type:PC', f'M1002 set_filament_type:{filament_type}')
        gcode = gcode.replace('M1002 set_filament_type:PETG', f'M1002 set_filament_type:{filament_type}')
        gcode = gcode.replace('M1002 set_filament_type:PLA', f'M1002 set_filament_type:{filament_type}')
        gcode = gcode.replace('M1002 set_filament_type:ABS', f'M1002 set_filament_type:{filament_type}')
        
        # Replace AMS slot selection (Bambu-specific, if present)
        gcode = gcode.replace('M620 S0A', f'M620 S{filament_id}A')
        gcode = gcode.replace('M621 S0A', f'M621 S{filament_id}A')
        
        # Replace tool selection
        gcode = gcode.replace('\nT0\n', f'\n{starting_tool}\n')
        
        return gcode.split('\n')


class EndSequenceGenerator:
    """Generic end sequence generator - reads from printer JSON config"""
    
    def __init__(self, config: Dict[str, Any] = None, config_path: str = None):
        """
        Initialize with either a config dict or path to config file
        
        Args:
            config: Full printer configuration dict (preferred)
            config_path: Path to printer JSON file (fallback)
        """
        if config is not None:
            self.config = config
        elif config_path is not None:
            # Load from file path
            if not os.path.exists(config_path):
                config_path = os.path.join(SCRIPT_DIR, config_path)
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            raise ValueError("Must provide either config dict or config_path")
        
        # Read end G-code from JSON or external file
        if 'endGcodeFile' in self.config:
            # Load from external file
            end_file = self.config['endGcodeFile']
            brand_folder = self.config.get('templateFolder', '')
            
            # Try brand folder first: qidi/qidi_end.txt
            if brand_folder:
                end_path = os.path.join(SCRIPT_DIR, brand_folder, end_file)
                if os.path.exists(end_path):
                    with open(end_path, 'r') as f:
                        self.end_gcode = f.read()
                    print(f"✅ Loaded end code from: {brand_folder}/{end_file}")
                else:
                    # Try root
                    end_path = os.path.join(SCRIPT_DIR, end_file)
                    if os.path.exists(end_path):
                        with open(end_path, 'r') as f:
                            self.end_gcode = f.read()
                        print(f"✅ Loaded end code from: {end_file}")
                    else:
                        print(f"⚠️ End file not found: {end_file}")
                        self.end_gcode = ''
            else:
                end_path = os.path.join(SCRIPT_DIR, end_file)
                if os.path.exists(end_path):
                    with open(end_path, 'r') as f:
                        self.end_gcode = f.read()
                else:
                    self.end_gcode = ''
        else:
            # Read from JSON (old way)
            self.end_gcode = self.config.get('endGcode', '')
        
        # If no end G-code in JSON, try legacy field or use minimal fallback
        if not self.end_gcode:
            self.end_gcode = self.config.get('endGcodeSettings', {}).get('customEndGcode', '')
        
        if not self.end_gcode:
            print("WARNING: No end G-code found in config, using minimal end sequence")
            self.end_gcode = self._get_minimal_end_sequence()
    
    def _get_minimal_end_sequence(self) -> str:
        """Minimal generic end sequence as fallback"""
        return """; === GENERIC END SEQUENCE ===
G92 E0 ; Reset extruder
G1 E-2 F1800 ; Retract filament
G91 ; Relative positioning
G1 Z10 F600 ; Raise Z
G90 ; Absolute positioning
G1 X10 Y10 F5000 ; Move to corner
M104 S0 ; Turn off nozzle
M140 S0 ; Turn off bed
M107 ; Turn off fan
M84 ; Disable motors
; === END COMPLETE ===
"""
    
    def generate(self, retraction_distance: float = None, 
                 cool_down_temp: int = 0, 
                 filament_type: str = None) -> List[str]:
        """
        Generate end sequence G-code
        
        Returns end G-code from JSON config (already complete)
        Parameters provided for backward compatibility but not used
        since modern configs have complete end G-code in JSON
        """
        # Just return the end G-code from JSON - it's already complete
        return self.end_gcode.split('\n')


# Backward compatibility aliases
# Old code can still import these names
BambuA1miniStartup = StartupGenerator
BambuA1miniEndSequence = EndSequenceGenerator
