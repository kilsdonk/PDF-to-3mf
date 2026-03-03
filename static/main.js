// =====================================================================================
// CONFIGURATION LOADING
// =====================================================================================
let h2dConfig = null;
let layers = [];
let filamentTypes = {};
let colors = {};
let clickSystemProfiles = {};

// =====================================================================================
// PRINTER SELECTION AND CONFIGURATION
// =====================================================================================
let printersList = null;
let currentPrinter = null;

// Load printers list
async function loadPrintersList() {
    try {
        console.log('=== DEBUG: loadPrintersList START ===');
        const response = await fetch('printers.json');
        printersList = await response.json();
        console.log('✅ Loaded printers list:', printersList);
        console.log('DEBUG: Number of brands:', printersList.brands.length);
        
        // Populate printer cards
        const cardsContainer = document.getElementById('printerCards');
        cardsContainer.innerHTML = '';
        
        printersList.brands.forEach(brand => {
            console.log('DEBUG: Processing brand:', brand.id, brand.name);
            brand.printers.forEach(printer => {
                console.log('DEBUG: Processing printer:', printer.id, printer.name);
                const card = document.createElement('div');
                card.className = `printer-card ${brand.id}`; // Add brand class for styling
                card.dataset.brandId = brand.id;
                card.dataset.printerId = printer.id;
                card.dataset.has3mf = printer.has3mf;
                
                console.log('DEBUG: Card dataset set:', card.dataset);
                
                // Determine image path based on brand folder structure
                // bambu/bambu_A1mini.png or qidi/qidi_max4.png
                const imagePath = `${brand.id}/${printer.id}.png`;
                
                // Support badge
                const supportBadge = printer.has3mf 
                    ? '<span class="support-badge support-3mf">3MF Supported</span>'
                    : '<span class="support-badge support-gcode">G-code Only</span>';
                
                card.innerHTML = `
                    <div class="checkmark">✓</div>
                    <img src="${imagePath}" alt="${printer.name}" onerror="if(this.src!=='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'320\\' height=\\'200\\'%3E%3Crect fill=\\'%23e0e0e0\\' width=\\'320\\' height=\\'200\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\' font-family=\\'Arial\\' font-size=\\'16\\' fill=\\'%23666\\'%3E${printer.name}%3C/text%3E%3C/svg%3E'){this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'320\\' height=\\'200\\'%3E%3Crect fill=\\'%23e0e0e0\\' width=\\'320\\' height=\\'200\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\' font-family=\\'Arial\\' font-size=\\'16\\' fill=\\'%23666\\'%3E${printer.name}%3C/text%3E%3C/svg%3E'}">
                    <h3>${printer.name}</h3>
                    <div class="printer-info">${brand.name}</div>
                    ${supportBadge}
                `;
                
                // Add click handler
                card.addEventListener('click', async function() {
                    console.log('===========================================');
                    console.log('PRINTER CARD CLICKED!!!');
                    console.log('===========================================');
                    console.log('=== DEBUG: CARD CLICKED ===');
                    console.log('DEBUG: Clicked card dataset:', this.dataset);
                    console.log('DEBUG: brandId =', this.dataset.brandId);
                    console.log('DEBUG: printerId =', this.dataset.printerId);
                    
                    // Remove selection from all cards
                    document.querySelectorAll('.printer-card').forEach(c => c.classList.remove('selected'));
                    
                    // Select this card
                    this.classList.add('selected');
                    
                    console.log('DEBUG: Calling loadPrinterConfig with:', this.dataset.brandId, this.dataset.printerId);
                    
                    try {
                        // Load printer config
                        await loadPrinterConfig(this.dataset.brandId, this.dataset.printerId);
                        
                        console.log('DEBUG: loadPrinterConfig returned');
                        
                        // Auto-refresh the GCode preview with new printer settings
                        console.log('DEBUG: Checking if SVG is loaded...');
                        console.log('DEBUG: originalSvgContent exists?', !!originalSvgContent);
                        console.log('DEBUG: shapelyUploadedFile exists?', !!shapelyUploadedFile);
                        
                        if (originalSvgContent || shapelyUploadedFile) {
                            console.log('DEBUG: SVG found! Reprocessing with new printer settings...');
                            
                            // Show notification to user
                            const notification = document.createElement('div');
                            notification.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #4CAF50; color: white; padding: 15px 20px; border-radius: 5px; z-index: 10000; box-shadow: 0 2px 10px rgba(0,0,0,0.3);';
                            notification.textContent = '🔄 Reprocessing SVG with new printer settings...';
                            document.body.appendChild(notification);
                            
                            // CRITICAL: Reprocess the original SVG with new printer's Shapely settings
                            // This ensures the returnSvgContent is regenerated with the new offsets
                            await processShapelySvg();
                            
                            notification.textContent = '✅ Preview updated with new printer!';
                            setTimeout(() => notification.remove(), 2000);
                            
                            console.log('DEBUG: SVG reprocessed and preview refreshed with new printer config');
                        } else {
                            console.log('DEBUG: No SVG loaded yet, skipping preview refresh');
                        }
                    } catch (error) {
                        console.error('ERROR in card click handler:', error);
                        console.error('Error stack:', error.stack);
                    }
                    
                    console.log('===========================================');
                    console.log('CARD CLICK HANDLER COMPLETE');
                    console.log('===========================================');
                });
                
                cardsContainer.appendChild(card);
            });
        });
        
        // Auto-select first printer
        if (printersList.brands && printersList.brands.length > 0) {
            const firstBrand = printersList.brands[0];
            if (firstBrand.printers && firstBrand.printers.length > 0) {
                const firstCard = cardsContainer.querySelector('.printer-card');
                if (firstCard) {
                    firstCard.click();
                }
            }
        }
    } catch (error) {
        console.error('Failed to load printers list:', error);
        const cardsContainer = document.getElementById('printerCards');
        cardsContainer.innerHTML = '<p style="color: red;">❌ Failed to load printers</p>';
    }
}

// Load specific printer configuration
async function loadPrinterConfig(brandId, printerId) {
    try {
        console.log('=== DEBUG: loadPrinterConfig START ===');
        console.log('DEBUG: brandId =', brandId);
        console.log('DEBUG: printerId =', printerId);
        
        const configPath = `${brandId}/${printerId}.json`;
        console.log(`DEBUG: configPath = ${configPath}`);
        console.log(`Loading printer config: ${configPath}`);
        
        // Add cache-busting to force fresh config load
        console.log('DEBUG: About to fetch...');
        const response = await fetch(configPath, { cache: 'no-store' });
        console.log('DEBUG: Fetch response received');
        console.log('DEBUG: Response status:', response.status);
        console.log('DEBUG: Response URL:', response.url);
        console.log('DEBUG: Response headers:', response.headers);
        
        console.log('DEBUG: About to parse JSON...');
        h2dConfig = await response.json();
        console.log('DEBUG: JSON parsed successfully');
        console.log('DEBUG: h2dConfig.name =', h2dConfig.name);
        console.log('DEBUG: h2dConfig.id =', h2dConfig.id);
        console.log('DEBUG: Full h2dConfig:', JSON.stringify(h2dConfig).substring(0, 200) + '...');
        
        // Store current printer info
        currentPrinter = {
            brandId: brandId,
            printerId: printerId,
            id: printerId,
            name: h2dConfig.name || printerId,
            has3mf: h2dConfig.has3mf !== undefined ? h2dConfig.has3mf : true,
            config: h2dConfig  // ← ADD THE FULL CONFIG!
        };
        
        console.log('DEBUG: currentPrinter =', currentPrinter);
        console.log('DEBUG: About to call applyConfigToUI...');
        
        applyConfigToUI();
        
        console.log('DEBUG: applyConfigToUI completed');
        
        // Update GCode viewer grid to match printer build volume
        if (h2dConfig.buildVolume) {
            console.log('DEBUG: Updating viewer grid to', h2dConfig.buildVolume.x, 'x', h2dConfig.buildVolume.y);
            updateViewerGrid(h2dConfig.buildVolume.x, h2dConfig.buildVolume.y);
        }
        
        console.log(`✅ Loaded ${currentPrinter.name} configuration`);
        console.log('=== DEBUG: loadPrinterConfig END ===');
        
    } catch (error) {
        console.error('=== DEBUG: ERROR in loadPrinterConfig ===');
        console.error('Failed to load printer configuration:', error);
        console.error('Error stack:', error.stack);
    }
}

// Direct config loading (backward compatibility)
async function loadPrinterConfigDirect(configFile) {
    try {
        // Add cache-busting to force fresh config load
        const response = await fetch(configFile, { cache: 'no-store' });
        h2dConfig = await response.json();
        
        currentPrinter = {
            brandId: 'bambu',
            printerId: 'bambu_a1mini',
            id: 'bambu_a1mini',
            name: h2dConfig.name || 'Bambu A1 Mini',
            has3mf: true,
            config: h2dConfig  // ← ADD THE FULL CONFIG!
        };
        
        applyConfigToUI();
        console.log('✅ Loaded configuration (legacy mode)');
    } catch (error) {
        console.error('Failed to load configuration:', error);
    }
}

