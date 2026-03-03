#!/usr/bin/env python3
"""
PROCESSING PIPELINE - Dependency & Stage Manager
Centralizes all processing dependencies and controls execution order
"""

import sys
from typing import List, Tuple, Dict, Any, Optional, Callable
import numpy as np

# ============================================================================
# DEPENDENCY MANAGEMENT - Graceful imports with fallbacks
# ============================================================================

class DependencyManager:
    """Manages optional dependencies with graceful fallbacks"""
    
    def __init__(self):
        self.available = {}
        self.modules = {}
        self._load_dependencies()
    
    def _load_dependencies(self):
        """Load all dependencies with graceful fallbacks"""
        
        # Shapely - Geometry operations (INSTALLED)
        try:
            from shapely.geometry import Polygon, Point, LineString, box, MultiPolygon
            from shapely.ops import unary_union
            self.modules['shapely'] = {
                'Polygon': Polygon,
                'Point': Point,
                'LineString': LineString,
                'box': box,
                'MultiPolygon': MultiPolygon,
                'unary_union': unary_union
            }
            self.available['shapely'] = True
            print("✓ Shapely loaded")
        except ImportError:
            self.available['shapely'] = False
            print("⚠ Shapely not available - limited geometry operations")
        
        # NumPy - Array operations (INSTALLED via numpy-stl)
        try:
            import numpy as np
            self.modules['numpy'] = np
            self.available['numpy'] = True
            print("✓ NumPy loaded")
        except ImportError:
            self.available['numpy'] = False
            print("❌ NumPy not available - CRITICAL")
            sys.exit(1)
        
        # numpy-stl - STL file operations (INSTALLED)
        try:
            from stl import mesh
            self.modules['numpy_stl'] = mesh
            self.available['numpy_stl'] = True
            print("✓ numpy-stl loaded")
        except ImportError:
            self.available['numpy_stl'] = False
            print("⚠ numpy-stl not available")
        
        # openpyxl - Excel operations (INSTALLED)
        try:
            import openpyxl
            self.modules['openpyxl'] = openpyxl
            self.available['openpyxl'] = True
            print("✓ openpyxl loaded")
        except ImportError:
            self.available['openpyxl'] = False
            print("⚠ openpyxl not available")
        
        # Pillow - Image handling (INSTALLED)
        try:
            from PIL import Image
            self.modules['PIL'] = Image
            self.available['PIL'] = True
            print("✓ Pillow loaded")
        except ImportError:
            self.available['PIL'] = False
            print("⚠ Pillow not available")
        
        # SciPy - Advanced processing
        try:
            from scipy import ndimage, interpolate
            self.modules['scipy'] = {
                'ndimage': ndimage,
                'interpolate': interpolate
            }
            self.available['scipy'] = True
            print("✓ SciPy loaded")
        except ImportError:
            self.available['scipy'] = False
            print("⚠ SciPy not available - smoothing/interpolation disabled")
        
        # OpenCV - Image processing
        try:
            import cv2
            self.modules['cv2'] = cv2
            self.available['cv2'] = True
            print("✓ OpenCV loaded")
        except ImportError:
            self.available['cv2'] = False
            print("⚠ OpenCV not available - image processing disabled")
    
    def get(self, module_name: str):
        """Get module if available, None otherwise"""
        return self.modules.get(module_name)
    
    def is_available(self, module_name: str) -> bool:
        """Check if module is available"""
        return self.available.get(module_name, False)
    
    def require(self, module_name: str):
        """Require module or raise error"""
        if not self.is_available(module_name):
            raise ImportError(f"Required module '{module_name}' is not available")
        return self.get(module_name)


# ============================================================================
# PROCESSING STAGES - Pipeline components
# ============================================================================

class ProcessingStage:
    """Base class for processing stages"""
    
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
    
    def process(self, data: Any, deps: DependencyManager, **kwargs) -> Any:
        """Process data - override in subclass"""
        raise NotImplementedError
    
    def __repr__(self):
        status = "✓" if self.enabled else "✗"
        return f"{status} {self.name}"


