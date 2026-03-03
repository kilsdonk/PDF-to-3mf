#!/usr/bin/env python3
"""
Winding Direction Handler for Shapely Project
CREATE THIS FILE: winding_handler.py
"""

import xml.etree.ElementTree as ET
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
import re

class WindingDirectionHandler:
    """Handles consistent winding direction for 3D printing compatibility"""
    
    def __init__(self, target_format="bambu"):
        """Initialize with target format (bambu, fusion360, solidworks, standard)"""
        self.target_format = target_format.lower()
        
        # Define winding rules for different software
        self.winding_rules = {
            "bambu": {"outer": "ccw", "holes": "cw"},
            "fusion360": {"outer": "cw", "holes": "ccw"},
            "solidworks": {"outer": "ccw", "holes": "cw"},
            "standard": {"outer": "ccw", "holes": "cw"}
        }
        
        self.rules = self.winding_rules.get(target_format, self.winding_rules["standard"])
        print(f"🎯 Target format: {target_format.upper()}")
        print(f"📐 Winding rules: Outer={self.rules['outer'].upper()}, Holes={self.rules['holes'].upper()}")

    def analyze_winding(self, points):
        """Analyze winding direction using shoelace formula"""
        if len(points) < 3:
            return {"direction": "unknown", "area": 0, "is_valid": False}
        
        # Shoelace formula for signed area
        signed_area = 0
        for i in range(len(points)):
            j = (i + 1) % len(points)
            signed_area += (points[j][0] - points[i][0]) * (points[j][1] + points[i][1])
        
        signed_area = signed_area / 2
        
        # Determine direction (Positive = clockwise, Negative = counter-clockwise)
        is_clockwise = signed_area > 0
        direction = "cw" if is_clockwise else "ccw"
        
        return {
            "direction": direction,
            "signed_area": signed_area,
            "absolute_area": abs(signed_area),
            "is_clockwise": is_clockwise,
            "is_valid": len(points) >= 3
        }

    def fix_polygon_winding(self, polygon):
        """Fix polygon winding according to target format rules"""
        if not polygon or polygon.is_empty:
            return polygon
            
        print(f"🔍 Fixing polygon winding for {self.target_format}...")
        
        # Get exterior ring
        exterior_coords = list(polygon.exterior.coords)
        exterior_analysis = self.analyze_winding(exterior_coords[:-1])  # Remove duplicate last point
        
        print(f"   Exterior: {len(exterior_coords)} points, {exterior_analysis['direction'].upper()}")
        
        # Fix exterior winding
        should_be_cw = self.rules["outer"] == "cw"
        if exterior_analysis["is_clockwise"] != should_be_cw:
            print(f"   🔄 Reversing exterior ring")
            exterior_coords = list(reversed(exterior_coords))
        
        # Fix holes
        fixed_holes = []
        hole_count = 0
        
        if hasattr(polygon, 'interiors'):
            for interior in polygon.interiors:
                hole_count += 1
                hole_coords = list(interior.coords)
                hole_analysis = self.analyze_winding(hole_coords[:-1])
                
                print(f"   Hole {hole_count}: {len(hole_coords)} points, {hole_analysis['direction'].upper()}")
                
                # Fix hole winding
                hole_should_be_cw = self.rules["holes"] == "cw"
                if hole_analysis["is_clockwise"] != hole_should_be_cw:
                    print(f"   🔄 Reversing hole {hole_count}")
                    hole_coords = list(reversed(hole_coords))
                
                fixed_holes.append(hole_coords[:-1])  # Remove duplicate last point
        
        # Create new polygon with fixed winding
        try:
            if fixed_holes:
                fixed_polygon = Polygon(exterior_coords[:-1], fixed_holes)
            else:
                fixed_polygon = Polygon(exterior_coords[:-1])
            
            print(f"✅ Fixed polygon: valid={fixed_polygon.is_valid}, area={fixed_polygon.area:.2f}")
            return fixed_polygon
            
        except Exception as e:
            print(f"❌ Error creating fixed polygon: {e}")
            return polygon

# Integration function for your existing Shapely.py
def fix_winding_for_format(polygon, target_format="bambu"):
    """Simple integration function - call this from your Shapely.py"""
    handler = WindingDirectionHandler(target_format)
    return handler.fix_polygon_winding(polygon)