// Apply loaded config to UI
function applyConfigToUI() {
    console.log("=== DEBUG: applyConfigToUI START ===");
    console.log("DEBUG: h2dConfig =", h2dConfig);
    console.log("DEBUG: h2dConfig.name =", h2dConfig ? h2dConfig.name : 'NULL');
    console.log("DEBUG: h2dConfig.id =", h2dConfig ? h2dConfig.id : 'NULL');
    console.log("Applying Config...", h2dConfig.name); // Debug
    // Load configuration
    layers = [...h2dConfig.layers];
    filamentTypes = {...h2dConfig.filamentTypes};
    clickSystemProfiles = h2dConfig.clickSystemProfiles || {};
    updateColors();
    
    // Load default settings
    const shapely = h2dConfig.shapelySettings || {}; // Safety check
    document.getElementById('shapelyOffsetInput').value = (shapely.offset !== undefined) ? shapely.offset : 0.0;
    document.getElementById('shapelyCornerInput').value = (shapely.corner !== undefined) ? shapely.corner : 0.0;
    document.getElementById('shapelyWhiteOffsetInput').value = (shapely.whiteOffset !== undefined) ? shapely.whiteOffset : 0.0;
    document.getElementById('shapelyResolutionInput').value = (shapely.resolution !== undefined) ? shapely.resolution : 20;
    
    // Load zigzag settings
    if (h2dConfig.zigzagSettings) {
        const zigzag = h2dConfig.zigzagSettings;
        document.getElementById('zigzagWavelengthInput').value = (zigzag.wavelength !== undefined) ? zigzag.wavelength : 5;
        document.getElementById('zigzagAmplitudeStartInput').value = (zigzag.amplitudeStart !== undefined) ? zigzag.amplitudeStart : 1.5;
        document.getElementById('zigzagAmplitudeEndInput').value = (zigzag.amplitudeEnd !== undefined) ? zigzag.amplitudeEnd : 1.5;
        document.getElementById('waveBiasStartInput').value = (zigzag.waveBiasStart !== undefined) ? zigzag.waveBiasStart : -0.2;
        document.getElementById('waveBiasEndInput').value = (zigzag.waveBiasEnd !== undefined) ? zigzag.waveBiasEnd : -0.2;
    }
    
    // Load wall offset settings
    if (h2dConfig.wallSettings) {
        const walls = h2dConfig.wallSettings;
        console.log("Wall Settings Found:", walls); // Debug: Check if 0.0 is here
        
        document.getElementById('normalWallOffsetInput').value = (walls.normalWallOffset !== undefined) ? walls.normalWallOffset : 4.0;
        document.getElementById('zigzagWallOffsetInput').value = (walls.zigzagWallOffset !== undefined) ? walls.zigzagWallOffset : 1.5;
    } else {
        console.warn("⚠️ wallSettings missing in JSON! Keeping HTML defaults (4.0/1.5)");
    }
    
    const infill = h2dConfig.infillSettings || {};
    document.getElementById('infillDensityInput').value = (infill.defaultDensity !== undefined) ? infill.defaultDensity : 20;
    document.getElementById('infillLineWidthInput').value = (infill.defaultLineWidth !== undefined) ? infill.defaultLineWidth : 0.42;
    document.getElementById('infillAngleInput').value = (infill.defaultBaseAngle !== undefined) ? infill.defaultBaseAngle : 45;
    
    // Initialize infill preview
    updateInfillPreview();
    
    renderLayers();
    validateAllLayers();
}

// Legacy function name for backward compatibility
async function loadA1miniConfig() {
    await loadPrintersList();
}

// Fallback configuration
function loadFallbackConfig() {
    filamentTypes = {
        0: { name: "PETG", color: "#FFFF66", textColor: "#000000", nozzle: 0, toolId: "T0", physicalExtruder: 0 }
    };
    
    layers = [
        { height: 2, filament: 0, nozzle: 0, tool: "T0", wallLoops: 4, name: "Floor", bottomShellLayers: 0, index: 0, enabled: true },
        { height: 2, filament: 0, nozzle: 0, tool: "T0", wallLoops: 1, name: "A1red", bottomShellLayers: 0, index: 1, enabled: true },
        { height: 2, filament: 0, nozzle: 0, tool: "T0", wallLoops: 3, name: "Return_floor", bottomShellLayers: 0, index: 2, enabled: true },
        { height: 2, filament: 0, nozzle: 0, tool: "T0", wallLoops: 2, name: "Return_top", bottomShellLayers: 0, index: 3, enabled: true },
        { height: 2, filament: 0, nozzle: 0, tool: "T0", wallLoops: 1, name: "one wall", bottomShellLayers: 0, index: 4, enabled: true },
        { height: 0.5, filament: 0, nozzle: 0, tool: "T0", wallLoops: 1, name: "click system", bottomShellLayers: 0, index: 5, enabled: false, clickSystemProfile: "none" }
    ];
    
    clickSystemProfiles = {
        profiles: {
            none: { name: "No Ribbing (Smooth)", speedOverride: null, flowOverride: null },
            light: { name: "Light Ribbing", speedOverride: 5000, flowOverride: 1.15 },
            medium: { name: "Medium Ribbing", speedOverride: 4000, flowOverride: 1.25 },
            strong: { name: "Strong Ribbing", speedOverride: 3500, flowOverride: 1.35 },
            heavy: { name: "Heavy Ribbing", speedOverride: 3000, flowOverride: 1.45 }
        }
    };
    
    updateColors();
    renderLayers();
    updateInfillPreview();
    validateAllLayers();
}

// Update colors object
function updateColors() {
    colors = {};
    Object.keys(filamentTypes).forEach(key => {
        colors[key] = filamentTypes[key].color;
    });
}

// =====================================================================================
// VALIDATION FUNCTIONS
// =====================================================================================

function validateLayer(layer) {
    const filament = filamentTypes[layer.filament];
    if (!filament) {
        return { valid: false, message: `Filament ${layer.filament} not found` };
    }
    
    if (layer.nozzle !== filament.nozzle || layer.tool !== filament.toolId) {
        return {
            valid: false,
            message: `Filament "${filament.name}" is on ${filament.toolId} (nozzle ${filament.nozzle}), but layer uses ${layer.tool} (nozzle ${layer.nozzle})`
        };
    }
    
    return { valid: true };
}

function validateAllLayers() {
    let hasErrors = false;
    let errorMessages = [];
    
    layers.forEach(layer => {
        if (!layer.enabled) return;
        
        const validation = validateLayer(layer);
        if (!validation.valid) {
            hasErrors = true;
            errorMessages.push(`Layer ${layer.index} (${layer.name}): ${validation.message}`);
        }
    });
    
    const warningDiv = document.getElementById('validationWarning');
    const messageDiv = document.getElementById('validationMessage');
    
    if (hasErrors) {
        warningDiv.style.display = 'block';
        messageDiv.innerHTML = errorMessages.join('<br>');
    } else {
        warningDiv.style.display = 'none';
    }
    
    return !hasErrors;
}

// =====================================================================================
// INFILL PREVIEW FUNCTION - FROM infill-good.html
// =====================================================================================
function updateInfillPreview() {
    const layersInput = document.getElementById('infillLayersInput');
    const angleInput = document.getElementById('infillAngleInput');
    
    if (!layersInput || !angleInput) return;
    
    const layersValue = layersInput.value;
    const baseAngle = parseInt(angleInput.value) || 45;
    const layersList = layersValue.split(',').map(n => parseInt(n.trim()));
    
    let previewHtml = '';
    layersList.forEach(layerNum => {
        const angle = layerNum % 2 === 1 ? baseAngle : (baseAngle + 90) % 180;
        previewHtml += `Layer ${layerNum}: ${angle}° lines<br>`;
    });
    
    const previewElement = document.getElementById('infillPreviewContent');
    if (previewElement) {
        previewElement.innerHTML = previewHtml;
    }
}

// =====================================================================================
// SHAPELY FUNCTIONALITY
// =====================================================================================
let shapelyUploadedFile = null;
let shapelyFaceFile = null;
let shapelyReturnFile = null;
let shapelyWhiteFile = null;
let originalSvgContent = null;
let returnSvgContent = null;

// File input change handler
document.getElementById('shapelyFileInput').addEventListener('change', function(e) {
    shapelyUploadedFile = e.target.files[0];
    if (shapelyUploadedFile) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const svgContent = e.target.result;
            
            // Store original SVG content
            originalSvgContent = svgContent;
            
            const container = document.getElementById('shapelyOriginalSvg');
            container.innerHTML = svgContent;
            
            const svg = container.querySelector('svg');
            if (svg) {
                svg.style.maxWidth = '100%';
                svg.style.maxHeight = '100%';
                svg.style.width = 'auto';
                svg.style.height = 'auto';
            }
            
            processShapelySvg();
        };
        reader.readAsText(shapelyUploadedFile);
    }
});

// Parameter change handlers
['shapelyOffsetInput', 'shapelyCornerInput', 'shapelyWhiteOffsetInput', 'shapelyResolutionInput'].forEach(id => {
    document.getElementById(id).addEventListener('change', function() {
        if (shapelyUploadedFile) {
            processShapelySvg();
        }
    });
});