class QualityDetectionStage(ProcessingStage):
    """Stage 0: Detect curve quality and adjust pipeline settings"""
    
    def __init__(self, enabled: bool = True):
        super().__init__("Quality Detection", enabled)
    
    def process(self, polygons: List, deps: DependencyManager, **kwargs) -> Tuple[List, Dict]:
        """Analyze curve quality and return recommended settings"""
        if not self.enabled:
            return polygons, {}
        
        # Import quality detector
        try:
            from curve_quality_detector import CurveQualityDetector
            detector = CurveQualityDetector()
            
            # Analyze all polygons
            analyses = []
            for i, poly in enumerate(polygons):
                analysis = detector.analyze(poly)
                analyses.append(analysis)
                
                # Print summary
                print(f"   Polygon {i+1}: {analysis['quality_level']} "
                      f"(score: {analysis['quality_score']:.0f}/100, "
                      f"points: {analysis['num_points']})")
            
            # Calculate average recommendations
            avg_settings = self._aggregate_recommendations(analyses)
            
            print(f"\n   Recommended Pipeline Settings:")
            print(f"   → Smoothing: {avg_settings['enable_smoothing']} "
                  f"(sigma: {avg_settings['smoothing_sigma']:.2f})")
            print(f"   → Interpolation: {avg_settings['enable_interpolation']} "
                  f"(points: {avg_settings['interpolation_points']})")
            print(f"   → Simplification: {avg_settings['enable_simplification']} "
                  f"(tolerance: {avg_settings['simplification_tolerance']:.2f})")
            
            return polygons, avg_settings
            
        except ImportError:
            print("   ⚠ Quality detector not available - using default settings")
            return polygons, {}
    
    def _aggregate_recommendations(self, analyses: List[Dict]) -> Dict:
        """Aggregate recommendations from multiple polygons"""
        if not analyses:
            return {}
        
        # Take the worst case (lowest quality) to determine settings
        worst_analysis = min(analyses, key=lambda a: a['quality_score'])
        return worst_analysis['recommended_settings']


class SVGCleanupStage(ProcessingStage):
    """Stage 1: Clean and validate SVG geometry"""
    
    def __init__(self, enabled: bool = True):
        super().__init__("SVG Cleanup", enabled)
    
    def sanitize_geometry(self, polygon):
        """
        REPAIR STEP: Fixes common signmaker SVG mistakes.
        1. Fixes self-intersections (buffer(0)).
        2. Removes micro-segments that cause printer stutter (simplify).
        """
        if not polygon.is_valid:
            # This fixes paths that cross over themselves
            polygon = polygon.buffer(0) 
        
        # Signmaker SVGs often have thousands of points for a simple letter.
        # We simplify to 0.05mm to keep the shape but remove the 'noise'.
        return polygon.simplify(0.05, preserve_topology=True)
    
    def process(self, polygons: List, deps: DependencyManager, **kwargs) -> List:
        """Clean SVG polygons using Shapely"""
        if not self.enabled:
            return polygons
        
        cleaned = []
        for poly in polygons:
            # REPAIR: If a signmaker letter has crossing lines, fix it first
            if not poly.is_valid:
                poly = poly.buffer(0)
            
            # Ensure it is still a valid shape after the repair
            if poly.is_valid and not poly.is_empty:
                # Remove micro-segments (vibration points)
                # 0.02mm is recommended for 3D printed letters
                fixed = poly.simplify(0.02, preserve_topology=True)
                cleaned.append(fixed)
        
        return cleaned


class CoordinateExtractionStage(ProcessingStage):
    """Stage 2: Extract coordinates from Shapely to NumPy arrays"""
    
    def __init__(self, enabled: bool = True):
        super().__init__("Coordinate Extraction", enabled)
    
    def process(self, polygons: List, deps: DependencyManager, **kwargs) -> List[np.ndarray]:
        """Convert Shapely polygons to NumPy coordinate arrays"""
        if not self.enabled:
            return polygons
        
        np = deps.require('numpy')
        
        arrays = []
        for poly in polygons:
            coords = np.array(poly.exterior.coords)
            arrays.append(coords)
        
        return arrays


class SmoothingStage(ProcessingStage):
    """Stage 3: Smooth coordinates using SciPy"""
    
    def __init__(self, enabled: bool = True, method: str = 'gaussian'):
        super().__init__("Coordinate Smoothing", enabled)
        self.method = method
    
    def process(self, coord_arrays: List[np.ndarray], deps: DependencyManager, **kwargs) -> List[np.ndarray]:
        """Smooth coordinate arrays"""
        if not self.enabled or not deps.is_available('scipy'):
            return coord_arrays
        
        scipy = deps.get('scipy')
        np = deps.require('numpy')
        sigma = kwargs.get('smoothing_sigma', 1.0)
        
        smoothed = []
        for i, coords in enumerate(coord_arrays):
            try:
                if len(coords) < 3:
                    print(f"   ⚠ Polygon {i+1}: Too few points for smoothing")
                    smoothed.append(coords)
                    continue
                
                if self.method == 'gaussian':
                    # Check if coords is 2D
                    if coords.ndim != 2 or coords.shape[1] != 2:
                        print(f"   ⚠ Polygon {i+1}: Invalid coordinate array shape")
                        smoothed.append(coords)
                        continue
                    
                    x_smooth = scipy['ndimage'].gaussian_filter1d(coords[:, 0], sigma)
                    y_smooth = scipy['ndimage'].gaussian_filter1d(coords[:, 1], sigma)
                    smoothed_coords = np.column_stack([x_smooth, y_smooth])
                    smoothed.append(smoothed_coords)
                else:
                    smoothed.append(coords)
            except Exception as e:
                print(f"   ⚠ Polygon {i+1}: Smoothing error ({e}), keeping original")
                smoothed.append(coords)
        
        return smoothed


