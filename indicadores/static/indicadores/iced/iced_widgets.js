/**
 * ICED Widgets — Motor genérico de widgets interactivos para campos JSON del FICED.
 *
 * Cómo funciona:
 *  - Busca elementos <div data-iced-widget="TIPO" data-config='{...}' data-target="nombre_campo">
 *  - Renderiza la UI según el tipo y sincroniza cambios al <input type="hidden" name="nombre_campo">
 *
 * Tipos soportados:
 *   - checkbox-tabla        : { codigo: {seleccion: bool, detalle: str} }
 *   - tabla-simple          : [ {col1: str, col2: str, ...} ]
 *   - tabla-compleja        : igual a tabla-simple pero columnas pueden ser bool/fecha
 *   - desplegables-multiples: [ "val1", "val2", ... ]  (hasta N selectores con lista de opciones)
 *   - matriz-satisfaccion   : { indicador: {nivel: str, urls: [str]} }
 *   - opciones-con-detalle  : { codigo: {seleccion: bool, cual: str} }
 */

(function() {
    'use strict';

    // ================================================================
    // Helpers
    // ================================================================

    function getHidden(targetName) {
        return document.querySelector(
            'input[type="hidden"][name="' + targetName + '"]' +
            ', input[type="hidden"][name$="-' + targetName + '"]'
        );
    }

    function writeJson(targetName, data) {
        const hidden = getHidden(targetName);
        if (!hidden) return;
        hidden.value = JSON.stringify(data);
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function readJson(targetName, fallback) {
        const hidden = getHidden(targetName);
        if (!hidden || !hidden.value) return fallback;
        try {
            return JSON.parse(hidden.value);
        } catch (e) {
            return fallback;
        }
    }

    function el(tag, attrs, children) {
        const e = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (k === 'class') e.className = v;
            else if (k === 'style') e.style.cssText = v;
            else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
            else if (v !== null && v !== undefined) e.setAttribute(k, v);
        });
        (children || []).forEach(c => {
            if (c === null || c === undefined) return;
            e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        });
        return e;
    }

    // Valida formato de URL; admite varias separadas por coma
    function esUrlValida(v) {
        return v.split(',').every(p => {
            p = p.trim();
            if (!p) return true;
            try {
                const u = new URL(p);
                return u.protocol === 'http:' || u.protocol === 'https:';
            } catch (e) {
                return false;
            }
        });
    }

    // Adjunta feedback visual de URL inválida a un input; devuelve el span de error
    function attachUrlValidation(input) {
        const err = el('span', {
            style: 'display: none; color: #dc2626; font-size: 0.75rem;'
        }, ['Ingrese una URL válida (ej: https://sitio.gov.co/pagina)']);
        input.addEventListener('input', () => {
            const v = input.value.trim();
            const ok = !v || esUrlValida(v);
            input.style.borderColor = ok ? '' : '#dc2626';
            err.style.display = ok ? 'none' : 'block';
        });
        return err;
    }

    // Evita que la rueda del mouse cambie el valor de inputs numéricos enfocados
    // (ej: porcentajes de P21). Al hacer wheel sobre un input[type=number] se
    // desenfoca, así el valor no cambia y la página sigue desplazándose.
    function preventNumberScroll() {
        const form = document.getElementById('iced-form');
        if (!form || form.dataset.wheelGuard === '1') return;
        form.dataset.wheelGuard = '1';
        form.addEventListener('wheel', function(e) {
            const t = e.target;
            if (t && t.tagName === 'INPUT' && t.type === 'number') {
                t.blur();
            }
        }, { passive: true });
    }

    // Evita que Enter envíe el formulario accidentalmente (avance/retroceso de paso).
    // Se permite Enter en textarea (salto de línea) y en botones/enlaces (activación).
    function preventEnterSubmit() {
        const form = document.getElementById('iced-form');
        if (!form || form.dataset.enterGuard === '1') return;
        form.dataset.enterGuard = '1';
        form.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter') return;
            const t = e.target;
            if (!t || !t.tagName) return;
            if (t.tagName === 'TEXTAREA' || t.tagName === 'BUTTON' || t.tagName === 'A') return;
            if (t.tagName === 'INPUT' && (t.type === 'submit' || t.type === 'button')) return;
            e.preventDefault();
        });
    }

    // ================================================================
    // Widget: checkbox-tabla
    // ================================================================
    // config: { 
    //   opciones: [{codigo, texto, columnas: [{name, label, tipo}]}], 
    //   exclusiva?: "codigo",
    //   con_detalle?: ["codigo1", "codigo2"] - solo estas opciones tienen input editable
    // }

    function renderCheckboxTabla(container, config, targetName) {
        const data = readJson(targetName, {});
        const opciones = config.opciones || [];
        const exclusiva = config.exclusiva;
        const conDetalle = config.con_detalle; // Array de códigos que tienen input
        const columnas = config.columnas || [{ name: 'detalle', label: 'Detalle', tipo: 'texto' }];

        container.innerHTML = '';
        const table = el('table', { class: 'iced-widget-table' });

        // Header
        const thead = el('thead', {}, [
            el('tr', {}, [
                el('th', { style: 'width: 45px;' }, ['']),
                el('th', {}, ['Opción']),
                ...columnas.map(c => el('th', {}, [c.label]))
            ])
        ]);
        table.appendChild(thead);

        // Body
        const tbody = el('tbody');
        opciones.forEach(opt => {
            const row = data[opt.codigo] || { seleccion: false };
            const tr = el('tr', { 'data-codigo': opt.codigo });

            // Checkbox
            const cb = el('input', {
                type: 'checkbox',
                class: 'iced-widget-checkbox',
                'data-codigo': opt.codigo,
            });
            cb.checked = !!row.seleccion;
            cb.addEventListener('change', () => {
                const current = readJson(targetName, {});
                if (!current[opt.codigo]) current[opt.codigo] = {};
                current[opt.codigo].seleccion = cb.checked;

                // Manejar exclusiva (ej: "ninguna" limpia las demás)
                if (exclusiva && cb.checked && opt.codigo === exclusiva) {
                    opciones.forEach(o => {
                        if (o.codigo !== exclusiva) {
                            if (current[o.codigo]) {
                                current[o.codigo].seleccion = false;
                                // Limpiar detalles de columnas
                                columnas.forEach(col => { delete current[o.codigo][col.name]; });
                            }
                        }
                    });
                } else if (exclusiva && cb.checked && opt.codigo !== exclusiva) {
                    if (current[exclusiva]) {
                        current[exclusiva].seleccion = false;
                        columnas.forEach(col => { delete current[exclusiva][col.name]; });
                    }
                }

                // Si se desmarca una opción, limpiar sus detalles
                if (!cb.checked) {
                    columnas.forEach(col => { delete current[opt.codigo][col.name]; });
                }

                writeJson(targetName, current);
                renderCheckboxTabla(container, config, targetName);
            });

            tr.appendChild(el('td', {}, [cb]));
            tr.appendChild(el('td', { class: 'iced-widget-opt-label' }, [opt.texto]));

            // Columnas de detalle: solo para opciones en con_detalle (o todas si no se especifica)
            // La opción exclusiva (ej: 'No se incluyen') nunca tiene campos de texto
            const tieneDetalle = conDetalle ? conDetalle.includes(opt.codigo) : true;
            if (opt.codigo === exclusiva || !tieneDetalle) {
                // Celda vacía o mensaje para opción exclusiva o sin detalle
                columnas.forEach(() => {
                    tr.appendChild(el('td', { 
                        style: 'background: #f3f4f6; color: #9ca3af; font-style: italic; font-size: 0.85rem;'
                    }, ['—']));
                });
            } else {
                // Columnas de detalle (solo editable si está seleccionada)
                columnas.forEach(col => {
                    const input = el('input', {
                        type: col.tipo === 'url' ? 'url' : 'text',
                        class: 'iced-widget-input',
                        placeholder: col.placeholder || '',
                        disabled: row.seleccion ? null : 'disabled',
                    });
                    input.value = row[col.name] || '';
                    input.addEventListener('input', () => {
                        const current = readJson(targetName, {});
                        if (!current[opt.codigo]) current[opt.codigo] = {};
                        current[opt.codigo][col.name] = input.value;
                        writeJson(targetName, current);
                    });
                    const tdChildren = [input];
                    if (col.tipo === 'url') tdChildren.push(attachUrlValidation(input));
                    tr.appendChild(el('td', {}, tdChildren));
                });
            }

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        // Envolver tabla en contenedor con scroll horizontal para tablas anchas
        const wrapper = el('div', { class: 'iced-widget-table-wrapper' });
        wrapper.appendChild(table);
        container.appendChild(wrapper);
    }

    // ================================================================
    // Widget: tabla-simple (filas dinámicas)
    // ================================================================
    // config: { columnas: [{name, label, tipo}], min_filas, max_filas }

    function renderTablaSimple(container, config, targetName) {
        const columnas = config.columnas || [];
        const minFilas = config.min_filas || 1;
        const maxFilas = config.max_filas || 20;
        // Reglas opcionales: config.control_bloqueo = {campo, valor, excluir[], campos[], valor_bloqueado}
        // o lista de reglas. Cuando fila[campo] === valor se deshabilitan los inputs
        // objetivo (todos menos excluir, o solo los listados en campos). Si la regla
        // define valor_bloqueado (p.ej. 'na'), se escribe en el JSON al bloquear y se
        // limpia al desbloquear.
        const controlBloqueo = config.control_bloqueo || null;
        const reglasBloqueo = controlBloqueo
            ? (Array.isArray(controlBloqueo) ? controlBloqueo : [controlBloqueo])
            : [];
        // Regla opcional: si config.autollenado = {campo_origen, campo_destino, mapa{}},
        // al cambiar campo_origen se rellena campo_destino con mapa[valor].
        const autollenado = config.autollenado || null;
        let filas = readJson(targetName, null) || [];
        if (!Array.isArray(filas)) filas = [];  // datos legacy: '{}' de borrador oculto
        while (filas.length < minFilas) {
            filas.push({});
        }

        function sync() {
            writeJson(targetName, filas);
        }

        function render() {
            container.innerHTML = '';
            const table = el('table', { class: 'iced-widget-table' });

            // Header
            const thead = el('thead', {}, [
                el('tr', {}, [
                    el('th', { style: 'width: 40px;' }, ['#']),
                    ...columnas.map(c => el('th', {}, [
                        c.label,
                        c.requerido ? el('span', { style: 'color:#dc2626; margin-left:2px;' }, ['*']) : ''
                    ])),
                    el('th', { style: 'width: 50px;' }, [''])
                ])
            ]);
            table.appendChild(thead);

            // Body
            const tbody = el('tbody');
            filas.forEach((fila, i) => {
                const tr = el('tr');
                tr.appendChild(el('td', { class: 'iced-widget-num' }, [String(i + 1)]));

                const inputsFila = {};
                columnas.forEach(col => {
                    let input;
                    if (col.tipo === 'booleano') {
                        input = el('select', { class: 'iced-widget-input' }, [
                            el('option', { value: '' }, ['—']),
                            el('option', { value: 'si' }, ['Sí']),
                            el('option', { value: 'no' }, ['No']),
                            // NA solo si la tabla lo habilita (config.opcion_na, p.ej. P23)
                            ...(config.opcion_na ? [el('option', { value: 'na' }, ['NA'])] : []),
                        ]);
                        input.value = fila[col.name] || '';
                    } else if (col.tipo === 'fecha') {
                        input = el('input', { type: 'date', class: 'iced-widget-input' });
                        input.value = fila[col.name] || '';
                    } else if (col.tipo === 'organismo') {
                        // Select con los organismos activos (window.ORGANISMOS).
                        // Conserva valores guardados que ya no estén en la lista.
                        const valorGuardado = fila[col.name] || '';
                        const listaOrg = (window.ORGANISMOS || []).slice();
                        if (valorGuardado && !listaOrg.includes(valorGuardado)) {
                            listaOrg.push(valorGuardado);
                        }
                        input = el('select', { class: 'iced-widget-input' }, [
                            el('option', { value: '' }, ['—']),
                            ...listaOrg.map(nombre =>
                                el('option', { value: nombre }, [nombre])
                            )
                        ]);
                        input.value = valorGuardado;
                    } else if (col.tipo === 'select' && Array.isArray(col.opciones)) {
                        input = el('select', { class: 'iced-widget-input' }, [
                            el('option', { value: '' }, ['—']),
                            ...col.opciones.map(o =>
                                el('option', { value: typeof o === 'string' ? o : o.valor }, [typeof o === 'string' ? o : o.texto])
                            )
                        ]);
                        input.value = fila[col.name] || '';
                    } else if (col.tipo === 'textarea') {
                        input = el('textarea', {
                            class: 'iced-widget-input',
                            placeholder: col.placeholder || '',
                            rows: col.rows || 3,
                            style: 'resize: vertical; min-height: 60px;'
                        });
                        input.value = fila[col.name] || '';
                    } else {
                        input = el('input', {
                            type: col.tipo === 'url' ? 'url' : 'text',
                            class: 'iced-widget-input',
                            placeholder: col.placeholder || '',
                        });
                        input.value = fila[col.name] || '';
                    }

                    input.addEventListener('input', () => {
                        filas[i][col.name] = input.value;
                        sync();
                    });
                    input.addEventListener('change', () => {
                        filas[i][col.name] = input.value;
                        sync();
                    });

                    inputsFila[col.name] = input;
                    const tdChildren = [input];
                    if (col.tipo === 'url') tdChildren.push(attachUrlValidation(input));
                    tr.appendChild(el('td', {}, tdChildren));
                });

                // control_bloqueo: para cada regla, si el campo de control vale `valor`,
                // deshabilitar los inputs objetivo. Si la regla define valor_bloqueado,
                // se escribe en esos campos al bloquear y se limpia al desbloquear.
                if (reglasBloqueo.length) {
                    const aplicarReglas = () => {
                        // 1) Recolectar campos bloqueados y el valor que les corresponde
                        const bloqueadoPor = {};
                        reglasBloqueo.forEach(regla => {
                            const ctrl = inputsFila[regla.campo];
                            if (!ctrl || ctrl.value !== regla.valor) return;
                            const excluir = regla.excluir || [];
                            columnas.forEach(c => {
                                if (excluir.indexOf(c.name) !== -1) return;
                                if (regla.campos && regla.campos.indexOf(c.name) === -1) return;
                                bloqueadoPor[c.name] = regla.valor_bloqueado;
                            });
                        });
                        // 2) Aplicar estado y valores
                        columnas.forEach(c => {
                            const inp = inputsFila[c.name];
                            if (!inp) return;
                            if (Object.prototype.hasOwnProperty.call(bloqueadoPor, c.name)) {
                                inp.disabled = true;
                                const vb = bloqueadoPor[c.name];
                                if (vb !== undefined && inp.value !== vb) {
                                    inp.value = vb;
                                    filas[i][c.name] = vb;
                                }
                            } else {
                                inp.disabled = false;
                                // Limpiar valor auto-seteado por reglas que ya no aplican
                                reglasBloqueo.forEach(regla => {
                                    const vb = regla.valor_bloqueado;
                                    if (vb === undefined) return;
                                    const esObjetivo = (regla.excluir || []).indexOf(c.name) === -1
                                        && (!regla.campos || regla.campos.indexOf(c.name) !== -1);
                                    if (esObjetivo && filas[i][c.name] === vb) {
                                        filas[i][c.name] = '';
                                        inp.value = '';
                                    }
                                });
                            }
                        });
                        sync();
                    };
                    reglasBloqueo.forEach(regla => {
                        const ctrl = inputsFila[regla.campo];
                        if (ctrl) ctrl.addEventListener('change', aplicarReglas);
                    });
                    aplicarReglas();
                }

                // autollenado: al cambiar campo_origen, rellenar campo_destino con mapa[valor]
                if (autollenado && inputsFila[autollenado.campo_origen] && inputsFila[autollenado.campo_destino]) {
                    const origen = inputsFila[autollenado.campo_origen];
                    const destino = inputsFila[autollenado.campo_destino];
                    origen.addEventListener('change', () => {
                        const val = autollenado.mapa[origen.value];
                        if (val !== undefined) {
                            destino.value = val;
                            filas[i][autollenado.campo_destino] = val;
                            sync();
                        }
                    });
                }

                // Botón eliminar
                const btnDel = el('button', {
                    type: 'button',
                    class: 'iced-widget-btn-del',
                    title: 'Eliminar fila',
                }, ['✕']);
                btnDel.addEventListener('click', () => {
                    if (filas.length <= minFilas) return;
                    filas.splice(i, 1);
                    sync();
                    render();
                });
                tr.appendChild(el('td', {}, [btnDel]));
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);

            // Envolver tabla en contenedor con scroll horizontal para tablas anchas
            const wrapper = el('div', { class: 'iced-widget-table-wrapper' });
            wrapper.appendChild(table);
            container.appendChild(wrapper);

            // Botón agregar
            if (filas.length < maxFilas) {
                const btnAdd = el('button', {
                    type: 'button',
                    class: 'iced-widget-btn-add',
                }, ['+ Agregar fila']);
                btnAdd.addEventListener('click', () => {
                    filas.push({});
                    sync();
                    render();
                });
                container.appendChild(btnAdd);
            }
        }

        sync();
        render();
    }

    // ================================================================
    // Widget: desplegables-multiples
    // ================================================================
    // config: { cantidad: N, opciones: ["..."], permitir_otro: bool }

    function renderDesplegablesMultiples(container, config, targetName) {
        const cantidad = config.cantidad || 3;
        const opciones = config.opciones || [];
        const permitirOtro = !!config.permitir_otro;

        let valores = readJson(targetName, null) || [];
        if (!Array.isArray(valores)) valores = [];  // datos legacy: '{}' de borrador oculto
        while (valores.length < cantidad) valores.push({ valor: '', otro: '' });

        function sync() {
            writeJson(targetName, valores);
        }

        function render() {
            container.innerHTML = '';
            for (let i = 0; i < cantidad; i++) {
                const v = valores[i] || { valor: '', otro: '' };
                const wrapper = el('div', { class: 'iced-widget-select-row' });
                wrapper.appendChild(el('label', { class: 'iced-widget-select-label' }, ['#' + (i + 1)]));

                // Opciones ya usadas en otros desplegables (evitar duplicados)
                const usados = new Set(valores.map((v, idx) => idx !== i && v.valor ? v.valor : '').filter(Boolean));
                const select = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: '' }, ['— Seleccione —']),
                    ...opciones.map(o => {
                        const yaUsado = usados.has(o) && v.valor !== o;
                        return el('option', { value: o, disabled: yaUsado ? 'disabled' : null, style: yaUsado ? 'color: #9ca3af;' : '' }, [o + (yaUsado ? ' (ya seleccionado)' : '')]);
                    }),
                    permitirOtro ? el('option', { value: '__otro__' }, ['Otro (especificar)']) : null,
                ]);
                select.value = v.valor || '';
                select.addEventListener('change', () => {
                    valores[i].valor = select.value;
                    sync();
                    render();
                });
                wrapper.appendChild(select);

                if (v.valor === '__otro__') {
                    const otro = el('input', {
                        type: 'text',
                        class: 'iced-widget-input',
                        placeholder: 'Especifique'
                    });
                    otro.value = v.otro || '';
                    otro.addEventListener('input', () => {
                        valores[i].otro = otro.value;
                        sync();
                    });
                    wrapper.appendChild(otro);
                }

                container.appendChild(wrapper);
            }
        }

        sync();
        render();
    }

    // ================================================================
    // Widget: matriz-satisfaccion
    // ================================================================
    // config: { indicadores: [...], niveles: [...], urls: N }

    function renderMatrizSatisfaccion(container, config, targetName) {
        const indicadores = config.indicadores || [];
        const niveles = config.niveles || [];
        const urlsCount = config.urls || 2;

        let data = readJson(targetName, null) || { matriz: {}, urls: [] };
        if (Array.isArray(data)) data = { matriz: {}, urls: [] };  // legacy '[]'
        if (!data.matriz) data.matriz = {};
        if (!data.urls) data.urls = [];
        while (data.urls.length < urlsCount) data.urls.push('');

        function sync() {
            writeJson(targetName, data);
        }

        container.innerHTML = '';

        // Contenedor scrollable para la tabla matriz
        const scrollWrapper = el('div', { 
            style: 'overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 1rem;'
        });

        // Tabla matriz
        const table = el('table', { 
            class: 'iced-widget-table',
            style: 'min-width: 800px;'  // Ancho mínimo para forzar scroll en pantallas pequeñas
        });
        const thead = el('thead', {}, [
            el('tr', {}, [
                el('th', { style: 'min-width: 300px;' }, ['Indicador']),
                ...niveles.map(n => el('th', { style: 'text-align: center; font-size: 0.75rem; min-width: 120px;' }, [n]))
            ])
        ]);
        table.appendChild(thead);

        const tbody = el('tbody');
        indicadores.forEach((ind, i) => {
            const tr = el('tr');
            tr.appendChild(el('td', { class: 'iced-widget-opt-label', style: 'min-width: 300px;' }, [ind]));
            niveles.forEach(nivel => {
                const td = el('td', { style: 'text-align: center; min-width: 120px;' });
                const radio = el('input', {
                    type: 'radio',
                    name: targetName + '_radio_' + i,
                    value: nivel,
                });
                radio.checked = (data.matriz[ind] === nivel);
                radio.addEventListener('change', () => {
                    data.matriz[ind] = nivel;
                    sync();
                });
                td.appendChild(radio);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        scrollWrapper.appendChild(table);
        container.appendChild(scrollWrapper);

        // URLs de evidencia
        const urlSection = el('div', { class: 'iced-widget-urls' });
        urlSection.appendChild(el('label', { class: 'iced-widget-section-label' }, ['URLs de evidencia']));
        for (let i = 0; i < urlsCount; i++) {
            const inp = el('input', {
                type: 'url',
                class: 'iced-widget-input',
                placeholder: 'URL ' + (i + 1),
            });
            inp.value = data.urls[i] || '';
            inp.addEventListener('input', () => {
                data.urls[i] = inp.value;
                sync();
            });
            urlSection.appendChild(inp);
            urlSection.appendChild(attachUrlValidation(inp));
        }
        container.appendChild(urlSection);

        sync();
    }

    // ================================================================
    // Widget: opciones-con-detalle
    // ================================================================
    // config: { opciones: [{codigo, texto, label_cual}], exclusiva?: "codigo" }

    function renderOpcionesDetalle(container, config, targetName) {
        const data = readJson(targetName, {});
        const opciones = config.opciones || [];
        const exclusiva = config.exclusiva;

        container.innerHTML = '';
        opciones.forEach(opt => {
            const row = data[opt.codigo] || { seleccion: false, cual: '' };
            const wrapper = el('div', { class: 'iced-widget-option-row' });

            const cb = el('input', { type: 'checkbox' });
            cb.checked = !!row.seleccion;
            const label = el('label', { class: 'iced-widget-opt-label-inline' }, [cb, ' ', opt.texto]);

            cb.addEventListener('change', () => {
                const current = readJson(targetName, {});
                if (!current[opt.codigo]) current[opt.codigo] = {};
                current[opt.codigo].seleccion = cb.checked;

                if (exclusiva && cb.checked && opt.codigo === exclusiva) {
                    opciones.forEach(o => {
                        if (o.codigo !== exclusiva && current[o.codigo]) current[o.codigo].seleccion = false;
                    });
                } else if (exclusiva && cb.checked && opt.codigo !== exclusiva) {
                    if (current[exclusiva]) current[exclusiva].seleccion = false;
                }

                writeJson(targetName, current);
                renderOpcionesDetalle(container, config, targetName);
            });

            wrapper.appendChild(label);

            if (row.seleccion && opt.label_cual) {
                const inp = el('input', {
                    type: 'text',
                    class: 'iced-widget-input',
                    placeholder: opt.label_cual,
                });
                inp.value = row.cual || '';
                inp.addEventListener('input', () => {
                    const current = readJson(targetName, {});
                    if (!current[opt.codigo]) current[opt.codigo] = {};
                    current[opt.codigo].cual = inp.value;
                    writeJson(targetName, current);
                });
                wrapper.appendChild(inp);
            }

            container.appendChild(wrapper);
        });
    }

    // ================================================================
    // Widget: rrhh-tabla (P19)
    // ================================================================
    // config: { min_filas, max_filas, categorias_nombrado, categorias_contratista, niveles_formacion, etapas }

    function renderRRHHTabla(container, config, targetName) {
        const minFilas = config.min_filas || 0;
        const maxFilas = config.max_filas || 100;
        const catNombrado = config.categorias_nombrado || [];
        const catContratista = config.categorias_contratista || [];
        const niveles = config.niveles_formacion || [];
        const etapas = config.etapas || [];

        let filas = readJson(targetName, null) || [];
        if (!Array.isArray(filas)) filas = [];  // datos legacy: '{}' de borrador oculto
        while (filas.length < minFilas) filas.push({});

        function newRow() {
            return {
                nombre_completo: '',
                correo: '',
                telefono: '',
                grupo: '',
                anios_experiencia: '',
                inicio_participacion: '',
                tipo_vinculacion: 'contratista',
                categoria_cargo: '',
                nivel_formacion: '',
                etapas_proceso: [],
                funciones_estadisticas: '',
            };
        }

        function sync() { writeJson(targetName, filas); }

        function render() {
            container.innerHTML = '';
            container.appendChild(el('div', {
                class: 'iced-widget-section-label',
                style: 'margin-bottom: 0.5rem;'
            }, ['PERSONAS VINCULADAS A PRODUCCIÓN ESTADÍSTICA (' + filas.length + ')']));

            if (filas.length === 0) {
                container.appendChild(el('p', {
                    style: 'color: var(--iced-muted, #64748b); font-size: 0.85rem; padding: 1rem; text-align: center;'
                }, ['No se ha registrado personal. Use el botón "Agregar persona" para iniciar.']));
            }

            filas.forEach((fila, i) => {
                const card = el('div', { class: 'iced-rrhh-card' });

                // Header con número y botón eliminar
                const header = el('div', { class: 'iced-rrhh-card-header' }, [
                    el('span', { class: 'iced-rrhh-num' }, ['Persona #' + (i + 1)]),
                ]);
                const btnDel = el('button', {
                    type: 'button',
                    class: 'iced-widget-btn-del',
                    title: 'Eliminar persona',
                }, ['✕']);
                btnDel.addEventListener('click', () => {
                    filas.splice(i, 1);
                    sync();
                    render();
                });
                header.appendChild(btnDel);
                card.appendChild(header);

                // Grid de campos
                const grid = el('div', { class: 'iced-rrhh-grid' });

                // Campo helper
                function addField(label, input, wide) {
                    const w = el('div', { class: wide ? 'iced-rrhh-field wide' : 'iced-rrhh-field' }, [
                        el('label', { class: 'iced-widget-select-label' }, [label]),
                        input,
                    ]);
                    grid.appendChild(w);
                }

                // Nombre completo
                const inpNombre = el('input', { type: 'text', class: 'iced-widget-input', placeholder: 'Nombre completo' });
                inpNombre.value = fila.nombre_completo || '';
                inpNombre.addEventListener('input', () => { filas[i].nombre_completo = inpNombre.value; sync(); });
                addField('Nombre completo *', inpNombre, true);

                // Correo
                const inpCorreo = el('input', { type: 'email', class: 'iced-widget-input', placeholder: 'correo@cali.gov.co' });
                inpCorreo.value = fila.correo || '';
                const errCorreo = el('span', { style: 'display: none; color: #dc2626; font-size: 0.75rem;' }, ['Correo inválido']);
                inpCorreo.addEventListener('input', () => {
                    filas[i].correo = inpCorreo.value;
                    const v = inpCorreo.value.trim();
                    const ok = !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
                    inpCorreo.style.borderColor = ok ? '' : '#dc2626';
                    errCorreo.style.display = ok ? 'none' : 'block';
                    sync();
                });
                addField('Correo electrónico', el('div', {}, [inpCorreo, errCorreo]));

                // Teléfono
                const inpTel = el('input', { type: 'tel', inputmode: 'tel', class: 'iced-widget-input', placeholder: '3001234567 o +573001234567', maxlength: '13', title: 'Máximo 10 dígitos, o 12 con prefijo +' });
                inpTel.value = fila.telefono || '';
                const errTel = el('span', {
                    style: 'display: none; color: #dc2626; font-size: 0.75rem;'
                }, ['Máximo 10 dígitos, o 12 con prefijo "+"']);
                inpTel.addEventListener('input', () => {
                    let limpio = inpTel.value.replace(/[^0-9+]/g, '').replace(/(?!^)\+/g, '');
                    const conMas = limpio.startsWith('+');
                    const digitos = limpio.replace(/\D/g, '');
                    const maxDig = conMas ? 12 : 10;
                    let excede = false;
                    if (digitos.length > maxDig) {
                        limpio = (conMas ? '+' : '') + digitos.slice(0, maxDig);
                        excede = true;
                    }
                    if (inpTel.value !== limpio) {
                        inpTel.value = limpio;
                    }
                    errTel.style.display = excede ? 'block' : 'none';
                    inpTel.style.borderColor = excede ? '#dc2626' : '';
                    filas[i].telefono = inpTel.value;
                    sync();
                });
                addField('Teléfono', el('div', {}, [inpTel, errTel]));

                // Grupo
                const inpGrupo = el('input', { type: 'text', class: 'iced-widget-input', placeholder: 'Grupo / área' });
                inpGrupo.value = fila.grupo || '';
                inpGrupo.addEventListener('input', () => { filas[i].grupo = inpGrupo.value; sync(); });
                addField('Grupo al que pertenece', inpGrupo);

                // Años experiencia
                const inpAnios = el('input', { type: 'number', min: '0', max: '80', class: 'iced-widget-input' });
                inpAnios.value = fila.anios_experiencia || '';
                inpAnios.addEventListener('input', () => { filas[i].anios_experiencia = inpAnios.value; sync(); });
                addField('Años de experiencia profesional', inpAnios);

                // Inicio de participación (mm/aaaa)
                const inpInicio = el('input', { type: 'text', inputmode: 'numeric', class: 'iced-widget-input', placeholder: 'MM/AAAA', maxlength: '7' });
                inpInicio.value = fila.inicio_participacion || '';
                const errInicio = el('span', {
                    style: 'display: none; color: #dc2626; font-size: 0.75rem;'
                }, ['Formato MM/AAAA con mes entre 01 y 12 (ej: 03/2024)']);
                inpInicio.addEventListener('input', () => {
                    // Solo dígitos, auto-insertar '/'
                    let v = inpInicio.value.replace(/\D/g, '').slice(0, 6);
                    if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
                    if (inpInicio.value !== v) inpInicio.value = v;
                    // Validar mes 01-12 solo cuando está completo
                    const mes = parseInt(v.slice(0, 2), 10);
                    const invalido = v.length === 7 && !(mes >= 1 && mes <= 12);
                    errInicio.style.display = invalido ? 'block' : 'none';
                    inpInicio.style.borderColor = invalido ? '#dc2626' : '';
                    filas[i].inicio_participacion = inpInicio.value;
                    sync();
                });
                addField('Inicio de participación en el proceso de producción estadística en el organismo (mm/aaaa)', el('div', {}, [inpInicio, errInicio]));

                // Tipo vinculación
                const selTipo = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: 'nombrado' }, ['Nombrado']),
                    el('option', { value: 'contratista' }, ['Contratista']),
                ]);
                selTipo.value = fila.tipo_vinculacion || 'contratista';
                selTipo.addEventListener('change', () => {
                    filas[i].tipo_vinculacion = selTipo.value;
                    filas[i].categoria_cargo = '';  // reset al cambiar tipo
                    sync();
                    render();
                });
                addField('Tipo de vinculación', selTipo);

                // Categoría de cargo (depende del tipo)
                const cats = filas[i].tipo_vinculacion === 'nombrado' ? catNombrado : catContratista;
                const selCat = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: '' }, ['—']),
                    ...cats.map(c => el('option', { value: c.valor }, [c.texto])),
                ]);
                selCat.value = fila.categoria_cargo || '';
                selCat.addEventListener('change', () => { filas[i].categoria_cargo = selCat.value; sync(); });
                addField('Categoría del cargo', selCat);

                // Nivel formación
                const selNivel = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: '' }, ['—']),
                    ...niveles.map(n => el('option', { value: n.valor }, [n.texto])),
                ]);
                selNivel.value = fila.nivel_formacion || '';
                selNivel.addEventListener('change', () => { filas[i].nivel_formacion = selNivel.value; sync(); });
                addField('Nivel de formación académica', selNivel);

                // Funciones estadísticas (desplegable Sí/No)
                // Guarda 'si'/'no'. Lee respuestas legacy guardadas como booleano.
                const selFunc = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: '' }, ['—']),
                    el('option', { value: 'si' }, ['Sí']),
                    el('option', { value: 'no' }, ['No']),
                ]);
                const funcVal = fila.funciones_estadisticas;
                selFunc.value = (funcVal === 'si' || funcVal === true) ? 'si'
                    : (funcVal === 'no' || funcVal === false) ? 'no' : '';
                selFunc.addEventListener('change', () => { filas[i].funciones_estadisticas = selFunc.value; sync(); });
                addField('¿Dentro de funciones/actividades contractuales, se describe de manera específica la realización de actividades de producción o gestión de la información estadística?', selFunc, true);

                // Etapas del proceso (multi-checkbox)
                const etapasWrap = el('div', { class: 'iced-rrhh-etapas' });
                const etapasSeleccionadas = Array.isArray(fila.etapas_proceso) ? fila.etapas_proceso : [];
                etapas.forEach(et => {
                    const cb = el('input', { type: 'checkbox', value: et.valor });
                    cb.checked = etapasSeleccionadas.includes(et.valor);
                    cb.addEventListener('change', () => {
                        const current = filas[i].etapas_proceso || [];
                        if (cb.checked && !current.includes(et.valor)) {
                            current.push(et.valor);
                        } else if (!cb.checked) {
                            const idx = current.indexOf(et.valor);
                            if (idx >= 0) current.splice(idx, 1);
                        }
                        filas[i].etapas_proceso = current;
                        sync();
                    });
                    const lbl = el('label', { class: 'iced-rrhh-etapa-chip' }, [cb, ' ', et.texto]);
                    etapasWrap.appendChild(lbl);
                });
                addField('Etapa del proceso en el que participa', etapasWrap, true);

                card.appendChild(grid);
                container.appendChild(card);
            });

            // Botón agregar
            if (filas.length < maxFilas) {
                const btnAdd = el('button', {
                    type: 'button',
                    class: 'iced-widget-btn-add',
                }, ['+ Agregar persona']);
                btnAdd.addEventListener('click', () => {
                    filas.push(newRow());
                    sync();
                    render();
                });
                container.appendChild(btnAdd);
            }
        }

        sync();
        render();
    }

    // ================================================================
    // Widget: personas-contacto-inline
    // ================================================================
    // Maneja múltiples personas de contacto (módulo A: P2-P5)
    // Estructura: [{ nombre_completo, tipo_vinculacion, cargo, correo, telefono }]

    function renderPersonasContactoInline(container, config, targetName) {
        const data = readJson(targetName, []);
        const filas = Array.isArray(data) ? data : [];  // datos legacy: '{}' de borrador oculto
        const minFilas = config.min || 1;
        const catNombrado = config.categorias_nombrado || [];
        const catContratista = config.categorias_contratista || [];
        // Sin límite máximo - permite agregar tantas personas como necesite

        function newRow() {
            return { nombre_completo: '', tipo_vinculacion: 'nombrado', cargo: '', correo: '', telefono: '' };
        }

        function sync() {
            writeJson(targetName, filas);
        }

        function render() {
            container.innerHTML = '';

            // Header informativo
            const header = el('div', { 
                class: 'iced-widget-subtitle',
                style: 'margin-bottom: 1rem; color: #64748b; font-size: 0.9rem;'
            }, [
                'Registre al menos una persona de contacto. Puede agregar tantas como necesite. ',
                el('span', { style: 'color: #dc2626;' }, ['* Campos requeridos'])
            ]);
            container.appendChild(header);

            // Contador
            const contador = el('div', { 
                style: 'margin-bottom: 1rem; font-size: 0.85rem; color: #64748b;' 
            }, [
                'Personas registradas: ',
                el('strong', {}, [String(filas.length)])
            ]);
            container.appendChild(contador);

            // Lista de personas
            filas.forEach((fila, i) => {
                const card = el('div', { 
                    class: 'iced-rrhh-card',
                    style: 'margin-bottom: 1rem; padding: 1rem; border: 1px solid #e2e8f0; border-radius: 0.5rem; background: #fff;'
                });

                // Header de la tarjeta con número y botón eliminar
                const cardHeader = el('div', { 
                    style: 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e2e8f0;'
                });
                
                const numero = el('span', { 
                    style: 'font-weight: 600; color: #000866;'
                }, ['Persona #' + (i + 1)]);
                
                // Botón eliminar (solo si hay más del mínimo)
                if (filas.length > minFilas) {
                    const btnEliminar = el('button', {
                        type: 'button',
                        style: 'background: #fee2e2; color: #dc2626; border: none; padding: 0.35rem 0.75rem; border-radius: 0.25rem; font-size: 0.8rem; cursor: pointer;'
                    }, ['Eliminar']);
                    btnEliminar.addEventListener('click', () => {
                        filas.splice(i, 1);
                        sync();
                        render();
                    });
                    cardHeader.appendChild(numero);
                    cardHeader.appendChild(btnEliminar);
                } else {
                    cardHeader.appendChild(numero);
                }
                
                card.appendChild(cardHeader);

                // Grid de campos
                const grid = el('div', { 
                    style: 'display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;'
                });

                // Nombre completo
                const grpNombre = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem;' });
                grpNombre.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['Nombre completo *']));
                const inpNombre = el('input', {
                    type: 'text',
                    class: 'iced-widget-input',
                    placeholder: 'Nombre completo',
                    value: fila.nombre_completo || ''
                });
                inpNombre.addEventListener('input', () => {
                    filas[i].nombre_completo = inpNombre.value;
                    sync();
                });
                grpNombre.appendChild(inpNombre);
                grid.appendChild(grpNombre);

                // Tipo de vinculación
                const grpTipo = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem;' });
                grpTipo.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['Tipo de vinculación *']));
                const selTipo = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: 'nombrado' }, ['Nombrado']),
                    el('option', { value: 'contratista' }, ['Contratista']),
                ]);
                selTipo.value = fila.tipo_vinculacion || 'nombrado';
                selTipo.addEventListener('change', () => {
                    filas[i].tipo_vinculacion = selTipo.value;
                    filas[i].cargo = '';  // reset cargo al cambiar tipo
                    sync();
                    render();
                });
                grpTipo.appendChild(selTipo);
                grid.appendChild(grpTipo);

                // Cargo (depende del tipo de vinculación)
                const grpCargo = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem;' });
                grpCargo.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['Cargo *']));
                const cats = filas[i].tipo_vinculacion === 'nombrado' ? catNombrado : catContratista;
                const selCargo = el('select', { class: 'iced-widget-input' }, [
                    el('option', { value: '' }, ['— Seleccione —']),
                    ...cats.map(c => el('option', { value: c.valor }, [c.texto])),
                ]);
                selCargo.value = fila.cargo || '';
                selCargo.addEventListener('change', () => {
                    filas[i].cargo = selCargo.value;
                    sync();
                });
                grpCargo.appendChild(selCargo);
                grid.appendChild(grpCargo);

                // Correo
                const grpCorreo = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem;' });
                grpCorreo.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['Correo electrónico *']));
                const inpCorreo = el('input', {
                    type: 'email',
                    class: 'iced-widget-input',
                    placeholder: 'correo@cali.gov.co',
                    value: fila.correo || ''
                });
                const errCorreo = el('span', {
                    style: 'display: none; color: #dc2626; font-size: 0.75rem;'
                }, ['Ingrese un correo electrónico válido (ej: nombre@dominio.com)']);
                inpCorreo.addEventListener('input', () => {
                    filas[i].correo = inpCorreo.value;
                    const v = inpCorreo.value.trim();
                    const ok = !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
                    inpCorreo.style.borderColor = ok ? '' : '#dc2626';
                    errCorreo.style.display = ok ? 'none' : 'block';
                    sync();
                });
                grpCorreo.appendChild(inpCorreo);
                grpCorreo.appendChild(errCorreo);
                grid.appendChild(grpCorreo);

                // Teléfono
                const grpTel = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem;' });
                grpTel.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['Teléfono']));
                const inpTel = el('input', {
                    type: 'tel',
                    inputmode: 'tel',
                    class: 'iced-widget-input',
                    placeholder: 'Ej: 3001234567 o +573001234567',
                    maxlength: '13',
                    title: 'Máximo 10 dígitos, o 12 dígitos con prefijo internacional (+)',
                    value: fila.telefono || ''
                });
                const errTel = el('span', {
                    style: 'display: none; color: #dc2626; font-size: 0.75rem;'
                }, ['Máximo 10 dígitos, o 12 con prefijo "+"']);
                inpTel.addEventListener('input', () => {
                    // Solo dígitos y un '+' inicial
                    let limpio = inpTel.value.replace(/[^0-9+]/g, '').replace(/(?!^)\+/g, '');
                    const conMas = limpio.startsWith('+');
                    const digitos = limpio.replace(/\D/g, '');
                    const maxDig = conMas ? 12 : 10;
                    let excede = false;
                    if (digitos.length > maxDig) {
                        limpio = (conMas ? '+' : '') + digitos.slice(0, maxDig);
                        excede = true;
                    }
                    if (inpTel.value !== limpio) {
                        inpTel.value = limpio;
                    }
                    errTel.style.display = excede ? 'block' : 'none';
                    inpTel.style.borderColor = excede ? '#dc2626' : '';
                    filas[i].telefono = inpTel.value;
                    sync();
                });
                grpTel.appendChild(inpTel);
                grpTel.appendChild(errTel);
                grid.appendChild(grpTel);

                card.appendChild(grid);
                container.appendChild(card);
            });

            // Botón agregar (sin límite máximo)
            const btnAdd = el('button', {
                type: 'button',
                class: 'iced-widget-btn-add',
                style: 'margin-top: 0.5rem;'
            }, ['+ Agregar otra persona']);
            btnAdd.addEventListener('click', () => {
                filas.push(newRow());
                sync();
                render();
            });
            container.appendChild(btnAdd);

            // Mensaje de validación si es necesario
            if (filas.length < minFilas) {
                const alert = el('div', {
                    style: 'margin-top: 1rem; padding: 0.75rem; background: #fef3c7; color: #92400e; border-radius: 0.375rem; font-size: 0.85rem;'
                }, [
                    '⚠️ Debe registrar al menos ' + minFilas + ' persona' + (minFilas > 1 ? 's' : '') + ' de contacto.'
                ]);
                container.appendChild(alert);
            }
        }

        sync();
        render();
    }

    // ================================================================
    // Widget: estructura-mop
    // ================================================================
    // Maneja MacroProceso → Proceso → Subproceso → Procedimientos (P7)
    // Datos de prueba hasta tener API real

    function renderEstructuraMOP(container, config, targetName) {
        // Estructura MOP real inyectada por el backend (views_iced.get_context_data).
        // Estructura: {macroprocesos: [], procesos: {macro: []},
        //   subprocesos: {proceso: []}, procedimientos: {subproceso: []},
        //   procedimientos_directos: {proceso: []}}
        // 'procedimientos_directos' cubre los procesos del MOP que no tienen
        // subprocesos y solo tienen procedimientos.
        const datosMOP = window.MOP_DATA || {
            macroprocesos: [], procesos: {}, subprocesos: {},
            procedimientos: {}, procedimientos_directos: {}
        };

        let data = readJson(targetName, []);
        if (!Array.isArray(data)) data = [];  // datos legacy: '{}' de borrador oculto
        let filas = Array.isArray(data) ? data : [];
        const minFilas = config.min || 1;

        // Asegurar mínimo de filas al inicializar
        while (filas.length < minFilas) {
            filas.push({ macroproceso_id: '', proceso_id: '', subproceso_id: '', procedimientos: [] });
        }

        function newRow() {
            return { macroproceso_id: '', proceso_id: '', subproceso_id: '', procedimientos: [] };
        }

        function sync() {
            writeJson(targetName, filas);
        }

        function render() {
            container.innerHTML = '';
            console.log('[MOP] Renderizando, filas:', JSON.parse(JSON.stringify(filas)));

            // Header informativo
            const header = el('div', { 
                class: 'iced-widget-subtitle',
                style: 'margin-bottom: 1rem; color: #64748b; font-size: 0.9rem;'
            }, [
                'Por favor, seleccione a continuación según la relación con el MOP. ',
                el('span', { style: 'color: #dc2626;' }, ['* Campos requeridos'])
            ]);
            container.appendChild(header);

            // Lista de bloques de subprocesos
            filas.forEach((fila, i) => {
                console.log(`[MOP] Renderizando fila ${i}:`, fila);
                const card = el('div', { 
                    class: 'iced-mop-card',
                    style: 'margin-bottom: 1.5rem; padding: 1.25rem; border: 1px solid #e2e8f0; border-radius: 0.5rem; background: #fff;'
                });

                // Header del bloque
                const cardHeader = el('div', { 
                    style: 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e2e8f0;'
                });
                
                const numero = el('span', { 
                    style: 'font-weight: 600; color: #000866; font-size: 1rem;'
                }, ['Registro MOP #' + (i + 1)]);
                
                // Botón eliminar
                if (filas.length > minFilas) {
                    const btnEliminar = el('button', {
                        type: 'button',
                        style: 'background: #fee2e2; color: #dc2626; border: none; padding: 0.35rem 0.75rem; border-radius: 0.25rem; font-size: 0.8rem; cursor: pointer;'
                    }, ['Eliminar']);
                    btnEliminar.addEventListener('click', () => {
                        filas.splice(i, 1);
                        sync();
                        render();
                    });
                    cardHeader.appendChild(numero);
                    cardHeader.appendChild(btnEliminar);
                } else {
                    cardHeader.appendChild(numero);
                }
                card.appendChild(cardHeader);

                // Grid de selects
                const grid = el('div', { 
                    style: 'display: grid; grid-template-columns: 1fr 120px; gap: 1rem; margin-bottom: 1rem;'
                });

                // Select MacroProceso
                const grpMacro = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem; grid-column: 1 / -1;' });
                grpMacro.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['MacroProceso *']));
                const selMacro = el('select', {
                    class: 'iced-widget-input',
                    style: 'width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem;'
                });
                selMacro.appendChild(el('option', {value: ''}, ['Seleccione...']));
                datosMOP.macroprocesos.forEach(mp => {
                    const opt = el('option', {value: mp.id}, [mp.codigo + ' - ' + mp.nombre]);
                    if (fila.macroproceso_id === mp.id) opt.selected = true;
                    selMacro.appendChild(opt);
                });
                selMacro.addEventListener('change', () => {
                    console.log(`[MOP] === MacroProceso cambiado en fila ${i}, valor: "${selMacro.value}"`);
                    filas[i].macroproceso_id = selMacro.value;
                    filas[i].proceso_id = '';
                    filas[i].subproceso_id = '';
                    filas[i].procedimientos = [];
                    console.log(`[MOP] Estado actualizado:`, JSON.parse(JSON.stringify(filas[i])));
                    sync();
                    render();
                    console.log(`[MOP] === Render completado`);
                });
                grpMacro.appendChild(selMacro);
                grid.appendChild(grpMacro);

                // Select Proceso (dependiente)
                const grpProceso = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem; grid-column: 1 / -1;' });
                grpProceso.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, ['Proceso *']));
                const tieneMacro = !!fila.macroproceso_id;
                const procesosDisponibles = tieneMacro ? datosMOP.procesos[fila.macroproceso_id] : null;
                console.log(`[MOP] Fila ${i} - Proceso: disabled=${!tieneMacro}, macroproceso_id=${fila.macroproceso_id}, procesos disponibles=`, procesosDisponibles ? procesosDisponibles.length : 0);
                const selProceso = el('select', {
                    class: 'iced-widget-input',
                    style: 'width: 100%; padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem;' + (tieneMacro ? '' : ' background: #f3f4f6;')
                });
                if (!tieneMacro) selProceso.disabled = true;
                selProceso.appendChild(el('option', {value: ''}, ['Seleccione...']));
                if (procesosDisponibles && procesosDisponibles.length > 0) {
                    procesosDisponibles.forEach(p => {
                        const opt = el('option', {value: p.id}, [p.codigo + ' - ' + p.nombre]);
                        if (fila.proceso_id === p.id) opt.selected = true;
                        selProceso.appendChild(opt);
                    });
                }
                selProceso.addEventListener('change', () => {
                    console.log(`[MOP] === Proceso cambiado en fila ${i}, valor: "${selProceso.value}"`);
                    filas[i].proceso_id = selProceso.value;
                    filas[i].subproceso_id = '';
                    filas[i].procedimientos = [];
                    console.log(`[MOP] Estado actualizado:`, JSON.parse(JSON.stringify(filas[i])));
                    sync();
                    render();
                    console.log(`[MOP] === Render completado`);
                });
                grpProceso.appendChild(selProceso);
                grid.appendChild(grpProceso);

                // Select Subproceso (dependiente)
                // En el MOP real hay procesos sin subprocesos (solo procedimientos
                // directos): en ese caso el select queda deshabilitado como N/A y
                // los procedimientos se cargan por proceso.
                const tieneProceso = !!fila.proceso_id;
                const subprocesosDisponibles = tieneProceso
                    ? (datosMOP.subprocesos[fila.proceso_id] || [])
                    : [];
                const procesoTieneSubprocesos = subprocesosDisponibles.length > 0;
                const subprocesoNoAplica = tieneProceso && !procesoTieneSubprocesos;

                const grpSub = el('div', { style: 'display: flex; flex-direction: column; gap: 0.35rem; grid-column: 1 / -1;' });
                grpSub.appendChild(el('label', { style: 'font-size: 0.85rem; font-weight: 500;' }, [
                    subprocesoNoAplica ? 'Subproceso (el proceso no tiene subprocesos)' : 'Subproceso *'
                ]));

                const selSubproceso = el('select', {
                    class: 'iced-widget-input',
                    style: 'padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem;' + (tieneProceso && !subprocesoNoAplica ? '' : ' background: #f3f4f6;')
                });
                if (!tieneProceso || subprocesoNoAplica) selSubproceso.disabled = true;
                selSubproceso.appendChild(el('option', {value: ''}, [subprocesoNoAplica ? 'No aplica' : 'Seleccione...']));
                subprocesosDisponibles.forEach(sp => {
                    const opt = el('option', {value: sp.id}, [sp.codigo + ' - ' + sp.nombre]);
                    if (fila.subproceso_id === sp.id) opt.selected = true;
                    selSubproceso.appendChild(opt);
                });
                selSubproceso.addEventListener('change', () => {
                    console.log(`[MOP] === Subproceso cambiado en fila ${i}, valor: "${selSubproceso.value}"`);
                    filas[i].subproceso_id = selSubproceso.value;
                    filas[i].procedimientos = [];
                    console.log(`[MOP] Estado actualizado:`, JSON.parse(JSON.stringify(filas[i])));
                    sync();
                    render();
                    console.log(`[MOP] === Render completado`);
                });

                // Row: select + código
                const subRow = el('div', { style: 'display: grid; grid-template-columns: 1fr 120px; gap: 1rem;' });
                subRow.appendChild(selSubproceso);

                // Código de subproceso (display)
                const codSub = fila.subproceso_id ? fila.subproceso_id : '#N/A';
                subRow.appendChild(el('input', {
                    type: 'text',
                    disabled: true,
                    value: codSub,
                    class: 'iced-widget-input',
                    style: 'padding: 0.5rem; border: 1px solid #e5e7eb; border-radius: 0.375rem; background: #f3f4f6; text-align: center;'
                }));
                grpSub.appendChild(subRow);
                grid.appendChild(grpSub);
                card.appendChild(grid);

                // Sección de procedimientos:
                // - con subproceso: procedimientos del subproceso elegido
                // - sin subprocesos en el proceso: procedimientos directos del proceso
                const fuenteProcedimientos = procesoTieneSubprocesos
                    ? (fila.subproceso_id ? datosMOP.procedimientos[fila.subproceso_id] : null)
                    : (tieneProceso ? (datosMOP.procedimientos_directos[fila.proceso_id] || null) : null);
                const mostrarProcedimientos = procesoTieneSubprocesos
                    ? !!fila.subproceso_id
                    : tieneProceso;

                if (mostrarProcedimientos) {
                    if (fuenteProcedimientos && fuenteProcedimientos.length > 0) {
                    const procSection = el('div', {
                        style: 'margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e2e8f0;'
                    });
                    procSection.appendChild(el('label', { 
                        style: 'font-size: 0.85rem; font-weight: 500; display: block; margin-bottom: 0.5rem;'
                    }, ['Procedimientos']));

                    // Lista de procedimientos seleccionados
                    fila.procedimientos.forEach((proc, pi) => {
                        const procRow = el('div', {
                            style: 'display: grid; grid-template-columns: 1fr 120px 40px; gap: 0.5rem; margin-bottom: 0.5rem;'
                        });
                        
                        const selProc = el('select', {
                            class: 'iced-widget-input',
                            style: 'padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.375rem;'
                        });
                        selProc.appendChild(el('option', {value: ''}, ['Seleccione...']));
                        fuenteProcedimientos.forEach(p => {
                            const opt = el('option', {value: p.id}, [p.codigo + ' - ' + p.nombre]);
                            if (proc === p.id) opt.selected = true;
                            selProc.appendChild(opt);
                        });
                        selProc.addEventListener('change', () => {
                            filas[i].procedimientos[pi] = selProc.value;
                            sync();
                        });
                        procRow.appendChild(selProc);
                        
                        // Código procedimiento
                        procRow.appendChild(el('input', {
                            type: 'text',
                            disabled: true,
                            value: proc || '#N/A',
                            class: 'iced-widget-input',
                            style: 'padding: 0.5rem; border: 1px solid #e5e7eb; border-radius: 0.375rem; background: #f3f4f6; text-align: center;'
                        }));
                        
                        // Botón eliminar procedimiento
                        const btnDelProc = el('button', {
                            type: 'button',
                            style: 'background: #fee2e2; color: #dc2626; border: none; border-radius: 0.25rem; cursor: pointer;'
                        }, ['×']);
                        btnDelProc.addEventListener('click', () => {
                            filas[i].procedimientos.splice(pi, 1);
                            sync();
                            render();
                        });
                        procRow.appendChild(btnDelProc);
                        
                        procSection.appendChild(procRow);
                    });

                    // Botón agregar procedimiento
                    const btnAddProc = el('button', {
                        type: 'button',
                        style: 'background: #e0f2fe; color: #0284c7; border: none; padding: 0.35rem 0.75rem; border-radius: 0.25rem; font-size: 0.8rem; cursor: pointer; margin-top: 0.5rem;'
                    }, ['+ Agregar procedimiento']);
                    btnAddProc.addEventListener('click', () => {
                        filas[i].procedimientos.push('');
                        sync();
                        render();
                    });
                    procSection.appendChild(btnAddProc);

                    card.appendChild(procSection);
                    } else {
                        // Nivel seleccionado pero sin procedimientos registrados
                        const noProcMsg = el('div', {
                            style: 'margin-top: 1rem; padding: 0.75rem; background: #f1f5f9; border-radius: 0.375rem; font-size: 0.85rem; color: #64748b;'
                        }, [procesoTieneSubprocesos
                            ? 'No hay procedimientos disponibles para este subproceso.'
                            : 'No hay procedimientos disponibles para este proceso.']);
                        card.appendChild(noProcMsg);
                    }
                }

                container.appendChild(card);
            });

            // Botón agregar subproceso
            const btnAdd = el('button', {
                type: 'button',
                class: 'iced-widget-btn-add',
                style: 'margin-top: 0.5rem; padding: 0.75rem 1.5rem; font-size: 0.95rem;'
            }, ['+ Agregar registro']);
            btnAdd.addEventListener('click', () => {
                filas.push(newRow());
                sync();
                render();
            });
            container.appendChild(btnAdd);

            // Link externo
            const linkDiv = el('div', {
                style: 'margin-top: 1rem; padding: 0.75rem; background: #f1f5f9; border-radius: 0.375rem; font-size: 0.85rem;'
            }, [
                'Si su respuesta es Sí, por favor diríjase a la ficha técnica de producción de información del organismo. ',
                el('a', {
                    href: 'https://docs.google.com/spreadsheets/d/1sGhiv9T4Q3iUGEjKnA20-jD6xyaTgd2mPwLqY7b6NIM/edit?gid=226015127',
                    target: '_blank',
                    style: 'color: #2563eb; text-decoration: underline;'
                }, ['Consultar aquí'])
            ]);
            container.appendChild(linkDiv);

            // Mensaje de validación si es necesario
            if (filas.length < minFilas) {
                const alert = el('div', {
                    style: 'margin-top: 1rem; padding: 0.75rem; background: #fef3c7; color: #92400e; border-radius: 0.375rem; font-size: 0.85rem;'
                }, [
                    '⚠️ Debe registrar al menos ' + minFilas + ' registro' + (minFilas > 1 ? 's' : '') + '.'
                ]);
                container.appendChild(alert);
            }
        }

        sync();
        render();
    }

    // ================================================================
    // Auto-init
    // ================================================================

    function initWidgets() {
        document.querySelectorAll('[data-iced-widget]').forEach(container => {
            // Siempre reinicializar widgets en contenedores recién visibles
            container.dataset.icedInit = '1';

            const tipo = container.dataset.icedWidget;
            const target = container.dataset.target;
            let config = {};
            try {
                config = JSON.parse(container.dataset.config || '{}');
            } catch (e) {
                console.error('ICED widget config inválido:', e);
                return;
            }

            // Un widget que falle no debe impedir inicializar los demás
            try {
                switch (tipo) {
                    case 'checkbox-tabla':
                        renderCheckboxTabla(container, config, target);
                        break;
                    case 'tabla-simple':
                    case 'tabla-compleja':
                        renderTablaSimple(container, config, target);
                        break;
                    case 'desplegables-multiples':
                        renderDesplegablesMultiples(container, config, target);
                        break;
                    case 'matriz-satisfaccion':
                        renderMatrizSatisfaccion(container, config, target);
                        break;
                    case 'opciones-con-detalle':
                        renderOpcionesDetalle(container, config, target);
                        break;
                    case 'rrhh-tabla':
                        renderRRHHTabla(container, config, target);
                        break;
                    case 'personas-contacto-inline':
                        renderPersonasContactoInline(container, config, target);
                        break;
                    case 'estructura-mop':
                        renderEstructuraMOP(container, config, target);
                        break;
                    default:
                        console.warn('ICED widget desconocido:', tipo);
                }
            } catch (e) {
                console.error('ICED widget falló al renderizar:', tipo, target, e);
            }
        });
    }

    // Función para agregar listeners de sincronización a campos JSON
    function addSyncListeners() {
        document.querySelectorAll('input[type="hidden"].iced-json-field').forEach(function(field) {
            if (field.dataset.syncListener === '1') return; // Ya tiene listener
            field.dataset.syncListener = '1';
            field.addEventListener('sync', function() {
                // Forzar que el widget se renderice nuevamente para sincronizar
                const container = document.querySelector('[data-target="' + field.name + '"], [data-target$="-' + field.name + '"], [data-target*="' + field.name + '"]');
                if (container) {
                    // Disparar evento de cambio para forzar sincronización
                    field.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initWidgets();
            addSyncListeners();
            preventEnterSubmit();
            preventNumberScroll();
        });
    } else {
        initWidgets();
        addSyncListeners();
        preventEnterSubmit();
        preventNumberScroll();
    }

    // Expose for manual reinit
    window.ICEDWidgets = { init: initWidgets };

    // Listen for custom event to init widgets on conditional fields
    window.addEventListener('initWidgets', function(e) {
        console.log('[ICEDWidgets] Evento initWidgets recibido, re-inicializando...');
        // Small delay to ensure DOM is updated
        setTimeout(function() {
            initWidgets();
            addSyncListeners();
        }, 50);
    });
})();