// Process SVG through Shapely
async function processShapelySvg() {
    if (!shapelyUploadedFile) {
        return;
    }

    const faceContainer = document.getElementById('shapelyFaceSvg');
    const returnContainer = document.getElementById('shapelyReturnSvg');
    faceContainer.innerHTML = '<div style="color: #666;">Processing Face...</div>';
    returnContainer.innerHTML = '<div style="color: #666;">Processing Return...</div>';
    
    disableAllButtons();

    const formData = new FormData();
    formData.append('file', shapelyUploadedFile);
    formData.append('offset', document.getElementById('shapelyOffsetInput').value);
    formData.append('corner', document.getElementById('shapelyCornerInput').value);
    formData.append('white_offset', document.getElementById('shapelyWhiteOffsetInput').value);
    formData.append('resolution', document.getElementById('shapelyResolutionInput').value);
    formData.append('printer', 'bambu');

    try {
        const response = await fetch('/shapely_convert', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        
        if (result.success) {
            // Face preview
            if (result.face_svg_content) {
                faceContainer.innerHTML = result.face_svg_content;
                const faceSvg = faceContainer.querySelector('svg');
                if (faceSvg) {
                    faceSvg.style.maxWidth = '100%';
                    faceSvg.style.maxHeight = '100%';
                    faceSvg.style.width = 'auto';
                    faceSvg.style.height = 'auto';
                }
            }
            
            // Return preview and store for gcode generation
            if (result.return_svg_content) {
                returnSvgContent = result.return_svg_content;
                returnContainer.innerHTML = result.return_svg_content;
                const returnSvg = returnContainer.querySelector('svg');
                if (returnSvg) {
                    returnSvg.style.maxWidth = '100%';
                    returnSvg.style.maxHeight = '100%';
                    returnSvg.style.width = 'auto';
                    returnSvg.style.height = 'auto';
                }
                console.log('Return SVG content stored:', returnSvgContent.length, 'characters');
            }
            
            shapelyFaceFile = result.face_filename;
            shapelyReturnFile = result.return_filename;
            shapelyWhiteFile = result.white_filename;
            
            enableAllButtons();
            
            console.log('Shapely processing complete');
            
            // Auto-update GCode viewer
            setTimeout(generateGcodePreview, 500);
            
        } else {
            faceContainer.innerHTML = '<div style="color: #cc0000;">Error: ' + result.error + '</div>';
            returnContainer.innerHTML = '<div style="color: #cc0000;">Error: ' + result.error + '</div>';
            disableAllButtons();
        }
    } catch (error) {
        faceContainer.innerHTML = '<div style="color: #cc0000;">Processing failed: ' + error.message + '</div>';
        returnContainer.innerHTML = '<div style="color: #cc0000;">Processing failed: ' + error.message + '</div>';
        disableAllButtons();
    }
}

// =====================================================================================
// NEW: ZIGZAG FUNCTIONALITY
// =====================================================================================

function applyZigzagEffect() {
    if (!returnSvgContent) {
        alert('Please process an SVG file first');
        return;
    }
    
    console.log('Applying zigzag effect...');
    
    setTimeout(() => {
        const wavelength = parseFloat(document.getElementById('zigzagWavelengthInput').value);
        const amplitude = parseFloat(document.getElementById('zigzagAmplitudeStartInput').value);
        
        console.log('Applying zigzag:', wavelength, 'mm wavelength,', amplitude, 'mm amplitude');
        
        const zigzagSvg = applyZigzagToSVG(returnSvgContent, wavelength, amplitude);
        
        // Update preview
        const returnContainer = document.getElementById('shapelyReturnSvg');
        returnContainer.innerHTML = zigzagSvg;
        const returnSvg = returnContainer.querySelector('svg');
        if (returnSvg) {
            returnSvg.style.maxWidth = '100%';
            returnSvg.style.maxHeight = '100%';
            returnSvg.style.width = 'auto';
            returnSvg.style.height = 'auto';
        }
        
        // Update stored content
        returnSvgContent = zigzagSvg;
        
        console.log('Zigzag applied successfully');
    }, 100);
}

function applyZigzagToSVG(svgContent, wavelength, amplitude) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgContent, 'image/svg+xml');
    
    const PIXEL_TO_MM = 0.35277;
    const wavelengthPx = wavelength / PIXEL_TO_MM;
    const amplitudePx = amplitude / PIXEL_TO_MM;
    
    const paths = doc.querySelectorAll('path, rect, circle, ellipse, polygon');
    
    paths.forEach(path => {
        const coords = extractCoords(path);
        if (coords.length < 2) return;
        
        const zigzagCoords = createZigzag(coords, wavelengthPx, amplitudePx);
        const pathData = coordsToPath(zigzagCoords);
        
        if (path.tagName === 'path') {
            path.setAttribute('d', pathData);
        } else {
            const newPath = doc.createElementNS('http://www.w3.org/2000/svg', 'path');
            newPath.setAttribute('d', pathData);
            Array.from(path.attributes).forEach(attr => {
                if (!['x', 'y', 'width', 'height', 'cx', 'cy', 'r', 'rx', 'ry', 'points'].includes(attr.name)) {
                    newPath.setAttribute(attr.name, attr.value);
                }
            });
            path.parentNode.replaceChild(newPath, path);
        }
    });
    
    const serializer = new XMLSerializer();
    return serializer.serializeToString(doc);
}

function extractCoords(element) {
    const coords = [];
    
    if (element.tagName === 'path') {
        const d = element.getAttribute('d');
        const commands = d.match(/[MLHVCSQTAZ][^MLHVCSQTAZ]*/gi) || [];
        let x = 0, y = 0;
        
        commands.forEach(cmd => {
            const type = cmd[0].toUpperCase();
            const values = cmd.slice(1).match(/[-+]?\d*\.?\d+/g) || [];
            const nums = values.map(parseFloat);
            
            if (type === 'M' && nums.length >= 2) {
                x = nums[0];
                y = nums[1];
                coords.push([x, y]);
            } else if (type === 'L') {
                for (let i = 0; i < nums.length; i += 2) {
                    x = nums[i];
                    y = nums[i + 1];
                    coords.push([x, y]);
                }
            }
        });
    } else if (element.tagName === 'rect') {
        const x = parseFloat(element.getAttribute('x') || 0);
        const y = parseFloat(element.getAttribute('y') || 0);
        const w = parseFloat(element.getAttribute('width') || 0);
        const h = parseFloat(element.getAttribute('height') || 0);
        coords.push([x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]);
    } else if (element.tagName === 'circle') {
        const cx = parseFloat(element.getAttribute('cx') || 0);
        const cy = parseFloat(element.getAttribute('cy') || 0);
        const r = parseFloat(element.getAttribute('r') || 0);
        for (let i = 0; i <= 32; i++) {
            const angle = (i / 32) * 2 * Math.PI;
            coords.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
        }
    } else if (element.tagName === 'polygon') {
        const points = element.getAttribute('points');
        const nums = points.match(/[-+]?\d*\.?\d+/g) || [];
        for (let i = 0; i < nums.length; i += 2) {
            coords.push([parseFloat(nums[i]), parseFloat(nums[i + 1])]);
        }
    }
    
    return coords;
}

function createZigzag(coords, wavelength, amplitude) {
    if (coords.length < 2) return coords;
    
    // Calculate total length
    let totalLength = 0;
    const distances = [0];
    for (let i = 1; i < coords.length; i++) {
        const dx = coords[i][0] - coords[i-1][0];
        const dy = coords[i][1] - coords[i-1][1];
        const dist = Math.sqrt(dx*dx + dy*dy);
        totalLength += dist;
        distances.push(totalLength);
    }
    
    if (totalLength < wavelength) return coords;
    
    const zigzagCoords = [];
    const segmentLength = wavelength / 2;
    let currentDist = 0;
    let direction = 1;
    
    zigzagCoords.push([...coords[0]]);
    
    while (currentDist < totalLength) {
        currentDist += segmentLength;
        if (currentDist > totalLength) currentDist = totalLength;
        
        const pt = interpolateAtDistance(coords, distances, currentDist);
        const tangent = getTangent(coords, distances, currentDist);
        
        const perpX = -tangent[1];
        const perpY = tangent[0];
        
        zigzagCoords.push([
            pt[0] + perpX * amplitude * direction,
            pt[1] + perpY * amplitude * direction
        ]);
        
        direction *= -1;
    }
    
    return zigzagCoords;
}

function interpolateAtDistance(coords, distances, targetDist) {
    for (let i = 0; i < distances.length - 1; i++) {
        if (distances[i] <= targetDist && targetDist <= distances[i+1]) {
            const segLen = distances[i+1] - distances[i];
            if (segLen < 0.001) return [...coords[i]];
            const t = (targetDist - distances[i]) / segLen;
            return [
                coords[i][0] + t * (coords[i+1][0] - coords[i][0]),
                coords[i][1] + t * (coords[i+1][1] - coords[i][1])
            ];
        }
    }
    return [...coords[coords.length-1]];
}

function getTangent(coords, distances, targetDist) {
    const epsilon = 0.1;
    const pt1 = interpolateAtDistance(coords, distances, Math.max(0, targetDist - epsilon));
    const pt2 = interpolateAtDistance(coords, distances, Math.min(distances[distances.length-1], targetDist + epsilon));
    
    const dx = pt2[0] - pt1[0];
    const dy = pt2[1] - pt1[1];
    const len = Math.sqrt(dx*dx + dy*dy);
    
    return len < 0.001 ? [1, 0] : [dx/len, dy/len];
}

function coordsToPath(coords) {
    if (coords.length === 0) return '';
    let d = `M ${coords[0][0].toFixed(3)} ${coords[0][1].toFixed(3)}`;
    for (let i = 1; i < coords.length; i++) {
        d += ` L ${coords[i][0].toFixed(3)} ${coords[i][1].toFixed(3)}`;
    }
    return d;
}

// =====================================================================================
// INFILL SETTINGS - UPDATED FOR ENHANCED FUNCTIONALITY
// =====================================================================================
function getInfillSettings() {
    const layersInput = document.getElementById('infillLayersInput');
    const angleInput = document.getElementById('infillAngleInput');
    const enabledInput = document.getElementById('infillEnabledInput');
    const densityInput = document.getElementById('infillDensityInput');
    const lineWidthInput = document.getElementById('infillLineWidthInput');
    
    if (!layersInput || !angleInput || !enabledInput || !densityInput || !lineWidthInput) {
        return {
            enabled: false,
            density: 0.15,
            pattern: "lines",
            layers: [1],
            baseAngle: 45,
            line_width: 0.42
        };
    }
    
    const layersValue = layersInput.value;
    const layersList = layersValue.split(',').map(n => parseInt(n.trim()));
    const baseAngle = parseInt(angleInput.value) || 45;
    
    return {
        enabled: enabledInput.value === 'true',
        density: parseFloat(densityInput.value) / 100,
        pattern: "lines",
        layers: layersList,
        baseAngle: baseAngle,
        line_width: parseFloat(lineWidthInput.value)
    };
}

