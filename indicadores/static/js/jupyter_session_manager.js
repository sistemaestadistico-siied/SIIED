// JupyterLite Session Manager
class JupyterSessionManager {
    constructor() {
        this.jupyterOrigin = window.location.origin;
        this.jupyterPath = '/notebook/';
    }

    async clearJupyterStorage() {
        try {
            // Limpiar IndexedDB específico de JupyterLite
            await this.clearIndexedDB();
            
            // Limpiar localStorage relacionado
            this.clearLocalStorage();
            
            // Limpiar sessionStorage
            this.clearSessionStorage();
            
            console.log('✅ Almacenamiento de JupyterLite limpiado');
            return true;
        } catch (error) {
            console.error('Error limpiando almacenamiento:', error);
            return false;
        }
    }

    async clearIndexedDB() {
        // JupyterLite usa estas bases de datos
        const jupyterDBs = [
            'JupyterLite Storage',
            'jupyter-lite-drive',
            'jupyter-lite-settings',
            'jupyter-lite-kernelspecs',
            'jupyter-lite-schemas',
            'jupyterlite-storage',
            'jupyterlite-settings',
            'jupyterlite-contents',
            'jupyterlite-kernels'
        ];

        for (const dbName of jupyterDBs) {
            try {
                await this.deleteDatabase(dbName);
            } catch (error) {
                console.warn(`No se pudo eliminar DB ${dbName}:`, error);
            }
        }
    }

    deleteDatabase(dbName) {
        return new Promise((resolve, reject) => {
            const deleteRequest = indexedDB.deleteDatabase(dbName);
            
            deleteRequest.onerror = () => reject(deleteRequest.error);
            deleteRequest.onsuccess = () => resolve();
            deleteRequest.onblocked = () => {
                console.warn(`Eliminación de ${dbName} bloqueada`);
                resolve(); // Continúar anyway
            };
        });
    }

    clearLocalStorage() {
        const keys = Object.keys(localStorage);
        keys.forEach(key => {
            if (key.includes('jupyter') || key.includes('lab') || key.includes('notebook') || 
                key.includes('jupyterlite') || key.includes('pyodide')) {
                localStorage.removeItem(key);
            }
        });
    }

    clearSessionStorage() {
        const keys = Object.keys(sessionStorage);
        keys.forEach(key => {
            if (key.includes('jupyter') || key.includes('lab') || key.includes('notebook') ||
                key.includes('jupyterlite') || key.includes('pyodide')) {
                sessionStorage.removeItem(key);
            }
        });
    }

    async startFreshSession(iframeId = 'jupyter-iframe') {
        // 1. Limpiar almacenamiento
        await this.clearJupyterStorage();
        
        // 2. Esperar un poco para que se complete
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // 3. Inicializar JupyterLite
        this.initializeJupyter(iframeId);
    }

    initializeJupyter(iframeId = 'jupyter-iframe') {
        const frame = document.getElementById(iframeId);
        
        if (!frame) {
            console.error(`No se encontró iframe con ID: ${iframeId}`);
            return;
        }
        
        // Forzar recarga completa con timestamp para evitar cache
        const timestamp = new Date().getTime();
        const freshUrl = `https://jupyterlite.readthedocs.io/en/latest/_static/lab/index.html?t=${timestamp}&session=fresh&clear=true`;
        
        frame.src = freshUrl;
        
        frame.onload = () => {
            console.log('🚀 Nueva sesión de JupyterLite iniciada');
        };
    }

    async waitForJupyter(iframeId = 'jupyter-iframe') {
        return new Promise((resolve) => {
            const checkJupyter = () => {
                const frame = document.getElementById(iframeId);
                try {
                    if (frame && frame.contentWindow && frame.contentWindow.jupyterapp) {
                        resolve();
                    } else {
                        setTimeout(checkJupyter, 1000);
                    }
                } catch (error) {
                    setTimeout(checkJupyter, 1000);
                }
            };
            checkJupyter();
        });
    }
}

// Instancia global
window.jupyterSessionManager = new JupyterSessionManager();