class InterpolationStage(ProcessingStage):
    """Stage 4: Interpolate points for smoother paths"""
    
    def __init__(self, enabled: bool = True):
        super().__init__("Path Interpolation", enabled)
    
    def process(self, coord_arrays: List[np.ndarray], deps: DependencyManager, **kwargs) -> List[np.ndarray]:
        """Interpolate additional points"""
        if not self.enabled or not deps.is_available('scipy'):
            return coord_arrays
        
        scipy = deps.get('scipy')
        np = deps.require('numpy')
        num_points = kwargs.get('interpolation_points', 100)
        
        interpolated = []
        for coords in coord_arrays:
            try:
                # Check if polygon is closed (first == last)
                is_closed = np.allclose(coords[0], coords[-1])
                if is_closed:
                    coords = coords[:-1]  # Remove duplicate closing point
                
                if len(coords) < 3:
                    interpolated.append(coords)
                    continue
                
                # Parametric interpolation
                t = np.linspace(0, 1, len(coords))
                t_new = np.linspace(0, 1, num_points)
                
                # Use linear interpolation for closed polygons to avoid self-intersection
                kind = 'linear' if is_closed else 'quadratic'
                
                x_interp = scipy['interpolate'].interp1d(t, coords[:, 0], kind=kind)(t_new)
                y_interp = scipy['interpolate'].interp1d(t, coords[:, 1], kind=kind)(t_new)
                
                interp_coords = np.column_stack([x_interp, y_interp])
                interpolated.append(interp_coords)
            except Exception as e:
                print(f"   ⚠ Interpolation failed, keeping original: {e}")
                interpolated.append(coords)
        
        return interpolated


class GeometryReconstructionStage(ProcessingStage):
    """Stage 5: Convert NumPy arrays back to Shapely polygons"""
    
    def __init__(self, enabled: bool = True):
        super().__init__("Geometry Reconstruction", enabled)
    
    def process(self, coord_arrays: List[np.ndarray], deps: DependencyManager, **kwargs) -> List:
        """Convert NumPy arrays back to Shapely polygons"""
        if not self.enabled:
            return coord_arrays
        
        shapely = deps.require('shapely')
        Polygon = shapely['Polygon']
        
        polygons = []
        for i, coords in enumerate(coord_arrays):
            try:
                # Make sure we have enough points
                if len(coords) < 3:
                    print(f"   ⚠ Polygon {i+1}: Too few points ({len(coords)}), skipping")
                    continue
                
                poly = Polygon(coords)
                if poly.is_valid and not poly.is_empty and poly.area > 0:
                    polygons.append(poly)
                else:
                    print(f"   ⚠ Polygon {i+1}: Invalid after reconstruction")
            except Exception as e:
                print(f"   ⚠ Polygon {i+1}: Reconstruction error ({e})")
        
        return polygons


class SimplificationStage(ProcessingStage):
    """Stage: Simplify geometry to remove micro-segments"""
    
    def __init__(self, enabled: bool = True):
        super().__init__("Geometry Simplification", enabled)
    
    def process(self, polygons: List, deps: DependencyManager, **kwargs) -> List:
        """Simplify polygons using Shapely's simplify"""
        if not self.enabled:
            return polygons
        
        tolerance = kwargs.get('simplification_tolerance', 0.1)
        
        simplified = []
        for i, poly in enumerate(polygons):
            try:
                simple_poly = poly.simplify(tolerance, preserve_topology=True)
                if simple_poly.is_valid and not simple_poly.is_empty and simple_poly.area > 0:
                    simplified.append(simple_poly)
                else:
                    # If simplification fails, keep original
                    print(f"   ⚠ Polygon {i+1}: Simplification produced invalid result, keeping original")
                    simplified.append(poly)
            except Exception as e:
                print(f"   ⚠ Polygon {i+1}: Simplification error ({e}), keeping original")
                simplified.append(poly)
        
        return simplified


# ============================================================================
# PIPELINE MANAGER
# ============================================================================