// =====================================================================================
// LAYER MAPPING
// =====================================================================================

// Map layers to coordinate files
		function mapLayersToFiles(enabledLayers) {
		    const layerFileMapping = {};
    
		    console.log("Mapping layers to coordinate files...");
    
		    enabledLayers.forEach(layer => {
		        const layerIndex = layer.index;
		        const layerName = layer.name;

		        if (layerName.toLowerCase().includes('inside') || layerIndex <= 1) {
		            // Layers 0-1 use "Inside white box" (return)
		            layerFileMapping[layerName] = {
		                primaryFile: 'return',
		                description: 'Inside layer - uses return coordinates (Inside white box)'
		            };
		            console.log(`   Layer ${layerIndex} (${layerName}) → RETURN coordinates (Inside white box)`);
		        } else if (layerName.toLowerCase().includes('return')) {
		            // NEW: Return layers use return file (with zigzag if applied)
		            layerFileMapping[layerName] = {
		                primaryFile: 'return',
		                description: 'Return layer - uses return coordinates (with zigzag if applied)'
		            };
		            console.log(`   Layer ${layerIndex} (${layerName}) → RETURN coordinates (with zigzag)`);
		        } else if (layerIndex >= 2 && layerIndex <= 5) {
		            // Other layers 2, 3, 4, 5 use original SVG
		            layerFileMapping[layerName] = {
		                primaryFile: 'original',
		                description: 'Return layer - uses original coordinates'
		            };
		            console.log(`   Layer ${layerIndex} (${layerName}) → ORIGINAL coordinates`);
		        }
		    });
    
		    return layerFileMapping;
		}

// Create mapped file structure
function createMappedFiles(layerFileMapping) {
    const mappedFiles = {};
    const usedFiles = new Set();
    
    Object.values(layerFileMapping).forEach(mapping => {
        usedFiles.add(mapping.primaryFile);
    });
    
    console.log("Files needed:", Array.from(usedFiles));
    
    if (usedFiles.has('face') && shapelyFaceFile) {
        mappedFiles.face = shapelyFaceFile;
    }
    if (usedFiles.has('return') && shapelyReturnFile) {
        mappedFiles.return = shapelyReturnFile;
    }
    if (usedFiles.has('white') && shapelyWhiteFile) {
        mappedFiles.white = shapelyWhiteFile;
    }
    if (usedFiles.has('original')) {
        mappedFiles.original = 'original';  // Flag to use original SVG
    }
    
    console.log("Mapped files:", mappedFiles);
    return mappedFiles;
}

// =====================================================================================
// PIPELINE FUNCTIONS - UPDATED FOR SHAPELY INTEGRATION
// =====================================================================================

