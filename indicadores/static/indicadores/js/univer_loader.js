/**
 * Univer.js Loader - Utilidad para cargar y usar Univer en el wizard
 * Basado en la implementación de conjunto_datos_detalle.html
 */

class UniverLoader {
    constructor() {
        this.univerInstance = null;
        this.currentData = null;
    }

    /**
     * Verifica si Univer está disponible
     */
    checkUniver() {
        console.log('Checking Univer availability...');
        console.log('window.UniverPresets:', !!window.UniverPresets);
        console.log('window.UniverCore:', !!window.UniverCore);
        console.log('window.UniverPresetSheetsCore:', !!window.UniverPresetSheetsCore);
        console.log('window.UniverPresetSheetsCoreEnUS:', !!window.UniverPresetSheetsCoreEnUS);
        
        if (!window.UniverPresets || !window.UniverCore || 
            !window.UniverPresetSheetsCore || !window.UniverPresetSheetsCoreEnUS) {
            return false;
        }
        
        if (typeof window.UniverPresets.createUniver !== 'function' && 
            typeof window.UniverPresets.default !== 'function' &&
            typeof window.UniverPresets.Univer !== 'function') {
            console.log('No valid Univer creation method found');
            return false;
        }
        
        if (!window.UniverCore.LocaleType) {
            console.log('UniverCore.LocaleType not found');
            return false;
        }
        
        if (!window.UniverPresetSheetsCore.UniverSheetsCorePreset) {
            console.log('UniverPresetSheetsCore.UniverSheetsCorePreset not found');
            return false;
        }
        
        console.log('All Univer libraries are available');
        return true;
    }

    /**
     * Carga los scripts de Univer dinámicamente
     */
    async loadUniverScripts() {
        return new Promise((resolve, reject) => {
            if (this.checkUniver()) {
                resolve();
                return;
            }
            
            console.log('Loading Univer scripts dynamically...');
            
            const scriptUrls = [
                'https://unpkg.com/react@18.3.1/umd/react.production.min.js',
                'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js',
                'https://unpkg.com/rxjs/dist/bundles/rxjs.umd.min.js',
                'https://unpkg.com/@univerjs/presets/lib/umd/index.js',
                'https://unpkg.com/@univerjs/preset-sheets-core/lib/umd/index.js',
                'https://unpkg.com/@univerjs/preset-sheets-core/lib/umd/locales/en-US.js'
            ];
            
            let loadedCount = 0;
            
            const loadNextScript = () => {
                if (loadedCount >= scriptUrls.length) {
                    setTimeout(() => {
                        if (this.checkUniver()) {
                            resolve();
                        } else {
                            reject(new Error('Failed to load Univer scripts'));
                        }
                    }, 100);
                    return;
                }
                
                const script = document.createElement('script');
                script.src = scriptUrls[loadedCount];
                script.onload = () => {
                    console.log(`Loaded: ${scriptUrls[loadedCount]}`);
                    loadedCount++;
                    loadNextScript();
                };
                script.onerror = () => {
                    reject(new Error(`Failed to load: ${scriptUrls[loadedCount]}`));
                };
                document.head.appendChild(script);
            };
            
            loadNextScript();
        });
    }

    /**
     * Parsea CSV manejando comillas y comas
     */
    parseCSV(text) {
        const lines = text.split('\n').filter(line => line.trim());
        if (lines.length === 0) return { headers: [], data: [] };
        
        const parseLine = (line) => {
            const result = [];
            let current = '';
            let inQuotes = false;
            
            for (let i = 0; i < line.length; i++) {
                const char = line[i];
                const nextChar = line[i + 1];
                
                if (char === '"') {
                    if (inQuotes && nextChar === '"') {
                        current += '"';
                        i++;
                    } else {
                        inQuotes = !inQuotes;
                    }
                } else if (char === ',' && !inQuotes) {
                    result.push(current.trim());
                    current = '';
                } else {
                    current += char;
                }
            }
            result.push(current.trim());
            return result;
        };
        
        const headers = parseLine(lines[0]).filter(h => h && h.trim() !== '');
        const data = lines.slice(1).map(line => {
            const values = parseLine(line);
            const row = {};
            headers.forEach((header, index) => {
                if (header && header.trim() !== '') {
                    row[header] = values[index] || '';
                }
            });
            return row;
        });
        
        return { headers, data };
    }