class ProcessingPipeline:
    """Manages the complete processing pipeline"""
    
    def repair_geometry(self, polygon):
            """
            REPAIR STEP: Fixes messy signmaker SVG mistakes.
            1. Fixes self-intersections (buffer(0)).
            2. Removes micro-segments (simplify).
            """
            if not self.deps.is_available('shapely'):
                return polygon
            
            # Fixes lines that cross over themselves (common in letter artwork)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            
            # Removes tiny points that cause printer vibration/stuttering
            # 0.02mm is a safe value for signmaking letters
            return polygon.simplify(0.02, preserve_topology=True)
    
    def __init__(self):
        self.deps = DependencyManager()
        self.stages = []
        self._setup_default_pipeline()
    
    def _setup_default_pipeline(self):
        """Setup default processing stages with quality detection"""
        # Check if SciPy is available to enable advanced stages
        scipy_available = self.deps.is_available('scipy')
        
        self.stages = [
            QualityDetectionStage(enabled=True),                  # NEW: Analyze quality first
            SimplificationStage(enabled=False),                   # NEW: Remove micro-segments (auto-enabled by detector)
            SVGCleanupStage(enabled=True),                        # Uses Shapely ✓
            CoordinateExtractionStage(enabled=True),              # Shapely → NumPy ✓
            SmoothingStage(enabled=False),                        # Uses SciPy (auto-enabled by detector)
            InterpolationStage(enabled=False),                    # Uses SciPy (auto-enabled by detector)
            GeometryReconstructionStage(enabled=True)             # NumPy → Shapely ✓
        ]
    
    def add_stage(self, stage: ProcessingStage, position: Optional[int] = None):
        """Add a processing stage at position (or end)"""
        if position is None:
            self.stages.append(stage)
        else:
            self.stages.insert(position, stage)
    
    def remove_stage(self, name: str):
        """Remove stage by name"""
        self.stages = [s for s in self.stages if s.name != name]
    
    def enable_stage(self, name: str):
        """Enable a stage"""
        for stage in self.stages:
            if stage.name == name:
                stage.enabled = True
    
    def disable_stage(self, name: str):
        """Disable a stage"""
        for stage in self.stages:
            if stage.name == name:
                stage.enabled = False
    
    def process(self, data: Any, **kwargs) -> Any:
        """Run data through the complete pipeline"""
        result = data
        quality_settings = {}
        
        print(f"\n{'='*60}")
        print("PROCESSING PIPELINE")
        print(f"{'='*60}")
        
        for i, stage in enumerate(self.stages, 1):
            if stage.enabled:
                print(f"{i}. {stage.name}...")
                
                # Quality detection returns both data and settings
                if isinstance(stage, QualityDetectionStage):
                    result, quality_settings = stage.process(result, self.deps, **kwargs)
                    
                    # Apply quality-based settings to later stages
                    if quality_settings:
                        # Enable/disable stages based on recommendations
                        for s in self.stages:
                            if s.name == 'Geometry Simplification':
                                s.enabled = quality_settings.get('enable_simplification', False)
                            elif s.name == 'Coordinate Smoothing':
                                s.enabled = quality_settings.get('enable_smoothing', False)
                            elif s.name == 'Path Interpolation':
                                s.enabled = quality_settings.get('enable_interpolation', False)
                        
                        # Merge quality settings with user kwargs (user settings override)
                        kwargs = {**quality_settings, **kwargs}
                else:
                    result = stage.process(result, self.deps, **kwargs)
                
                print(f"   ✓ Complete")
            else:
                print(f"{i}. {stage.name} [SKIPPED]")
        
        print(f"{'='*60}\n")
        return result
    
    def get_dependencies(self) -> Dict[str, bool]:
        """Get status of all dependencies"""
        return self.deps.available.copy()
    
    def __repr__(self):
        lines = ["Processing Pipeline:"]
        for stage in self.stages:
            lines.append(f"  {stage}")
        return "\n".join(lines)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_pipeline(**kwargs) -> ProcessingPipeline:
    """Create a processing pipeline with optional configuration"""
    pipeline = ProcessingPipeline()
    
    # Apply configuration
    if 'enable_smoothing' in kwargs:
        if kwargs['enable_smoothing']:
            pipeline.enable_stage('Coordinate Smoothing')
        else:
            pipeline.disable_stage('Coordinate Smoothing')
    
    if 'enable_interpolation' in kwargs:
        if kwargs['enable_interpolation']:
            pipeline.enable_stage('Path Interpolation')
        else:
            pipeline.disable_stage('Path Interpolation')
    
    return pipeline


# ============================================================================
# MAIN - For testing
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PROCESSING PIPELINE - Dependency Test")
    print("=" * 60)
    
    pipeline = create_pipeline()
    print(pipeline)
    
    print("\nDependency Status:")
    for dep, available in pipeline.get_dependencies().items():
        status = "✓ Available" if available else "✗ Not Available"
        print(f"  {dep}: {status}")
