#!/usr/bin/env python3
"""
Normal Layer Generator - Regular layer-by-layer printing (no corkscrew)
For testing multiple walls and standard printing
"""

print("=" * 80)
print("Normal Layer Generator - Standard Printing")
print("=" * 80)

from gcode_core import ConfigurationManager, HAS_INFILL_GENERATOR
from gcode_3mf import GCodeRendererBase, PackageBuilder, EnhancedPathProcessor
import json
import os
from typing import Dict, Any, Tuple, Optional

class NormalLayerGenerator(GCodeRendererBase):
    """Generate normal layers - standard layer-by-layer printing"""
    
    def __init__(self, config_manager: ConfigurationManager, 
                 path_processor: EnhancedPathProcessor,
                 vertical_curve_path: Optional[str] = None):
        super().__init__(config_manager, path_processor)
        self.vertical_curve_path = vertical_curve_path
    
    # Don't override anything - just use parent's generate_gcode()


def generate_3mf_from_html_json(html_json: Dict[str, Any]) -> Tuple[bool, Any]:
    """Main entry point - Normal printing mode"""
    try:
        print("=" * 80)
        print("GENERATING 3MF - NORMAL MODE (NO CORKSCREW)")
        print("=" * 80)
        
        # Get printer info from html_json
        # Priority 1: Full config already in request (from main.js)
        # Priority 2: Load from brand folder using printerId + brandId
        # Priority 3: Legacy fallback
        
        if 'printerConfig' in html_json and html_json['printerConfig']:
            # Full config already provided - USE THIS!
            full_config = html_json['printerConfig']
            print(f"✅ Using provided printer config: {full_config.get('name', 'Unknown')}")
        elif 'printerId' in html_json and 'brandId' in html_json:
            # Load config from brand folder
            printer_id = html_json['printerId']
            brand_id = html_json['brandId']
            
            # Build config path: {brand}/{printer_id}.json
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(script_dir, brand_id, f"{printer_id}.json")
            
            if not os.path.exists(config_file):
                return False, f"Config not found: {config_file}"
            
            print(f"✅ Loading config from: {config_file}")
            with open(config_file, 'r') as f:
                full_config = json.load(f)
        else:
            # Legacy fallback - look in root directory
            printer_type = html_json.get('printer', 'bambu')
            
            # Try brand folder first
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(script_dir, printer_type, f"{printer_type}_a1mini.json")
            
            if not os.path.exists(config_file):
                # Try root directory
                config_file = os.path.join(script_dir, f"{printer_type}_A1mini.json")
            
            if not os.path.exists(config_file):
                return False, f"Config not found. Please put config in {printer_type}/ folder or pass 'printerConfig' in request."
            
            print(f"⚠️ Using legacy config loading: {config_file}")
            with open(config_file, 'r') as f:
                full_config = json.load(f)

        if 'layerSettings' in html_json:
            full_config['layers'] = html_json['layerSettings']
        
        if 'shapeSettings' in html_json:
            if 'shapeSettings' not in full_config:
                full_config['shapeSettings'] = {}
            full_config['shapeSettings'].update(html_json['shapeSettings'])
        
        if 'files' in html_json:
            files = html_json['files']
            svg_content = None
            
            if 'layerFileMapping' in html_json and 'layerSettings' in html_json:
                layer_file_mapping = html_json['layerFileMapping']
                if len(html_json['layerSettings']) > 0:
                    current_layer_name = html_json['layerSettings'][0]['name']
                    if current_layer_name in layer_file_mapping:
                        layer_mapping = layer_file_mapping[current_layer_name]
                        primary_file = layer_mapping.get('primaryFile')
                        if primary_file == "return" and 'returnSvgContent' in files:
                            svg_content = files['returnSvgContent']
                        elif primary_file == "original" and 'originalSvgContent' in files:
                            svg_content = files['originalSvgContent']
            
            if not svg_content:
                if 'returnSvgContent' in files and files['returnSvgContent']:
                    svg_content = files['returnSvgContent']
                elif 'originalSvgContent' in files and files['originalSvgContent']:
                    svg_content = files['originalSvgContent']
            
            if svg_content:
                if 'shapeSettings' not in full_config:
                    full_config['shapeSettings'] = {}
                full_config['shapeSettings']['svgContent'] = svg_content
        
        if 'zigzagSettings' in html_json:
            html_zigzag = html_json['zigzagSettings']
            if 'zigzagSettings' not in full_config:
                full_config['zigzagSettings'] = {}
            
            full_config['zigzagSettings'].update({
                'wavelength': html_zigzag.get('wavelength', full_config['zigzagSettings'].get('wavelength', 5.0)),
                'amplitude': html_zigzag.get('amplitude', full_config['zigzagSettings'].get('amplitude', 1.5)),
                'amplitudeStart': html_zigzag.get('amplitudeStart', full_config['zigzagSettings'].get('amplitudeStart')),
                'amplitudeEnd': html_zigzag.get('amplitudeEnd', full_config['zigzagSettings'].get('amplitudeEnd')),
                'waveBias': html_zigzag.get('waveBias', full_config['zigzagSettings'].get('waveBias', 0.0)),
                'waveBiasStart': html_zigzag.get('waveBiasStart', full_config['zigzagSettings'].get('waveBiasStart', 0.0)),
                'waveBiasEnd': html_zigzag.get('waveBiasEnd', full_config['zigzagSettings'].get('waveBiasEnd', 0.0)),
                'pointsPerWavelength': html_zigzag.get('pointsPerWavelength', 
                                                       full_config['zigzagSettings'].get('pointsPerWavelength', 20)),
                'waveType': html_zigzag.get('waveType', 
                                            full_config['zigzagSettings'].get('waveType', 'sine')),
                'variableAmplitude': html_zigzag.get('variableAmplitude', 
                                                     full_config['zigzagSettings'].get('variableAmplitude', False)),
                'enabled': html_zigzag.get('enabled', full_config['zigzagSettings'].get('enabled', True)),
                'applyToMiddleWallsOnly': html_zigzag.get('applyToMiddleWallsOnly', 
                                                         full_config['zigzagSettings'].get('applyToMiddleWallsOnly', True))
            })
        
        for key in ['pathSettings', 'wallSettings', 'seamSelections', 
                   'infillSettings', 'filamentTypes']:
            if key in html_json:
                if key not in full_config:
                    full_config[key] = {}
                if isinstance(html_json[key], dict):
                    full_config[key].update(html_json[key])
                else:
                    full_config[key] = html_json[key]
        
        if 'printMode' in html_json:
            if 'metadataSettings' not in full_config:
                full_config['metadataSettings'] = {}
            full_config['metadataSettings']['printMode'] = html_json['printMode']
        
        # NORMAL MODE: Standard layer-by-layer printing
        print(f"🎯 Generating NORMAL layers - standard printing mode")
        
        # Generate with normal config
        config_manager = ConfigurationManager(full_config)
        path_processor = EnhancedPathProcessor(config_manager)
        shape_info = path_processor.get_shape_info()
        
        vertical_curve = html_json.get('verticalCurvePath', None)
        gcode_renderer = NormalLayerGenerator(config_manager, path_processor, vertical_curve)
        gcode_content = gcode_renderer.generate_gcode()
        
        # Count layers generated
        layer_count = gcode_content.count('LAYER_CHANGE')
        print(f"✓ Generated {layer_count} layers")
        
        # Check max Z
        import re
        z_values = re.findall(r'Z(\d+\.\d+)', gcode_content)
        if z_values:
            max_z = max(float(z) for z in z_values)
            print(f"✓ Max Z height: {max_z}mm")
        
        # Check wall loops in config
        if 'layers' in full_config and len(full_config['layers']) > 0:
            wall_loops = full_config['layers'][0].get('wallLoops', 'not specified')
            print(f"✓ Wall loops configured: {wall_loops}")
        
        package_builder = PackageBuilder(config_manager, gcode_renderer)
        package_bytes = package_builder.build_3mf_package(gcode_content, shape_info)
        
        import base64
        mf3_base64 = base64.b64encode(package_bytes).decode('utf-8')
        
        result = {
            'data': mf3_base64,
            'filename': f"normal_layers.3mf",
            'type': 'binary',
            'version': 'v1.0-normal',
            'gcode': gcode_content
        }
        
        print("=" * 80)
        print("SUCCESS - Normal layers generated")
        print("=" * 80)
        return True, result
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False, f"Error: {str(e)}"


if __name__ == "__main__":
    print("Normal Layer Generator - Standard layer-by-layer printing")