    /**
     * Carga y renderiza datos CSV en Univer
     */
    async loadFromCSV(csvText, containerId = 'univer-container', options = {}) {
        try {
            // Cargar scripts si es necesario
            if (!this.checkUniver()) {
                console.log('Univer not available, loading scripts...');
                await this.loadUniverScripts();
            }
            
            // Parsear CSV
            const { headers, data } = this.parseCSV(csvText);
            
            if (data.length === 0) {
                throw new Error('No hay datos disponibles');
            }
            
            this.currentData = data;
            
            // Preparar celldata para Univer
            const celldata = [];
            
            // Headers (fila 0)
            headers.forEach((header, c) => {
                celldata.push({ r: 0, c, v: { v: String(header) } });
            });
            
            // Datos
            data.forEach((row, rIdx) => {
                headers.forEach((header, c) => {
                    const val = row[header] != null ? row[header] : '';
                    celldata.push({ r: rIdx + 1, c, v: { v: String(val) } });
                });
            });
            
            // Limpiar instancia anterior
            if (this.univerInstance) {
                try {
                    this.univerInstance.dispose();
                } catch (e) {
                    console.warn('Error disposing Univer instance:', e);
                }
            }
            
            const totalRows = data.length + 1;
            const totalCols = headers.length;
            const workbookTitle = options.title || 'Datos';
            const sheetName = options.sheetName || 'Hoja1';
            
            // Verificar contenedor
            const container = document.getElementById(containerId);
            if (!container) {
                throw new Error(`Container ${containerId} not found`);
            }
            
            // Limpiar contenedor completamente
            container.innerHTML = '';
            
            // Convertir celldata a formato correcto según documentación oficial
            const cellDataObj = {};
            celldata.forEach(cell => {
                if (!cellDataObj[cell.r]) cellDataObj[cell.r] = {};
                cellDataObj[cell.r][cell.c] = cell.v;
            });
            
            // Preparar workbook data según documentación oficial
            const workbookData = {
                id: `workbook-${Date.now()}`,
                name: workbookTitle,
                sheetOrder: ['sheet-01'],
                sheets: {
                    'sheet-01': {
                        id: 'sheet-01',
                        name: sheetName,
                        rowCount: totalRows,
                        columnCount: totalCols,
                        cellData: cellDataObj
                    }
                }
            };
            
            // COPIAR EXACTAMENTE de conjunto_datos_detalle.html líneas 990-1008
            const univer = new window.UniverCore.Univer();
            const injector = univer.__getInjector();
            
            // Core plugins
            const dependencies = [
                [window.UniverPresetSheetsCore.UniverSheetsCorePreset],
            ];
            
            dependencies.forEach((d) => injector.add(d));
            
            window.univerInstance = univer; // Store instance for later disposal
            this.univerInstance = univer;
            
            // Create the workbook via the Univer instance
            const workbook = univer.createUniverSheet(workbookData);
            
            if (!workbook) {
                throw new Error('Failed to create Univer workbook.');
            }
            
            console.log('Univer workbook created successfully.');
            
            console.log('Univer loaded successfully');
            
            return {
                success: true,
                rows: totalRows,
                columns: totalCols,
                headers: headers
            };
            
        } catch (error) {
            console.error('Error loading Univer:', error);
            throw error;
        }
    }

    /**
     * Carga datos desde una URL
     */
    async loadFromURL(url, containerId = 'univer-container', options = {}) {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const csvText = await response.text();
            return await this.loadFromCSV(csvText, containerId, options);
        } catch (error) {
            console.error('Error loading from URL:', error);
            throw error;
        }
    }

    /**
     * Exporta datos a CSV
     */
    exportToCSV() {
        if (!this.currentData) {
            throw new Error('No hay datos para exportar');
        }
        
        const headers = Object.keys(this.currentData[0]);
        const csvRows = [headers.join(',')];
        
        this.currentData.forEach(row => {
            const values = headers.map(header => {
                const val = row[header] || '';
                return `"${String(val).replace(/"/g, '""')}"`;
            });
            csvRows.push(values.join(','));
        });
        
        const csvContent = csvRows.join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'export.csv';
        link.click();
    }

    /**
     * Limpia la instancia
     */
    dispose() {
        if (this.univerInstance) {
            try {
                this.univerInstance.dispose();
                this.univerInstance = null;
            } catch (e) {
                console.warn('Error disposing Univer:', e);
            }
        }
        this.currentData = null;
    }
}

// Exportar para uso global
window.UniverLoader = UniverLoader;
