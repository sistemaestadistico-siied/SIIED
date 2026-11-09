/* CAMPAÑA · LA OPERACIÓN ESTADÍSTICA
 * Las 8 etapas del ciclo de una operación estadística (Marco Operativo
 * de Procesos) convertidas en misiones jugables. Cada etapa declara el
 * mapa, la misión y el brief narrativo. */

export const ETAPAS = [
    {
        id: 'deteccion', mapa: 'barrio', mision: 'deteccion', icon: '📡',
        etapa: 'Detección de necesidades',
        breve: 'Recorre el territorio y sintoniza los puntos de necesidad de información.',
        lore: 'Toda operación estadística nace de una necesidad. Antes de mover un dedo hay que salir al terreno: detectar dónde, qué y para quién hace falta información. Los sensores marcan los puntos — sintonízalos todos.',
        nota: 'Los puntos de necesidad están cerca de los puntos de interés del barrio.',
    },
    {
        id: 'diseno', mapa: 'arena', mision: 'diseno', icon: '📐',
        etapa: 'Diseño',
        breve: 'Arma el instrumento: cada pieza del marco metodológico a la mesa.',
        lore: 'Con la necesidad detectada toca diseñar: variable, universo, método de captación, periodicidad, cobertura e instrumento. Cada pieza pesa — una a la vez hasta la mesa de diseño.',
        nota: 'Solo puedes llevar una pieza a la vez. No descuides la retaguardia.',
    },
    {
        id: 'construccion', mapa: 'torres', mision: 'construccion', icon: '🗼',
        etapa: 'Construcción',
        breve: 'Monta la infraestructura: instala las estaciones de captura en las torres.',
        lore: 'El diseño es papel: ahora se construye. Sube por los ascensores de datos e instala cada estación de captura en la cima de las torres del parque.',
        nota: 'Mantén E junto a cada panel para instalar la estación.',
    },
    {
        id: 'recoleccion', mapa: 'barrio', mision: 'recoleccion', icon: '🌃',
        etapa: 'Recolección / Acopio',
        breve: 'Día de campo: recupera los paquetes de datos y entrégalos en el Kiosco SIIED.',
        lore: 'Los informantes repartieron los paquetes de datos por todo el barrio. Recógelos y regrésalos al punto de acopio — el ruido de los datos crudos atrae hostiles.',
        nota: 'Puedes cargar varios paquetes y entregarlos de una vez en el Kiosco.',
    },
    {
        id: 'procesamiento', mapa: 'pila', mision: 'procesamiento', icon: '⚙️',
        etapa: 'Procesamiento',
        breve: 'Depura el acervo: elimina NULLs y duplicados. Los registros válidos son intocables.',
        lore: 'Los datos crudos siempre traen ruido: valores nulos, duplicados, formatos rotos. En el patio de normalización toca depurar a mano — pero ojo: los REGISTROS VÁLIDOS (verde) son intocables. Eliminar tres y la operación queda degradada.',
        nota: 'ROJO = ruido, se elimina. VERDE = registro válido, huye de ti. 3 errores = misión fallida.',
    },
    {
        id: 'analisis', mapa: 'pila', mision: 'analisis', icon: '🗂️',
        etapa: 'Análisis',
        breve: 'Clasifica cada registro procesado en la torre de su serie.',
        lore: 'Con datos limpios empieza el análisis: agrupar por serie temática. Cada chontaduro-registro va a la torre de su color — mezclar series es el error clásico del analista novato.',
        nota: 'Un registro a la vez, a la torre de su serie.',
    },
    {
        id: 'difusion', mapa: 'barrio', mision: 'difusion', icon: '📰',
        etapa: 'Difusión',
        breve: 'Distribuye el informe final por todos los canales de difusión.',
        lore: 'Resultados listos: un informe que vale oro. Llévalo a cada canal — portal web, ADDA, boletín, medio físico — mientras la desinformación intenta interceptarte. Datos que no se difunden, no existen.',
        nota: 'Los canales se publican en orden: sigue el marcador activo.',
    },
    {
        id: 'evaluacion', mapa: 'arena', mision: 'evaluacion', icon: '⚔️',
        etapa: 'Evaluación',
        breve: 'Resiste la revisión externa: 4 oleadas y el jefe final, EL AUDITOR.',
        lore: 'Última etapa: el equipo de evaluación examina la operación completa. Cuatro oleadas de revisión — y al final viene EL AUDITOR en persona. Sobrevive para cerrar el ciclo.',
        nota: 'El Auditor es más grande, más resistente y dispara más certero.',
    },
];