// Download original SVG
function downloadOriginalSVG() {
    if (originalSvgContent) {
        const blob = new Blob([originalSvgContent], { type: 'image/svg+xml' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'original_input.svg';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
}

// Download Shapely outputs
function downloadShapelyFace() {
    if (shapelyFaceFile) {
        window.open('/shapely_download/' + encodeURIComponent(shapelyFaceFile));
    }
}

function downloadShapelyReturn() {
    if (returnSvgContent) {
        const blob = new Blob([returnSvgContent], { type: 'image/svg+xml' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'return.svg';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
}

// Download HTML output
function downloadHtmlOutput() {
    if (!validateAllLayers()) {
        alert('Cannot export: Configuration has validation errors. Please fix filament/tool mismatches.');
        return;
    }
    
    const enabledLayers = getEnabledLayers();
    const layerFileMapping = mapLayersToFiles(enabledLayers);
    const mappedFiles = createMappedFiles(layerFileMapping);
    
    const filesWithSvg = {
        originalSvgContent: originalSvgContent || '',
        returnSvgContent: returnSvgContent || '',
        ...mappedFiles
    };
    
    const htmlOutput = {
        printer: 'bambu',
        printerName: 'Bambu Lab A1 mini',
        buildVolume: { x: 180, y: 180, z: 180 },
        layerSettings: enabledLayers,
        shapelySettings: {
            offset: parseFloat(document.getElementById('shapelyOffsetInput').value),
            corner: parseFloat(document.getElementById('shapelyCornerInput').value),
            white_offset: parseFloat(document.getElementById('shapelyWhiteOffsetInput').value),
            resolution: parseInt(document.getElementById('shapelyResolutionInput').value)
        },
        files: filesWithSvg,
        layerFileMapping: layerFileMapping,
        infillSettings: getInfillSettings(),
        filamentTypes: filamentTypes,
        colors: colors,
        clickSystemProfiles: clickSystemProfiles,
        pathSettings: {
            curveResolution: parseInt(document.getElementById('shapelyResolutionInput').value),
            corner: parseFloat(document.getElementById('shapelyCornerInput').value)
        }
    };

    const blob = new Blob([JSON.stringify(htmlOutput, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'html_output_validated.json';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// =====================================================================================
// STAGE 3: DOWNLOAD GCODE FOR TESTING
// =====================================================================================
async function downloadGcode() {
    if (!validateAllLayers()) {
        alert('Cannot generate GCode: Configuration has validation errors. Please fix filament/tool mismatches.');
        return;
    }
    
    if (!returnSvgContent) {
        alert('Please upload and process SVG first');
        return;
    }
    
    try {
        const enabledLayers = getEnabledLayers();
        const layerFileMapping = mapLayersToFiles(enabledLayers);
        const mappedFiles = createMappedFiles(layerFileMapping);
        
        console.log("Generating GCode for testing...");
        
        const filesWithSvg = {
            originalSvgContent: originalSvgContent || '',
            returnSvgContent: returnSvgContent || '',
            ...mappedFiles
        };
        
        const htmlOutput = {
            printerId: currentPrinter?.id || 'bambu_A1mini',
            brandId: currentPrinter?.brandId || 'bambu',
            printerConfig: currentPrinter?.config || null,
            printer: currentPrinter?.brandId || 'bambu',
            printerName: currentPrinter?.name || 'Bambu Lab A1 Mini',
            buildVolume: currentPrinter?.config?.buildVolume || { x: 180, y: 180, z: 180 },
            layerSettings: enabledLayers,
            shapelySettings: {
                offset: parseFloat(document.getElementById('shapelyOffsetInput').value),
                corner: parseFloat(document.getElementById('shapelyCornerInput').value),
                white_offset: parseFloat(document.getElementById('shapelyWhiteOffsetInput').value),
                resolution: parseInt(document.getElementById('shapelyResolutionInput').value)
            },
            zigzagSettings: {
                wavelength: parseFloat(document.getElementById('zigzagWavelengthInput').value),
                amplitudeStart: parseFloat(document.getElementById('zigzagAmplitudeStartInput').value),
                amplitudeEnd: parseFloat(document.getElementById('zigzagAmplitudeEndInput').value),
                variableAmplitude: (document.getElementById('zigzagAmplitudeStartInput').value !== document.getElementById('zigzagAmplitudeEndInput').value),
                waveBiasStart: parseFloat(document.getElementById('waveBiasStartInput').value),
                waveBiasEnd: parseFloat(document.getElementById('waveBiasEndInput').value)
            },
            wallSettings: {
                normalWallOffset: parseFloat(document.getElementById('normalWallOffsetInput').value),
                zigzagWallOffset: parseFloat(document.getElementById('zigzagWallOffsetInput').value)
            },
            files: filesWithSvg,
            layerFileMapping: layerFileMapping,
            infillSettings: getInfillSettings(),
            filamentTypes: filamentTypes,
            colors: colors,
            clickSystemProfiles: clickSystemProfiles,
            pathSettings: {
                wallOffset: 0.6,
                curveResolution: parseInt(document.getElementById('shapelyResolutionInput').value),
                corner: parseFloat(document.getElementById('shapelyCornerInput').value)
            }
        };

        console.log("Requesting GCode from backend...");

        const response = await fetch('/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                processor: 'gcode_3mf',  // Same processor, we'll get gcode from result
                payload: htmlOutput
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success && result.result && result.result.gcode) {
                // Debug: Check what's in the gcode
                console.log('=== GCODE DEBUG ===');
                console.log('First 100 lines:', result.result.gcode.split('\n').slice(0, 100).join('\n'));
                console.log('Has T0?', result.result.gcode.includes('T0'));
                console.log('Has T1?', result.result.gcode.includes('T1'));
                console.log('Has T2?', result.result.gcode.includes('T2'));
                console.log('Has T3?', result.result.gcode.includes('T3'));
                console.log('Has T4?', result.result.gcode.includes('T4'));
                console.log('Has T5?', result.result.gcode.includes('T5'));
                console.log('Total lines:', result.result.gcode.split('\n').length);
                
                // Download as .gcode file
                const blob = new Blob([result.result.gcode], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'h2d_test.gcode';
                document.body.appendChild(a);
                a.click();
                URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                console.log('✅ GCode downloaded - Test in Simplify3D!');
            } else {
                alert('Failed to generate GCode');
            }
        } else {
            alert('Server error generating GCode');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to generate GCode: ' + error.message);
    }
}

// =====================================================================================
// STAGE 4: GENERATE AND DOWNLOAD 3MF
// =====================================================================================
// Generate and download 3MF
async function generateAndDownload3MF() {
    if (!validateAllLayers()) {
        alert('Cannot generate 3MF: Configuration has validation errors. Please fix filament/tool mismatches.');
        return;
    }
    
    console.log('=== DEBUG: generateAndDownload3MF START ===');
    console.log('DEBUG: currentPrinter =', currentPrinter);
    console.log('DEBUG: currentPrinter.config =', currentPrinter?.config);
    
    try {
        const enabledLayers = getEnabledLayers();
        const layerFileMapping = mapLayersToFiles(enabledLayers);
        const mappedFiles = createMappedFiles(layerFileMapping);
        
        console.log("Generating 3MF with validated configuration...");
        
        const filesWithSvg = {
            originalSvgContent: originalSvgContent || '',
            returnSvgContent: returnSvgContent || '',
            ...mappedFiles
        };
        
        const htmlOutput = {
            printerId: currentPrinter?.id || 'bambu_A1mini',
            brandId: currentPrinter?.brandId || 'bambu',
            printerConfig: currentPrinter?.config || null,
            printer: currentPrinter?.brandId || 'bambu',
            printerName: currentPrinter?.name || 'Bambu Lab A1 Mini',
            buildVolume: currentPrinter?.config?.buildVolume || { x: 180, y: 180, z: 180 },
            layerSettings: enabledLayers,
            shapelySettings: {
                offset: parseFloat(document.getElementById('shapelyOffsetInput').value),
                corner: parseFloat(document.getElementById('shapelyCornerInput').value),
                white_offset: parseFloat(document.getElementById('shapelyWhiteOffsetInput').value),
                resolution: parseInt(document.getElementById('shapelyResolutionInput').value)
            },
            zigzagSettings: {
                wavelength: parseFloat(document.getElementById('zigzagWavelengthInput').value),
                amplitudeStart: parseFloat(document.getElementById('zigzagAmplitudeStartInput').value),
                amplitudeEnd: parseFloat(document.getElementById('zigzagAmplitudeEndInput').value),
                variableAmplitude: (document.getElementById('zigzagAmplitudeStartInput').value !== document.getElementById('zigzagAmplitudeEndInput').value),
                waveBiasStart: parseFloat(document.getElementById('waveBiasStartInput').value),
                waveBiasEnd: parseFloat(document.getElementById('waveBiasEndInput').value)
            },
            wallSettings: {
                normalWallOffset: parseFloat(document.getElementById('normalWallOffsetInput').value),
                zigzagWallOffset: parseFloat(document.getElementById('zigzagWallOffsetInput').value)
            },
            files: filesWithSvg,
            layerFileMapping: layerFileMapping,
            infillSettings: getInfillSettings(),
            filamentTypes: filamentTypes,
            colors: colors,
            clickSystemProfiles: clickSystemProfiles,
            pathSettings: {
                wallOffset: 0.6,
                curveResolution: parseInt(document.getElementById('shapelyResolutionInput').value),
                corner: parseFloat(document.getElementById('shapelyCornerInput').value)
            }
        };
        
        console.log('DEBUG: htmlOutput.printerId =', htmlOutput.printerId);
        console.log('DEBUG: htmlOutput.printerConfig?.name =', htmlOutput.printerConfig?.name);
        console.log('DEBUG: htmlOutput.printerConfig?.wallSettings =', htmlOutput.printerConfig?.wallSettings);
        console.log('DEBUG: FULL printerConfig being sent:', JSON.stringify(htmlOutput.printerConfig, null, 2));
        console.log("DEBUG: Sending to /process for 3MF generation");

        console.log("Sending to /process for 3MF generation");

        const response = await fetch('/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                processor: 'gcode_3mf',
                payload: htmlOutput
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                // Decode and download 3MF file
                const binaryString = atob(result.result.data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                
                const blob = new Blob([bytes], { type: 'application/octet-stream' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = result.result.filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                // Update viewer with new gcode if available
                if (result.result.gcode) {
                    updateGcodeViewer(result.result.gcode);
                }
                
                console.log("3MF generation complete");
                alert('3MF file generated successfully! Ready for printing!');
            } else {
                alert('Error generating 3MF: ' + result.error);
            }
        } else {
            alert('Failed to generate 3MF');
        }
    } catch (error) {
        console.error('Error generating 3MF:', error);
        alert('Error: ' + error.message);
    }
}

// =====================================================================================
// LAYER MANAGEMENT WITH VALIDATION - UPDATED WITH SIMPLIFIED CLICK SYSTEM UI
// =====================================================================================

function getEnabledLayers() {
    return layers.filter(layer => layer.enabled === true);
}

function renderLayers() {
    let html = '';
    
    layers.forEach(layer => {
        const disabledClass = layer.enabled ? '' : ' disabled';
        const validation = validateLayer(layer);
        const mismatchClass = (!validation.valid && layer.enabled) ? ' mismatch-warning' : '';
        const isClickSystemCard = (layer.index === 5);
        const clickSystemClass = isClickSystemCard ? ' click-system-card' : '';
        
        html += `
        <div class="layer-card${disabledClass}${mismatchClass}${clickSystemClass}">
            <div class="layer-index">Index: ${layer.index}</div>
            ${!validation.valid && layer.enabled ? '<div class="mismatch-badge">⚠</div>' : ''}
            <div class="layer-title">${layer.name}</div>`;
        
        // SIMPLIFIED UI FOR CLICK SYSTEM (INDEX 5)
        if (isClickSystemCard) {
            html += `
            <div class="setting-group">
                <label>Status & Profile:</label>
                <div class="setting-input">
                    <select id="clickSystemControl-${layer.index}" onchange="updateClickSystemControl(${layer.index}, this.value)" style="font-weight: bold;">
                        <option value="disabled" ${!layer.enabled ? 'selected' : ''}>Disabled</option>
                        <option value="none" ${(layer.enabled && layer.clickSystemProfile === 'none') ? 'selected' : ''}>Smooth (No Ribbing)</option>
                        <option value="light" ${(layer.enabled && layer.clickSystemProfile === 'light') ? 'selected' : ''}>Light Ribbing</option>
                        <option value="medium" ${(layer.enabled && layer.clickSystemProfile === 'medium') ? 'selected' : ''}>Medium Ribbing</option>
                        <option value="strong" ${(layer.enabled && layer.clickSystemProfile === 'strong') ? 'selected' : ''}>Strong Ribbing</option>
                        <option value="heavy" ${(layer.enabled && layer.clickSystemProfile === 'heavy') ? 'selected' : ''}>Heavy Ribbing</option>
                    </select>
                </div>
            </div>`;
        } else {
            // NORMAL ENABLED DROPDOWN FOR OTHER LAYERS
            html += `
            <div class="setting-group">
                <label>Enabled:</label>
                <div class="setting-input">
                    <select id="enabled-${layer.index}" onchange="updateLayer(${layer.index}, 'enabled', this.value === 'true')">
                        <option value="true" ${layer.enabled ? 'selected' : ''}>Enabled</option>
                        <option value="false" ${!layer.enabled ? 'selected' : ''}>Disabled</option>
                    </select>
                </div>
            </div>`;
        }
        
        html += `
            <div class="setting-group">
                <label>Height:</label>
                <div class="setting-input ${isClickSystemCard ? 'fixed' : ''}">
                    <input type="number" 
                       id="height-${layer.index}" 
                       value="${layer.height}" 
                       min="0.1" 
                       max="50" 
                       step="0.1"
                       ${isClickSystemCard ? 'disabled' : ''}
                       onchange="updateLayer(${layer.index}, 'height', this.value)">
                    <span style="font-size: 12px;">mm</span>
                </div>
            </div>
            
            <div class="setting-group">
                <label>PC Color:</label>
                <div class="setting-input">
                    <select id="filament-${layer.index}" class="filament-select" style="background-color: ${colors[layer.filament] || '#FFFFFF'}; color: ${filamentTypes[layer.filament] && filamentTypes[layer.filament].textColor || '#000000'};" onchange="updateLayer(${layer.index}, 'filament', this.value)">`;
        
        Object.keys(filamentTypes).forEach(key => {
            const filament = filamentTypes[key];
            html += `<option value="${key}" ${layer.filament == key ? 'selected' : ''}>${filament.name} (${filament.toolId})</option>`;
        });
        
        html += `
                    </select>
                </div>
            </div>
            
            <div class="setting-group">
                <label>Tool (Auto):</label>
                <div class="setting-input ${isClickSystemCard ? 'auto-tool' : ''}" ${!isClickSystemCard ? 'style="padding: 10px; background: #e0e0e0; border-radius: 4px; text-align: center; font-weight: bold;"' : ''}>
                    ${!isClickSystemCard ? layer.tool : '<div>' + layer.tool + '</div>'}
                </div>
            </div>
            
            <div class="setting-group">
                <label>Walls:</label>
                <div class="setting-input ${isClickSystemCard ? 'fixed' : ''}">`;
        
        if (isClickSystemCard) {
            html += `<input type="text" value="1" disabled style="width: 100%;">`;
        } else {
            html += `
                    <select id="walls-${layer.index}" onchange="updateLayer(${layer.index}, 'wallLoops', this.value)">
                        <option value="1" ${layer.wallLoops === 1 ? 'selected' : ''}>1</option>
                        <option value="2" ${layer.wallLoops === 2 ? 'selected' : ''}>2</option>
                        <option value="3" ${layer.wallLoops === 3 ? 'selected' : ''}>3</option>
                        <option value="4" ${layer.wallLoops === 4 ? 'selected' : ''}>4</option>
                    </select>`;
        }
        
        html += `
                </div>
            </div>`;
        
        if (isClickSystemCard && layer.enabled) {
            html += `
            <div class="profile-description" id="profileDesc-${layer.index}" style="font-size: 10px;">
                ${getProfileDescription(layer.clickSystemProfile || 'none')}
            </div>`;
        }
        
        html += `</div>`;
    });
    
    document.getElementById('layerCards').innerHTML = html;
}

// NEW FUNCTION: Handle combined enable/profile control for click system
function updateClickSystemControl(index, value) {
    const layer = layers.find(l => l.index === index);
    if (!layer) return;
    
    if (value === 'disabled') {
        layer.enabled = false;
        layer.clickSystemProfile = 'none';
    } else {
        layer.enabled = true;
        layer.clickSystemProfile = value;
    }
    
    console.log(`Layer ${index}: ${value === 'disabled' ? 'Disabled' : 'Enabled with profile "' + value + '"'}`);
    
    renderLayers();
    validateAllLayers();
}

// UPDATED FUNCTION: Read profile description from JSON
function getProfileDescription(profile) {
    if (!clickSystemProfiles || !clickSystemProfiles.profiles) {
        return 'Profile information not loaded';
    }
    
    const profileData = clickSystemProfiles.profiles[profile];
    if (!profileData) {
        return 'Unknown profile';
    }
    
    // Get speed and flow percentages from JSON
    const speedPercent = profileData.speedPercent || (profileData.speedOverride ? Math.round((profileData.speedOverride / 10000) * 100) : 100);
    const flowPercent = profileData.flowPercent || (profileData.flowOverride ? Math.round(profileData.flowOverride * 100) : 100);
    
    return `${profileData.description} (${speedPercent}% speed, ${flowPercent}% flow)`;
}

function updateLayer(index, property, value) {
    const layer = layers.find(l => l.index === index);
    if (!layer) return;
    
    if (property === 'enabled') {
        layer.enabled = value;
        renderLayers();
        validateAllLayers();
        return;
    }
    
    if (property === 'height') {
        layer.height = parseFloat(value);
    } else if (property === 'filament') {
        const filamentId = parseInt(value);
        const filament = filamentTypes[filamentId];
        
        // Auto-correct tool and nozzle to match filament
        layer.filament = filamentId;
        layer.nozzle = filament.nozzle;
        layer.tool = filament.toolId;
        
        console.log(`Layer ${index}: Auto-corrected to ${filament.toolId} (nozzle ${filament.nozzle}) for filament "${filament.name}"`);
        
        renderLayers();
        validateAllLayers();
        return;
    } else if (property === 'wallLoops') {
        layer.wallLoops = parseInt(value);
    }
    
    validateAllLayers();
}

// =====================================================================================
// BUTTON MANAGEMENT
// =====================================================================================

function disableAllButtons() {
    const buttons = [
        'downloadOriginalBtn', 'downloadFaceBtn', 'downloadReturnBtn', 'downloadHtmlOutputBtn',
        'downloadGcodeBtn', 'download3mfBtn'
    ];
    
    buttons.forEach(buttonId => {
        const btn = document.getElementById(buttonId);
        if (btn) {
            btn.disabled = true;
        }
    });
}

function enableAllButtons() {
    const buttons = [
        'downloadOriginalBtn', 'downloadFaceBtn', 'downloadReturnBtn', 'downloadHtmlOutputBtn',
        'downloadGcodeBtn', 'download3mfBtn'
    ];
    
    buttons.forEach(buttonId => {
        const btn = document.getElementById(buttonId);
        if (btn) {
            btn.disabled = false;
        }
    });
    
    console.log('All pipeline buttons enabled');
}

// =====================================================================================
// GCODE VIEWER - THREE.JS WITH MULTI-COLOR SUPPORT
// =====================================================================================
let scene, camera, renderer, controls, gridHelper, axesHelper;
let gcodeObject = null;

function initGcodeViewer() {
    const container = document.getElementById('gcodeViewer');
    if (!container || typeof THREE === 'undefined') {
        console.log('THREE.js not loaded');
        return;
    }
    
    // 1. Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f5f5);
    
    // 2. Camera (Z-up)
    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 10000);
    camera.up.set(0, 0, 1);
    
    // 3. Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    
    // 4. Controls
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    
    // 5. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight.position.set(100, 100, 50);
    scene.add(dirLight);
    
    // 6. Axes
    axesHelper = new THREE.AxesHelper(50);
    scene.add(axesHelper);
    
    // 7. Initialize Grid & Camera Position
    if (h2dConfig && h2dConfig.buildVolume) {
        updateViewerGrid(h2dConfig.buildVolume.x, h2dConfig.buildVolume.y);
    } else {
        updateViewerGrid(180, 180); // Default fallback
    }
    
    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);
        if (controls) controls.update();
        if (renderer && scene && camera) renderer.render(scene, camera);
    }
    animate();
    
    console.log('✅ GCode viewer initialized');
}

// NEW: Centralized function to update Grid and Camera Target
function updateViewerGrid(width, depth) {
    if (!scene || !controls) return;
    
    // Remove old grid
    if (gridHelper) scene.remove(gridHelper);
    
    const centerX = width / 2;
    const centerY = depth / 2;
    const size = Math.max(width, depth) + 40;
    
    // Scale grid divisions based on build volume
    // Small printers (< 250mm): 20 divisions (10mm spacing for 200mm bed)
    // Large printers (>= 250mm): 40 divisions (10mm spacing for 400mm bed)
    const divisions = Math.max(20, Math.ceil(size / 10));
    
    // Determine grid colors based on background
    const bgColor = scene.background ? scene.background.getHexString() : 'f5f5f5';
    let color1 = 0x999999, color2 = 0xdddddd;
    if (bgColor === '000000' || bgColor === '222222') {
        color1 = 0x666666; color2 = 0x333333; // Dark mode grid
    }
    
    // Create new grid
    gridHelper = new THREE.GridHelper(size, divisions, color1, color2);
    gridHelper.rotateOnAxis(new THREE.Vector3(1, 0, 0), 90 * (Math.PI / 180));
    gridHelper.position.set(centerX, centerY, 0);
    scene.add(gridHelper);
    
    // FIX: Set rotation point (target) to the CENTER of the bed
    controls.target.set(centerX, centerY, 0);
    
    // Move camera to a nice viewing angle
    camera.position.set(centerX, -size * 0.8, size * 0.8);
    camera.lookAt(centerX, centerY, 0);
    
    controls.update();
    console.log(`📏 Grid updated: ${width}x${depth}mm, Center: (${centerX},${centerY}), Divisions: ${divisions}`);
}

// =====================================================================================
// PROFESSIONAL GCODE PARSER - CYLINDER MESHES (LIKE REAL FILAMENT)
// =====================================================================================
function parseGcodeCustom(gcodeText, toolColors) {
    const lines = gcodeText.split('\n');
    const group = new THREE.Group();
    
    let currentTool = 0;
    let currentX = 0, currentY = 0, currentZ = 0;
    let isAbsolute = true;
    let skipPurgeLine = false;
    
    // --- 1. Initialize Bounding Box Tracking ---
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    let hasPoints = false;
    // ------------------------------------------------
    
    // Initialize tracking variables
    const layerZHeights = new Set();
    let segmentCount = 0;
    const toolUsage = {};
    
    // Collect segment data by tool
    const toolSegmentData = {};
    if (Object.keys(toolColors).length === 0) {
        toolColors[0] = '#ff0000';
    }
    
    for (const tool in toolColors) {
        const toolNum = parseInt(tool);
        toolSegmentData[toolNum] = [];
        toolUsage[toolNum] = 0;
    }
    
    // Parse G-code
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        
        if (line.includes('noozle load line end') || line.includes('nozzle load line end')) {
            skipPurgeLine = false; 
            continue; 
        }
        
        if (!line || line.startsWith(';')) continue;
        
        if (line.startsWith('T')) {
            const match = line.match(/T(\d+)/);
            if (match) currentTool = parseInt(match[1]);
        }
        
        if (line.includes('G90')) isAbsolute = true;
        if (line.includes('G91')) isAbsolute = false;
        
        if (line.startsWith('G1') || line.startsWith('G0')) {
            const xMatch = line.match(/X([-\d.]+)/);
            const yMatch = line.match(/Y([-\d.]+)/);
            const zMatch = line.match(/Z([-\d.]+)/);
            
            let newX = currentX, newY = currentY, newZ = currentZ;
            if (xMatch) newX = isAbsolute ? parseFloat(xMatch[1]) : currentX + parseFloat(xMatch[1]);
            if (yMatch) newY = isAbsolute ? parseFloat(yMatch[1]) : currentY + parseFloat(yMatch[1]);
            if (zMatch) newZ = isAbsolute ? parseFloat(zMatch[1]) : currentZ + parseFloat(zMatch[1]);
            
            // --- 2. Update Bounding Box for every move ---
            if (newX !== 0 || newY !== 0) {
                minX = Math.min(minX, newX); maxX = Math.max(maxX, newX);
                minY = Math.min(minY, newY); maxY = Math.max(maxY, newY);
                minZ = Math.min(minZ, newZ); maxZ = Math.max(maxZ, newZ);
                hasPoints = true;
            }
            
            if (!skipPurgeLine && (newX !== currentX || newY !== currentY || newZ !== currentZ)) {
                const dx = newX - currentX;
                const dy = newY - currentY;
                const dz = newZ - currentZ;
                const length = Math.sqrt(dx*dx + dy*dy + dz*dz);
                
                if (length >= 0.1) { 
                    if (!toolSegmentData[currentTool]) {
                        toolSegmentData[currentTool] = [];
                        toolUsage[currentTool] = 0;
                    }
                    
                    toolSegmentData[currentTool].push({
                        x: (currentX + newX) / 2,
                        y: (currentY + newY) / 2,
                        z: (currentZ + newZ) / 2,
                        length: length,
                        dx: dx / length, dy: dy / length, dz: dz / length
                    });
                    
                    segmentCount++;
                    toolUsage[currentTool]++;
                    layerZHeights.add(Math.round(newZ * 100) / 100); // Track layer heights
                }
            }
            currentX = newX; currentY = newY; currentZ = newZ;
        }
    }
    
    // Create instanced meshes
    const baseGeometry = new THREE.CylinderGeometry(0.3, 0.3, 1, 5);
    const dummy = new THREE.Object3D();
    const upVector = new THREE.Vector3(0, 1, 0);
    
    for (const tool in toolSegmentData) {
        const toolNum = parseInt(tool);
        const segments = toolSegmentData[toolNum];
        if (segments.length === 0) continue;
        
        const material = new THREE.MeshPhongMaterial({
            color: new THREE.Color(toolColors[toolNum] || '#ff0000'),
            shininess: 30
        });
        
        const instancedMesh = new THREE.InstancedMesh(baseGeometry, material, segments.length);
        
        segments.forEach((seg, idx) => {
            dummy.position.set(seg.x, seg.y, seg.z);
            const direction = new THREE.Vector3(seg.dx, seg.dy, seg.dz);
            dummy.quaternion.setFromUnitVectors(upVector, direction);
            dummy.scale.set(1, seg.length, 1);
            dummy.updateMatrix();
            instancedMesh.setMatrixAt(idx, dummy.matrix);
        });
        
        instancedMesh.instanceMatrix.needsUpdate = true;
        group.add(instancedMesh);
    }
    
    // --- 3. Save the calculated box to the object ---
    if (hasPoints) {
        group.userData.bbox = new THREE.Box3(
            new THREE.Vector3(minX, minY, minZ),
            new THREE.Vector3(maxX, maxY, maxZ)
        );
        group.userData.center = new THREE.Vector3(
            (minX + maxX) / 2,
            (minY + maxY) / 2,
            (minZ + maxZ) / 2
        );
        console.log(`📏 Calculated BBox: X[${minX.toFixed(1)}, ${maxX.toFixed(1)}] Y[${minY.toFixed(1)}, ${maxY.toFixed(1)}]`);
    } else {
        // Fallback for empty G-code
        group.userData.bbox = new THREE.Box3(new THREE.Vector3(0,0,0), new THREE.Vector3(10,10,10));
        group.userData.center = new THREE.Vector3(0,0,0);
        maxZ = 10; // Set fallback maxZ
    }
    
    // Store layer information globally
    const allLayersArray = Array.from(layerZHeights).sort((a, b) => a - b);
    if (typeof allLayers !== 'undefined') allLayers = allLayersArray;
    if (typeof layerHeights !== 'undefined') layerHeights = allLayersArray;
    setupLayerSlider(maxZ || 0);
    
    console.log('═══════════════════════════════════════');
    console.log('✅ G-CODE PARSING COMPLETE (INSTANCED)');
    console.log('═══════════════════════════════════════');
    console.log(`📊 Statistics:`);
    console.log(`   • Total segments: ${segmentCount}`);
    console.log(`   • Rendering: Instanced Cylinders (FASTER)`);
    console.log(`   • Layers detected: ${allLayers.length}`);
    console.log(`   • Max Z height: ${maxZ.toFixed(2)}mm`);
    console.log(``);
    console.log(`🔧 Tool Usage:`);
    Object.keys(toolUsage).sort((a, b) => parseInt(a) - parseInt(b)).forEach(tool => {
        const count = toolUsage[tool];
        const colorHex = toolColors[parseInt(tool)] || '#999999';
        console.log(`   • Tool ${tool}: ${count} segments, color: ${colorHex}`);
    });
    console.log('═══════════════════════════════════════');

    return group;
}

function updateGcodeViewer(gcodeText) {
    if (!scene || !gcodeText) return;
    
    try {
        if (gcodeObject) scene.remove(gcodeObject);
        
        // Setup colors
        const enabledLayers = getEnabledLayers();
        const toolColors = {};
        enabledLayers.forEach((layer, index) => {
            let tool = layer.tool || index;
            if (typeof tool === 'string') tool = tool.replace(/^T/i, '');
            const filament = filamentTypes[layer.filament];
            toolColors[parseInt(tool)] = filament ? filament.color : '#999999';
        });
        
        // Parse & Add
        gcodeObject = parseGcodeCustom(gcodeText, toolColors);
        scene.add(gcodeObject);
        
        // === FIX: Use Manually Calculated Bounding Box ===
        let center, size, radius;
        
        if (gcodeObject.userData.bbox) {
            // Use the precise box we calculated during parsing
            const bbox = gcodeObject.userData.bbox;
            center = gcodeObject.userData.center;
            size = new THREE.Vector3();
            bbox.getSize(size);
            
            // Calculate radius of the bounding sphere manually
            radius = Math.max(size.x, size.y, size.z) / 2;
        } else {
            // Fallback (should rarely happen)
            const box = new THREE.Box3().setFromObject(gcodeObject);
            center = box.getCenter(new THREE.Vector3());
            const sphere = box.getBoundingSphere(new THREE.Sphere());
            radius = sphere.radius;
        }
        
        // 1. Center controls on the actual model
        controls.target.copy(center);
        
        // 2. Position camera nicely (AMF Loader style)
        // Ensure minimum radius to avoid being "inside" small objects
        const targetRadius = Math.max(radius, 40); 
        const fov = camera.fov * (Math.PI / 180);
        let dist = Math.abs(targetRadius / Math.sin(fov / 2));
        dist *= 1.5; // Zoom out a bit for padding
        
        // Position: Center X, Back Y, Up Z (Isometric-ish view)
        camera.position.set(
            center.x + dist * 0.5, 
            center.y - dist,       
            center.z + dist * 0.5
        );
        
        camera.lookAt(center);
        controls.update();
        
        updateColorLegend(toolColors);
        console.log(`✅ Camera centered at (${center.x.toFixed(0)},${center.y.toFixed(0)},${center.z.toFixed(0)}) distance: ${dist.toFixed(0)}`);
        
    } catch (error) {
        console.error('❌ Error rendering GCode:', error);
    }
}

function updateColorLegend(toolColors) {
    const legend = document.getElementById('colorLegend');
    if (!legend) return;
    
    const enabledLayers = getEnabledLayers();
    
    legend.innerHTML = '<span style="font-weight: bold; margin-right: 10px;">Layer Colors:</span>';
    
    enabledLayers.forEach((layer) => {
        // Get color from filament definition
        const filamentId = layer.filament;
        const filament = filamentTypes[filamentId];
        const color = filament ? filament.color : '#999999';
        
        const item = document.createElement('div');
        item.className = 'color-legend-item';
        item.innerHTML = `
            <div class="color-box" style="background-color: ${color};"></div>
            <span>T${layer.tool || 0}: ${layer.layerName || layer.name}</span>
        `;
        legend.appendChild(item);
    });
}

// =====================================================================================
// TEST FUNCTION - Verify colors work
// =====================================================================================
function testColors() {
    if (!scene) {
        console.error('Scene not initialized');
        return;
    }
    
    console.log('🧪 Testing color rendering...');
    
    // Create test cubes in different colors
    const testGroup = new THREE.Group();
    const colors = [0xff0000, 0x00ff00, 0x0000ff, 0xffff00];
    const colorNames = ['Red', 'Green', 'Blue', 'Yellow'];
    
    colors.forEach((color, i) => {
        const material = new THREE.MeshPhongMaterial({
            color: color,
            shininess: 30,
            specular: 0x222222
        });
        const geometry = new THREE.BoxGeometry(10, 10, 10);
        const cube = new THREE.Mesh(geometry, material);
        cube.position.set(i * 15, 0, 5);
        testGroup.add(cube);
        console.log(`✅ Created ${colorNames[i]} cube at x=${i * 15}`);
    });
    
    scene.add(testGroup);
    console.log('🎨 Test cubes added to scene - you should see 4 colored cubes!');
    console.log('💡 Call clearTestColors() to remove them');
    
    window.testGroup = testGroup;  // Save for cleanup
}

function clearTestColors() {
    if (window.testGroup) {
        scene.remove(window.testGroup);
        console.log('🧹 Test cubes removed');
    }
}

// Make functions globally accessible
window.testColors = testColors;
window.clearTestColors = clearTestColors;

// =====================================================================================
// VIEWER CONTROLS
// =====================================================================================
function changeBackground() {
    if (!scene) return;
    const color = document.getElementById('bgColorSelect').value;
    scene.background = new THREE.Color(color);
    
    // Update grid colors based on background
    if (gridHelper && gridHelper.parent === scene) {
        scene.remove(gridHelper);
        
        // Choose grid colors based on background
        let centerColor, gridColor;
        if (color === '#000000' || color === '#222222') {
            // Dark background - light grid
            centerColor = 0x666666;
            gridColor = 0x333333;
        } else {
            // Light background - dark grid
            centerColor = 0x999999;
            gridColor = 0xdddddd;
        }
        
        gridHelper = new THREE.GridHelper(200, 20, centerColor, gridColor);
        gridHelper.rotateOnAxis(new THREE.Vector3(1, 0, 0), 90 * (Math.PI / 180));
        gridHelper.position.set(90, 90, 0);  // Build plate center for A1 mini
        if (document.getElementById('gridToggle').value === 'on') {
            scene.add(gridHelper);
        }
    }
    
    console.log('Background changed to:', color);
}

function toggleGrid() {
    if (!scene || !gridHelper) return;
    const state = document.getElementById('gridToggle').value;
    
    if (state === 'on' && gridHelper.parent !== scene) {
        scene.add(gridHelper);
    } else if (state === 'off' && gridHelper.parent === scene) {
        scene.remove(gridHelper);
    }
    
    console.log('Grid:', state);
}

function toggleAxes() {
    if (!scene || !axesHelper) return;
    const state = document.getElementById('axesToggle').value;
    
    if (state === 'on' && axesHelper.parent !== scene) {
        scene.add(axesHelper);
    } else if (state === 'off' && axesHelper.parent === scene) {
        scene.remove(axesHelper);
    }
    
    console.log('Axes:', state);
}

// =====================================================================================
// LAYER SLIDER FUNCTIONS
// =====================================================================================
let allLayers = [];
let layerHeights = [];

function updateLayerDisplay(percentage) {
    if (!gcodeObject || allLayers.length === 0) return;
    
    const maxLayer = Math.floor((percentage / 100) * allLayers.length);
    document.getElementById('currentLayer').textContent = 
        percentage == 100 ? 'All' : `${maxLayer} / ${allLayers.length}`;
    
    // Show/hide layers based on slider
    gcodeObject.children.forEach((child, index) => {
        if (child.userData && child.userData.layer !== undefined) {
            child.visible = child.userData.layer <= maxLayer;
        }
    });
}

function resetLayerView() {
    document.getElementById('layerSlider').value = 100;
    updateLayerDisplay(100);
}

function setupLayerSlider(maxZ) {
    const sliderGroup = document.getElementById('layerSliderGroup');
    if (maxZ > 0) {
        sliderGroup.style.display = 'flex';
        // Layer slider is now available
        console.log(`✅ Layer slider enabled (max Z: ${maxZ}mm)`);
    } else {
        sliderGroup.style.display = 'none';
    }
}

async function refreshGcodeViewer() {
    console.log('🔄 Refreshing GCode preview...');
    await generateGcodePreview();
}

async function generateGcodePreview() {
    if (!returnSvgContent) {
        console.log('No SVG content - upload SVG first');
        return;
    }
    
    console.log('=== DEBUG: generateGcodePreview START ===');
    console.log('DEBUG: currentPrinter =', currentPrinter);
    console.log('DEBUG: currentPrinter.config =', currentPrinter?.config);
    
    try {
        const enabledLayers = getEnabledLayers();
        const layerFileMapping = mapLayersToFiles(enabledLayers);
        const mappedFiles = createMappedFiles(layerFileMapping);
        
        const htmlOutput = {
            printerId: currentPrinter?.id || 'bambu_A1mini',
            brandId: currentPrinter?.brandId || 'bambu',
            printerConfig: currentPrinter?.config || null,
            printer: currentPrinter?.brandId || 'bambu',
            printerName: currentPrinter?.name || 'Bambu Lab A1 Mini',
            buildVolume: currentPrinter?.config?.buildVolume || { x: 180, y: 180, z: 180 },
            layerSettings: enabledLayers,
            shapelySettings: {
                offset: parseFloat(document.getElementById('shapelyOffsetInput').value),
                corner: parseFloat(document.getElementById('shapelyCornerInput').value),
                white_offset: parseFloat(document.getElementById('shapelyWhiteOffsetInput').value),
                resolution: parseInt(document.getElementById('shapelyResolutionInput').value)
            },
            zigzagSettings: {
                wavelength: parseFloat(document.getElementById('zigzagWavelengthInput').value),
                amplitudeStart: parseFloat(document.getElementById('zigzagAmplitudeStartInput').value),
                amplitudeEnd: parseFloat(document.getElementById('zigzagAmplitudeEndInput').value),
                variableAmplitude: (document.getElementById('zigzagAmplitudeStartInput').value !== document.getElementById('zigzagAmplitudeEndInput').value),
                waveBiasStart: parseFloat(document.getElementById('waveBiasStartInput').value),
                waveBiasEnd: parseFloat(document.getElementById('waveBiasEndInput').value)
            },
            wallSettings: {
                normalWallOffset: parseFloat(document.getElementById('normalWallOffsetInput').value),
                zigzagWallOffset: parseFloat(document.getElementById('zigzagWallOffsetInput').value)
            },
            files: {
                originalSvgContent: originalSvgContent || '',
                returnSvgContent: returnSvgContent || '',
                ...mappedFiles
            },
            layerFileMapping: layerFileMapping,
            infillSettings: getInfillSettings(),
            filamentTypes: filamentTypes,
            colors: colors,
            clickSystemProfiles: clickSystemProfiles,
            pathSettings: {
                wallOffset: 0.6,
                curveResolution: parseInt(document.getElementById('shapelyResolutionInput').value),
                corner: parseFloat(document.getElementById('shapelyCornerInput').value)
            }
        };
        
        console.log('DEBUG: htmlOutput.printerId =', htmlOutput.printerId);
        console.log('DEBUG: htmlOutput.printerConfig?.name =', htmlOutput.printerConfig?.name);
        console.log('DEBUG: htmlOutput.printerConfig?.wallSettings =', htmlOutput.printerConfig?.wallSettings);
        console.log('DEBUG: FULL printerConfig being sent:', JSON.stringify(htmlOutput.printerConfig, null, 2));
        console.log('DEBUG: Sending to server...');

        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                processor: 'gcode_3mf',
                payload: htmlOutput
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success && result.result && result.result.gcode) {
                updateGcodeViewer(result.result.gcode);
                console.log('✅ Preview updated!');
            } else {
                console.log('❌ No gcode in response');
            }
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// =====================================================================================
// PRESET FUNCTIONS
// =====================================================================================
async function loadPreset(presetNumber) {
    const filename = 'Preset_' + presetNumber + '.json';
    console.log('Loading ' + filename);
    
    try {
        const response = await fetch(filename);
        h2dConfig = await response.json();
        
        // Load configuration
        layers = [...h2dConfig.layers];
        filamentTypes = {...h2dConfig.filamentTypes};
        clickSystemProfiles = h2dConfig.clickSystemProfiles || {};
        updateColors();
        
        // Load default settings
        const shapely = h2dConfig.shapelySettings;
        document.getElementById('shapelyOffsetInput').value = (shapely.offset !== undefined) ? shapely.offset : 0.0;
        document.getElementById('shapelyCornerInput').value = (shapely.corner !== undefined) ? shapely.corner : 0.0;
        document.getElementById('shapelyWhiteOffsetInput').value = (shapely.whiteOffset !== undefined) ? shapely.whiteOffset : 0.0;
        document.getElementById('shapelyResolutionInput').value = (shapely.resolution !== undefined) ? shapely.resolution : 20;
        
        // Load zigzag settings
        if (h2dConfig.zigzagSettings) {
            const zigzag = h2dConfig.zigzagSettings;
            document.getElementById('zigzagWavelengthInput').value = (zigzag.wavelength !== undefined) ? zigzag.wavelength : 5;
            document.getElementById('zigzagAmplitudeStartInput').value = (zigzag.amplitudeStart !== undefined) ? zigzag.amplitudeStart : 1.5;
            document.getElementById('zigzagAmplitudeEndInput').value = (zigzag.amplitudeEnd !== undefined) ? zigzag.amplitudeEnd : 1.5;
            document.getElementById('waveBiasStartInput').value = (zigzag.waveBiasStart !== undefined) ? zigzag.waveBiasStart : -0.2;
            document.getElementById('waveBiasEndInput').value = (zigzag.waveBiasEnd !== undefined) ? zigzag.waveBiasEnd : -0.2;
        }
        
        // Load wall offset settings
        if (h2dConfig.wallSettings) {
            const walls = h2dConfig.wallSettings;
            // FIX: Use undefined check so 0.0 works
            document.getElementById('normalWallOffsetInput').value = (walls.normalWallOffset !== undefined) ? walls.normalWallOffset : 4.0;
            document.getElementById('zigzagWallOffsetInput').value = (walls.zigzagWallOffset !== undefined) ? walls.zigzagWallOffset : 1.5;
        }
        
        const infill = h2dConfig.infillSettings;
        document.getElementById('infillDensityInput').value = (infill.defaultDensity !== undefined) ? infill.defaultDensity : 20;
        document.getElementById('infillLineWidthInput').value = (infill.defaultLineWidth !== undefined) ? infill.defaultLineWidth : 0.42;
        document.getElementById('infillAngleInput').value = (infill.defaultBaseAngle !== undefined) ? infill.defaultBaseAngle : 45;
        
        // Initialize infill preview
        updateInfillPreview();
        
        // Update Viewer Grid for preset
        if (h2dConfig.buildVolume) {
            updateViewerGrid(h2dConfig.buildVolume.x, h2dConfig.buildVolume.y);
        }
        
        renderLayers();
        validateAllLayers();
        console.log('Preset ' + presetNumber + ' loaded successfully');
        
    } catch (error) {
        console.error('Failed to load ' + filename + ':', error);
        alert('Failed to load Preset ' + presetNumber);
    }
}

// =====================================================================================
// PRESET CARDS GENERATION
// =====================================================================================
function generatePresetCards() {
    const presets = [
        { id: 1, name: 'Basic', desc: 'Simple text layout' },
        { id: 2, name: 'Detailed', desc: 'Multiple layers' },
        { id: 3, name: 'Minimal', desc: 'Clean & simple' },
        { id: 4, name: 'Complex', desc: 'Advanced settings' },
        { id: 5, name: 'Bold', desc: 'Thick walls' },
        { id: 6, name: 'Delicate', desc: 'Fine details' }
    ];
    
    const cardsContainer = document.getElementById('presetCards');
    if (!cardsContainer) return;
    
    cardsContainer.innerHTML = '';
    
    presets.forEach(preset => {
        const card = document.createElement('div');
        card.className = 'preset-card';
        card.dataset.presetId = preset.id;
        
        card.innerHTML = `
            <div class="checkmark">✓</div>
            <h3>${preset.name}</h3>
            <div class="preset-desc">${preset.desc}</div>
        `;
        
        card.addEventListener('click', function() {
            // Remove selection from all preset cards
            document.querySelectorAll('.preset-card').forEach(c => c.classList.remove('selected'));
            
            // Select this card
            this.classList.add('selected');
            
            // Load the preset
            loadPreset(preset.id);
        });
        
        cardsContainer.appendChild(card);
    });
}

// =====================================================================================
// INITIALIZATION
// =====================================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Load printers list and let user select
    loadPrintersList();
    
    // Generate preset cards
    generatePresetCards();
    
    // Initialize GCode viewer
    setTimeout(initGcodeViewer, 500);
    console.log('SVG to 3MF Pipeline v2.0 - Printer Selection Mode');
});
