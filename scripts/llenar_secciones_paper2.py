# -*- coding: utf-8 -*-
"""Llena el contenido de las 15 SeccionPaper del ProductoAcademico id=2
(Proyecciones experimentales de población por comunas, Cali 2019-2030)
con texto académico completo en HTML, fórmulas LaTeX (MathJax) y tablas.
Idempotente: ejecutar cuantas veces sea necesario.
"""
from indicadores.models import ProductoAcademico, SeccionPaper, Indicador

P = ProductoAcademico.objects.get(pk=2)
IND_COMUNA = Indicador.objects.get(pk=1954)   # Población por comuna
IND_SEXO = Indicador.objects.get(pk=1955)     # Comuna + sexo
IND_PIRAMIDE = Indicador.objects.get(pk=1956) # Comuna + sexo + grupo edad

TABLA_FUENTES = """
<table>
<thead><tr><th>Componente</th><th>Fuente principal</th><th>Desagregación</th><th>Uso en el ejercicio</th></tr></thead>
<tbody>
<tr><td>Población</td><td>Censos 2005 y 2018, DANE</td><td>Comuna, sexo, edad</td><td>Base y relaciones históricas</td></tr>
<tr><td>Área mayor</td><td>Proyecciones post-COVID, DANE</td><td>Año, sexo, edad, área</td><td>Techo y conciliación</td></tr>
<tr><td>Fecundidad</td><td>Censos y nacimientos de Estadísticas Vitales</td><td>Edad de la madre y residencia</td><td>TOPALS e IDF</td></tr>
<tr><td>Mortalidad</td><td>Defunciones de Estadísticas Vitales</td><td>Sexo, edad y residencia</td><td>TOPALS y supervivencia</td></tr>
<tr><td>Territorio</td><td>Cartografía censal y límites administrativos</td><td>Comuna</td><td>Armonización geográfica</td></tr>
<tr><td>Resultados</td><td>Libro RC suministrado</td><td>Año, comuna, sexo, edad</td><td>Análisis 2019–2030</td></tr>
</tbody>
</table>
"""

TABLA_DICCIONARIO = """
<table>
<thead><tr><th>Variable</th><th>Definición</th></tr></thead>
<tbody>
<tr><td>AÑO</td><td>Año calendario de la estimación o proyección.</td></tr>
<tr><td>COMUNA</td><td>Código de la comuna urbana, de 1 a 22.</td></tr>
<tr><td>GRUPO_EDAD</td><td>Grupo quinquenal; el último identifica 80 años o más.</td></tr>
<tr><td>EDAD</td><td>Edad simple; el valor 80 representa el grupo abierto 80+.</td></tr>
<tr><td>HOMBRES</td><td>Población masculina redondeada.</td></tr>
<tr><td>MUJERES</td><td>Población femenina redondeada.</td></tr>
<tr><td>HOMBRES_DEC</td><td>Población masculina antes del redondeo.</td></tr>
<tr><td>MUJERES_DEC</td><td>Población femenina antes del redondeo.</td></tr>
</tbody>
</table>
"""

TABLA_SIIED = """
<table>
<thead><tr><th>Elemento</th><th>Identificador</th><th>Descripción</th></tr></thead>
<tbody>
<tr><td>Conjunto de datos</td><td>ConjuntoDatos id 32</td><td>Proyecciones de población por comuna, sexo y grupo de edad 2019-2030; archivo <code>microdata/Proyecciones_poblacion_comuna_2019_2030.csv</code> (8.976 filas).</td></tr>
<tr><td>Indicador 1954</td><td>Población por comuna</td><td>264 datos; desagregación geográfica Comuna; gráfico de barras, 22 series.</td></tr>
<tr><td>Indicador 1955</td><td>Población por comuna y sexo</td><td>528 datos; desagregaciones Comuna + Sexo; gráfico de líneas.</td></tr>
<tr><td>Indicador 1956</td><td>Población por comuna, sexo y grupo de edad</td><td>8.976 datos; desagregaciones Comuna + Sexo + Grupo de edad; pirámide poblacional.</td></tr>
<tr><td>Clasificación</td><td>Subtema Población</td><td>Demografía y población › Salud, Bienestar Social y Demografía.</td></tr>
<tr><td>Dominio geográfico</td><td>Comuna (id 270)</td><td>Nivel geográfico 4 — Comunas y Corregimientos; 22 desagregaciones enlazadas a capas cartográficas.</td></tr>
<tr><td>Dominios temáticos</td><td>Sexo (id 2), Grupo de edad (id 529)</td><td>Hombres/Mujeres/Total; 17 grupos quinquenales 0 a 4 – 80 y más.</td></tr>
</tbody>
</table>
"""

REFERENCIAS = """
<ol>
<li>Alcaldía de Santiago de Cali. (2019, 22 de octubre). En un 18,2 % se ajustó el censo poblacional en Cali. <a href="https://www.cali.gov.co/hacienda/publicaciones/150182/en-un-182-se-ajusto-el-censo-poblacional-en-cali/" target="_blank" rel="noopener">cali.gov.co</a></li>
<li>Brito, L. P. G. de, Cavenaghi, S., &amp; Jannuzzi, P. de M. (2010). Estimativas e projeções populacionais para pequenos domínios: Uma avaliação da precisão para municípios do Rio de Janeiro em 2000 e 2007. <em>Revista Brasileira de Estudos de População, 27</em>(1), 35–57. <a href="https://doi.org/10.1590/S0102-30982010000100004" target="_blank" rel="noopener">doi.org/10.1590/S0102-30982010000100004</a></li>
<li>De Beer, J. (2011). A new relational method for smoothing and projecting age-specific fertility rates: TOPALS. <em>Demographic Research, 24</em>, 409–454. <a href="https://doi.org/10.4054/DemRes.2011.24.18" target="_blank" rel="noopener">doi.org/10.4054/DemRes.2011.24.18</a></li>
<li>De Beer, J. (2012). Smoothing and projecting age-specific probabilities of death by TOPALS. <em>Demographic Research, 27</em>, 543–592. <a href="https://doi.org/10.4054/DemRes.2012.27.20" target="_blank" rel="noopener">doi.org/10.4054/DemRes.2012.27.20</a></li>
<li>Departamento Administrativo Nacional de Estadística. (2021). <em>Metodología general de proyecciones de población y estudios demográficos</em>. DANE.</li>
<li>Departamento Administrativo Nacional de Estadística. (2023). <em>Proyecciones de población con la actualización post COVID-19 calculadas con base en el CNPV 2018</em>. DANE.</li>
<li>Duchesne, L. (1988). <em>Proyecciones de población por sexo y edad para áreas intermedias y menores</em>. CELADE, Serie A, No. 187. Repositorio CEPAL.</li>
<li>Dyrting, S. (2020). Smoothing migration intensities with P-TOPALS. <em>Demographic Research, 43</em>, 1607–1650. <a href="https://doi.org/10.4054/DemRes.2020.43.55" target="_blank" rel="noopener">doi.org/10.4054/DemRes.2020.43.55</a></li>
<li>Dyrting, S., Taylor, A., &amp; Wilson, T. (2024). Application of P-TOPALS for smoothing input data for population projections "at the Edge". <em>Population Research and Policy Review, 43</em>, Article 31. <a href="https://doi.org/10.1007/s11113-024-09874-7" target="_blank" rel="noopener">doi.org/10.1007/s11113-024-09874-7</a></li>
<li>Freire, F. H. M. de A., Gonzaga, M. R., &amp; Gomes, M. M. F. (2020). Projeções populacionais por sexo e idade para pequenas áreas no Brasil. <em>Revista Latinoamericana de Población, 14</em>(26), 124–149. <a href="https://doi.org/10.31406/relap2020.v14.i1.n26.6" target="_blank" rel="noopener">doi.org/10.31406/relap2020.v14.i1.n26.6</a></li>
<li>Gonzaga, M. R., &amp; Schmertmann, C. P. (2016). Estimating age- and sex-specific mortality rates for small areas with TOPALS regression: An application to Brazil in 2010. <em>Revista Brasileira de Estudos de População, 33</em>(3), 629–652. <a href="https://doi.org/10.20947/S0102-30982016c0009" target="_blank" rel="noopener">doi.org/10.20947/S0102-30982016c0009</a></li>
<li>Loaiza Cerón, W., &amp; Carvajal Escobar, Y. (2014). Índice de segregación espacial y socioeconómico (ISES) en las comunas de Santiago de Cali. <em>Cuadernos de Vivienda y Urbanismo, 7</em>(13).</li>
<li>Schmertmann, C. P., &amp; Gonzaga, M. R. (2018). Bayesian estimation of age-specific mortality and life expectancy for small areas with defective vital records. <em>Demography, 55</em>(4), 1363–1388. <a href="https://doi.org/10.1007/s13524-018-0695-2" target="_blank" rel="noopener">doi.org/10.1007/s13524-018-0695-2</a></li>
<li>Smith, S. K., Tayman, J., &amp; Swanson, D. A. (2013). <em>A practitioner's guide to state and local population projections</em>. Springer. <a href="https://doi.org/10.1007/978-94-007-7551-0" target="_blank" rel="noopener">doi.org/10.1007/978-94-007-7551-0</a></li>
<li>United Nations. (1956). <em>Manual III: Methods for population projections by sex and age</em>. Department of Economic and Social Affairs.</li>
<li>United Nations. (1974). <em>Manual VIII: Methods for projections of urban and rural population</em>. Department of Economic and Social Affairs.</li>
<li>Wilson, T., Grossman, I., Alexander, M., Rees, P., &amp; Temple, J. (2022). Methods for small area population forecasts: State-of-the-art and research needs. <em>Population Research and Policy Review, 41</em>(3), 865–898. <a href="https://doi.org/10.1007/s11113-021-09671-6" target="_blank" rel="noopener">doi.org/10.1007/s11113-021-09671-6</a></li>
</ol>
"""

# ══ Contenido por numero_orden ══

CONTENIDO = {
0: dict(contenido="""
<p>Este documento presenta la metodología y los resultados de un ejercicio experimental de proyecciones de población para las 22 comunas urbanas de Santiago de Cali durante 2019–2030. La arquitectura metodológica conserva el esquema empleado en las proyecciones de Medellín: construcción y evaluación de insumos, suavización de patrones demográficos, aplicación del método de relación de cohortes de Duchesne, contracción bayesiana empírica de factores diferenciales y conciliación con la proyección del área mayor. El alcance se limita de manera explícita a comunas; no comprende corregimientos ni población rural.</p>
<p>El enfoque responde a una dificultad clásica de las proyecciones para áreas pequeñas: los componentes demográficos locales presentan elevada variabilidad, conteos reducidos y sensibilidad a movimientos residenciales. La literatura reciente recomienda combinar modelos simplificados por cohortes, procedimientos de suavización, información del área mayor y mecanismos de coherencia territorial, en lugar de extrapolar de forma independiente cada territorio (Wilson et al., 2022). La evidencia latinoamericana muestra que la contracción bayesiana puede estabilizar relaciones de cohortes sin eliminar completamente la heterogeneidad local (Freire et al., 2020).</p>
<p>Para este documento se utilizó exclusivamente la serie de resultados 2019–2030. El agregado de las comunas pasa de <strong>2.194.330</strong> personas en 2019 a un máximo de <strong>2.230.667</strong> en 2022 y posteriormente desciende hasta <strong>2.181.620</strong> en 2030. Entre los extremos del periodo, el cambio neto es de <strong>-12.710 habitantes, equivalente a -0,58%</strong>. Esta trayectoria agregada oculta diferencias internas: siete comunas presentan crecimiento y quince reducción poblacional.</p>
<p>La transformación más relevante ocurre en la composición por edad. La participación de la población de 0 a 14 años baja de 18,74% en 2019 a 15,08% en 2030, mientras el peso de 65 años o más aumenta de 12,18% a 15,92%. En consecuencia, el índice de envejecimiento pasa de 65,0 a 105,6 personas mayores por cada 100 menores de 15 años. Este desplazamiento exige interpretar las proyecciones no solo como una serie de totales, sino como una base para anticipar demandas territoriales diferenciadas de educación, salud, cuidado y accesibilidad urbana.</p>
<p>Los resultados deben leerse como una trayectoria condicionada por los supuestos y por la información disponible, no como una predicción exacta. La población de cada comuna se encuentra restringida por el techo del área mayor y por la lógica de continuidad de las cohortes; por ello, cambios futuros en migración, vivienda, mortalidad, fecundidad, delimitación territorial o calidad de registros pueden modificar la senda esperada. La transparencia sobre esas condiciones es parte integral de la calidad metodológica.</p>
<p><em>La condición experimental debe acompañar toda publicación, descarga o uso secundario. Los resultados no sustituyen las proyecciones oficiales del DANE.</em></p>
"""),

1: dict(contenido="""
<p>Las proyecciones de población por sexo y edad constituyen un instrumento básico para dimensionar la demanda futura de bienes, equipamientos y servicios públicos. En el nivel intraurbano permiten relacionar el volumen de habitantes con etapas específicas del curso de vida: primera infancia, edad escolar, población en edades potencialmente activas y personas mayores. La desagregación por comunas resulta especialmente relevante porque los promedios municipales pueden ocultar cambios de signo contrario entre zonas de una misma ciudad.</p>
<p>Santiago de Cali presenta una estructura territorial urbana compuesta por 22 comunas, con diferencias históricas en consolidación urbana, acceso a infraestructura, composición socioeconómica y patrones de ocupación. Los estudios sobre segregación en la ciudad han mostrado que las condiciones sociales y espaciales no se distribuyen homogéneamente y que existen contrastes entre las laderas occidentales, el oriente asociado al río Cauca y los sectores de mayor ingreso del norte y el sur (Loaiza Cerón &amp; Carvajal Escobar, 2014). Estas desigualdades justifican producir resultados demográficos a una escala inferior al total municipal.</p>
<p>El Censo Nacional de Población y Vivienda de 2018 proporciona el marco estructural más reciente de cobertura nacional para caracterizar población y viviendas. No obstante, una proyección de pequeñas áreas no puede construirse mediante la simple repetición de proporciones censales, porque las cohortes cambian a ritmos diferentes y la movilidad residencial altera la distribución interna. Por ello se requiere un procedimiento que preserve la coherencia con el área mayor y, al mismo tiempo, admita diferenciales locales.</p>
<p>El ejercicio fue desarrollado de manera colaborativa por un equipo técnico interdisciplinar y adopta los métodos empleados en las proyecciones de Medellín. La transferencia metodológica no significa que ambas ciudades tengan dinámicas idénticas; implica utilizar un marco común de estimación, evaluación y ajuste, reemplazando los insumos territoriales y demográficos por los correspondientes a Cali. La comparabilidad metodológica mejora la trazabilidad, mientras la calibración local evita asumir estructuras ajenas a la ciudad.</p>
<p>El documento se organiza desde los fundamentos conceptuales hacia la especificación operativa y los resultados. Primero se presenta la justificación, el marco conceptual y la evidencia académica; luego se desarrollan TOPALS, la relación de cohortes, los índices diferenciales y el estimador bayesiano; finalmente se describen los insumos, la implementación, la evaluación de consistencia y las transformaciones observadas entre 2019 y 2030. Esta secuencia conecta explícitamente los conceptos demográficos con las decisiones de cálculo.</p>
"""),

2: dict(contenido="""
<p>Las proyecciones oficiales municipales son indispensables para establecer la trayectoria general de Cali, pero no satisfacen por sí solas la demanda de información de las comunas. La planeación de cupos escolares, redes de cuidado, atención primaria, transporte, espacio público y programas sociales requiere conocer dónde se concentrarán los distintos grupos de edad. Una asignación basada solamente en el total de la ciudad puede producir sobreoferta en unas zonas y déficit en otras.</p>
<p>La necesidad de actualización también se relaciona con la ruptura que produjo la pandemia de COVID-19 en los componentes demográficos. La mortalidad aumentó de forma extraordinaria, la fecundidad y la formación de hogares cambiaron, y la movilidad residencial experimentó alteraciones que no estaban contenidas en escenarios previos. Aunque las series posteriores tienden a estabilizarse, el choque exige revisar los niveles y las tendencias que alimentan los ejercicios submunicipales.</p>
<p>En áreas pequeñas, los errores relativos pueden ser mayores que en una proyección municipal, dado que un número reducido de eventos o movimientos modifica de manera visible una tasa local. Brito, Cavenaghi y Jannuzzi (2010) muestran que la precisión de las estimaciones para dominios pequeños depende tanto del tamaño poblacional como del método y del horizonte. Por esta razón, el presente ejercicio no proyecta cada comuna como un sistema completamente independiente, sino que aprovecha la información estructural del área mayor.</p>
<p>La justificación técnica se apoya igualmente en la coherencia aditiva. La suma de las 22 comunas debe reproducir, para cada sexo, edad y año, el total urbano utilizado como control. Esta restricción evita que la acumulación de errores locales genere una ciudad implausible y permite que las diferencias territoriales se interpreten como redistribución y crecimiento diferencial dentro de un marco común.</p>
<p>Finalmente, el carácter experimental es una fortaleza y una limitación. Permite evaluar métodos contemporáneos, producir insumos útiles y documentar aprendizajes institucionales; al mismo tiempo, obliga a distinguir claramente entre resultados técnicos y cifras oficialmente adoptadas. La justificación de uso depende, por tanto, de una gobernanza que conserve archivos fuente, supuestos, versiones y resultados de validación.</p>
"""),

3: dict(contenido="""
<h3>3.1. Objetivo general</h3>
<p>Estimar la población de las 22 comunas urbanas de Santiago de Cali por sexo y edad simple para el periodo 2019–2030, mediante un procedimiento coherente con la proyección del área mayor y basado en relaciones de cohortes, suavización de patrones demográficos y ajuste bayesiano empírico.</p>
<p>El objetivo combina tres dimensiones que no deben separarse: <strong>volumen, estructura y territorio</strong>. El volumen informa cuántas personas residen en cada comuna; la estructura describe cómo se distribuyen por sexo y edad; y el territorio permite identificar dónde se concentran las demandas asociadas al curso de vida. La utilidad práctica surge precisamente de integrar estas dimensiones.</p>
<p>La proyección busca servir como soporte para la planeación urbana, social y sectorial. No pretende anticipar cada evento individual ni sustituir registros administrativos; ofrece una trayectoria demográfica plausible y consistente bajo un conjunto de supuestos. Esta distinción es fundamental para evitar que una proyección se interprete como conteo observado.</p>
<p>La orientación hacia edades simples permite reagrupar posteriormente la información conforme a necesidades sectoriales sin perder detalle. Así, la misma base puede producir grupos escolares, edades reproductivas, edades laborales o grupos de personas mayores. La apertura del grupo final en 80 años o más refleja la estructura del archivo de resultados suministrado.</p>
<p>El objetivo se desarrolla bajo una perspectiva de reproducibilidad. Cada transformación debe poder rastrearse desde los datos censales y vitales hasta los factores de crecimiento, los ajustes de coherencia y las salidas anuales. La documentación metodológica forma parte del producto y no constituye un anexo accesorio.</p>
<h3>3.2. Objetivos específicos</h3>
<ol>
<li><strong>Organizar y evaluar insumos</strong> de población, fecundidad y mortalidad: verificar cobertura temporal, correspondencia geográfica, codificación de sexo y edad, consistencia de totales y compatibilidad entre fuentes.</li>
<li><strong>Estimar patrones demográficos regulares</strong> para el área mayor, evitando que fluctuaciones aleatorias por edad se transmitan a las comunas mediante el modelo relacional TOPALS (de Beer, 2011, 2012).</li>
<li><strong>Calcular relaciones de supervivencia y crecimiento de cohortes</strong> para distribuir en las comunas la evolución del área mayor, con el método de Duchesne diseñado para áreas intermedias y menores.</li>
<li><strong>Estabilizar los factores diferenciales</strong> mediante contracción bayesiana empírica, aproximando las estimaciones menos confiables al promedio del conjunto (Freire, Gonzaga y Gomes, 2020).</li>
<li><strong>Producir indicadores y diagnósticos</strong> de evaluación: crecimiento, estructura por grandes grupos, relación de masculinidad, dependencia demográfica, envejecimiento y coherencia aditiva.</li>
</ol>
<h3>3.3. Alcance y limitaciones</h3>
<p>La cobertura geográfica comprende exclusivamente las comunas urbanas numeradas del 1 al 22. No se proyectan los corregimientos, los centros poblados rurales ni el rural disperso. Por ello, el total agregado debe interpretarse como población del sistema de comunas utilizado en el ejercicio y no como sinónimo automático de población municipal total.</p>
<p>La cobertura temporal efectiva es 2019–2030. La hoja denominada 2018 del libro original no se utilizó, de acuerdo con la instrucción recibida, porque el documento debía construirse únicamente desde 2019. La comparación principal de resultados se realiza entre 2019 y 2030.</p>
<p>La desagregación considera hombres, mujeres y edades simples desde cero hasta 80 años. En el archivo, la edad 80 funciona como grupo abierto de 80 años o más; en consecuencia, los indicadores de longevidad dentro de la vejez avanzada no pueden calcularse con la misma precisión que si existieran edades de 80 a 100 o más. Esta agregación debe conservarse al redistribuir o publicar los resultados.</p>
<p>El método supone continuidad suficiente en la dinámica de las cohortes y coherencia con el techo del área mayor. No modela explícitamente proyectos de vivienda, reasentamientos, cambios normativos del suelo ni choques migratorios futuros, salvo en la medida en que estén contenidos en las relaciones históricas y en la proyección superior. Las intervenciones urbanas de gran escala pueden invalidar localmente el supuesto de continuidad.</p>
<p>Finalmente, la incertidumbre no se expresa mediante intervalos probabilísticos en el archivo entregado. El ajuste bayesiano reduce inestabilidad, pero no convierte la proyección en una estimación sin error. Se recomienda complementar futuras versiones con escenarios o intervalos, tal como propone la revisión internacional sobre pronósticos de pequeñas áreas (Wilson et al., 2022).</p>
"""),

4: dict(contenido="""
<h3>4.1. Proyecciones y estimaciones</h3>
<p>Una estimación demográfica busca aproximar el tamaño o la estructura de una población en una fecha para la cual no existe una medición completa. Una proyección, en cambio, describe la evolución futura que resultaría de aplicar determinados supuestos a una población inicial. El término proyección enfatiza su carácter condicional: si cambian los supuestos o se incorpora nueva evidencia, la trayectoria debe revisarse.</p>
<p>El método de componentes por cohortes representa a la población como grupos que envejecen, sobreviven, se reproducen y migran. Para cada sexo y edad, la población futura resulta de la población precedente, las probabilidades de supervivencia y el saldo migratorio; los nacimientos forman las nuevas cohortes. En áreas pequeñas, la aplicación completa puede verse limitada por la escasez de eventos locales y por la dificultad de estimar migración.</p>
<p>Los métodos de relación de cohortes simplifican esa arquitectura mediante razones de cambio entre cohortes observadas en dos momentos. Estas razones incorporan de manera conjunta la supervivencia y la migración neta de una cohorte, sin exigir estimarlas por separado para cada comuna. Su principal ventaja es la parsimonia; su principal riesgo es proyectar anomalías históricas como si fueran permanentes.</p>
<p>La proyección de un área menor debe mantener relación con el sistema territorial al que pertenece. El enfoque top-down comienza por una proyección del área mayor y distribuye el total entre unidades menores según patrones diferenciales. La conciliación posterior asegura aditividad y evita que los totales de las comunas se separen de la senda urbana o municipal adoptada como referencia.</p>
<h3>4.2. Población de área menor</h3>
<p>Una pequeña área no se define solamente por un umbral poblacional. También es una unidad territorial en la que los eventos demográficos son pocos, la movilidad tiene gran peso relativo y las decisiones de planeación exigen detalle espacial. Una comuna de gran tamaño puede seguir siendo "pequeña" desde la perspectiva estadística cuando se cruza por sexo y edad simple.</p>
<p>La variabilidad aleatoria aumenta al reducirse los denominadores. Un traslado residencial, un conjunto habitacional o una concentración institucional puede alterar fuertemente una edad específica, aunque no represente una tendencia duradera. Por ello se combinan información local y patrones del área mayor mediante suavización y contracción.</p>
<p>La literatura identifica una caja de herramientas más limitada para pequeñas áreas que para poblaciones nacionales. Entre las alternativas se encuentran extrapolaciones, métodos comparativos, relaciones de cohortes, desagregación de proyecciones superiores, microsimulación y modelos espaciales. Wilson et al. (2022) destacan que ninguna técnica domina en todos los contextos y que la evaluación empírica debe orientar la elección.</p>
<p>En Cali, la comuna es una unidad administrativa pertinente para la planeación, pero no constituye un sistema demográfico cerrado. Las personas se desplazan entre comunas por vivienda, empleo, educación y cuidado, de modo que la migración interna puede superar en importancia a la diferencia entre nacimientos y defunciones. El método debe interpretar los cambios de cohorte como resultados territoriales netos, no como historias individuales.</p>
<p>La heterogeneidad socioespacial añade otra capa de complejidad. Los patrones de segregación y expansión urbana pueden asociarse con estructuras de edad diferenciadas, pero la proyección no debe asignar causalidad automática. Los indicadores describen dónde y cómo cambia la estructura; la explicación causal requiere integrar información de vivienda, mercado de suelo, movilidad y condiciones sociales.</p>
<h3>4.3. Transición demográfica</h3>
<p>La transición demográfica describe el paso desde regímenes de alta fecundidad y mortalidad hacia niveles bajos de ambos componentes. Durante ese proceso cambian el crecimiento y la forma de la pirámide: primero aumenta la población infantil, luego crece la proporción en edades activas y, finalmente, se expande el peso de las edades mayores. La transformación no ocurre con la misma velocidad en todos los territorios.</p>
<p>En áreas urbanas consolidadas, la disminución de nacimientos estrecha la base de la pirámide, mientras la supervivencia acumulada ensancha las edades avanzadas. Sin embargo, la migración residencial puede reforzar o contrarrestar el patrón: sectores que atraen hogares jóvenes pueden conservar bases amplias, mientras zonas con permanencia de residentes antiguos envejecen con rapidez. Así, la transición demográfica adquiere una expresión espacial intraurbana.</p>
<p>La estructura por edad condiciona la demanda social. Una elevada proporción de niños incrementa necesidades educativas y de cuidado inicial; una mayor presencia de edades activas modifica transporte, empleo y vivienda; y el crecimiento de la población mayor exige servicios de salud, cuidado de larga duración y entornos accesibles. Las proyecciones por edad simple convierten estas relaciones generales en insumos territoriales.</p>
<p>El índice de envejecimiento relaciona la población de 65 años o más con la población de 0 a 14 años. Cuando supera 100, las personas mayores son más numerosas que los menores. La relación de dependencia, por su parte, compara los grupos 0–14 y 65 o más con la población de 15–64; es una aproximación demográfica y no una medida directa de dependencia económica.</p>
"""),

5: dict(tipo_bloque='formula', contenido="""
<h3 style="text-align:left">5.1. TOPALS para fecundidad y mortalidad</h3>
<p style="text-align:left">TOPALS —<em>Tool for Projecting Age Patterns using Linear Splines</em>— es un modelo relacional para suavizar y proyectar perfiles por edad. Su punto de partida es una curva estándar y un conjunto reducido de nodos que representan desviaciones locales; entre nodos, las desviaciones se interpolan mediante splines lineales. Para fecundidad expresa las tasas específicas por edad como transformación de una pauta estándar y una función de ajuste (de Beer, 2011); para mortalidad representa la relación entre probabilidades locales de muerte y un patrón estándar (de Beer, 2012). En pequeñas áreas puede integrarse con regresión de Poisson (Gonzaga y Schmertmann, 2016; Schmertmann y Gonzaga, 2018). Su función en este ejercicio es auxiliar: proporciona patrones consistentes para el área mayor.</p>
<p>\\[ \\log m(x) \\;=\\; \\log m^{*}(x) \\;+\\; \\sum_{i} \\alpha_i\\, B_i(x) \\]</p>
<p style="text-align:left">donde \\(m(x)\\) es la tasa o probabilidad estimada a la edad \\(x\\), \\(m^{*}(x)\\) el patrón estándar, \\(B_i(x)\\) las bases spline y \\(\\alpha_i\\) los parámetros que capturan las desviaciones locales. La reducción del número de nodos controla el equilibrio entre ajuste y suavidad.</p>

<h3 style="text-align:left">5.2. Relación de cohortes de Duchesne</h3>
<p style="text-align:left">El método de Duchesne (1988) proyecta poblaciones por sexo y edad en áreas intermedias y menores cuando existe una proyección del área mayor. Sea \\(P_{i,x,t}\\) la población de la comuna \\(i\\) en el grupo de edad \\(x\\) en el año \\(t\\). Para amplitud quinquenal, la relación de crecimiento de cohorte se expresa como:</p>
<p>\\[ RCC_{i,x} \\;=\\; \\frac{P_{i,x+5,\\,t+5}}{P_{i,x,t}} \\]</p>
<p style="text-align:left">El factor diferencial \\(K\\) compara esa relación con la de la misma cohorte en el área mayor (\\(RCC_M\\)):</p>
<p>\\[ K_{i,x} \\;=\\; \\frac{RCC_{i,x}}{RCC_{M,x}} \\]</p>
<p style="text-align:left">Un valor cercano a uno sugiere comportamiento similar al área mayor; valores superiores o inferiores reflejan atracción, expulsión o supervivencia diferencial, además de posibles problemas de medición. La proyección preliminar multiplica la relación del área mayor por el factor estabilizado \\(\\tilde{K}\\):</p>
<p>\\[ \\hat{P}_{i,x+5,\\,t+5} \\;=\\; P_{i,x,t} \\times RCC_{M,x} \\times \\tilde{K}_{i,x} \\]</p>

<h3 style="text-align:left">5.3. Coeficiente del área mayor</h3>
<p style="text-align:left">El coeficiente de crecimiento del área mayor resume la evolución de cada cohorte de Cali entre dos momentos e incorpora la supervivencia esperada y la migración neta del conjunto urbano. Su calidad es decisiva porque funciona como ancla para las 22 comunas: un error en la senda superior se distribuye territorialmente aunque los factores locales estén bien estimados. Para el grupo abierto 80+ se aplica un tratamiento específico que considera sobrevivientes de 75–79 y permanencia dentro del grupo.</p>

<h3 style="text-align:left">5.4. Índice diferencial para mayores de cinco años</h3>
<p style="text-align:left">Los índices se calculan por sexo y grupo de edad y comparan el crecimiento de cada cohorte comunal con el de la misma cohorte en el área mayor, separando el movimiento general de la ciudad del comportamiento territorial específico. Antes del ajuste se revisan valores faltantes, denominadores cero y razones atípicas, contrastándolos con edades vecinas, comunas semejantes y totales censales: un valor extremo no se trunca mecánicamente porque podría representar un cambio territorial real.</p>

<h3 style="text-align:left">5.5. Índice diferencial para menores de cinco años</h3>
<p style="text-align:left">La población 0–4 se estima desde los nacimientos esperados y la supervivencia infantil. El indicador básico es la relación niños–mujeres: población 0–4 sobre población femenina 15–49. El índice diferencial de fecundidad compara esa relación en cada comuna con la del área mayor:</p>
<p>\\[ IDF_{i} \\;=\\; \\frac{P_{i,0-4} \\,/\\, M_{i,15-49}}{P_{M,0-4} \\,/\\, M_{M,15-49}} \\]</p>
<p style="text-align:left">Los nacimientos del área mayor se distribuyen entre comunas mediante el IDF y la exposición de mujeres; luego se aplican supervivencia infantil y razón de masculinidad al nacer, y el resultado se concilia con el total del área mayor para 0–4.</p>

<h3 style="text-align:left">5.6. Ajuste bayesiano empírico</h3>
<p style="text-align:left">El estimador combina el factor observado de cada comuna con el valor de referencia del área mayor mediante un peso dependiente de la confiabilidad:</p>
<p>\\[ \\tilde{K}_{i,x} \\;=\\; c_{i,x}\\, K_{i,x} \\;+\\; (1-c_{i,x})\\, \\bar{K}_{x}, \\qquad 0 \\le c_{i,x} \\le 1 \\]</p>
<p style="text-align:left">Si la varianza muestral es pequeña, \\(c\\) se acerca a uno y el ajuste es reducido; si es grande, aumenta la contracción hacia el patrón común. Freire et al. (2020) documentan su utilidad para pequeñas áreas en Brasil. La contracción mejora la estabilidad, aunque puede reducir diferencias reales si se aplica con excesiva intensidad.</p>

<h3 style="text-align:left">5.7. Conciliación y edades simples</h3>
<p style="text-align:left">La conciliación garantiza que la suma de las 22 comunas reproduzca el control del área mayor para cada año, sexo y edad. Sea \\(S_{x,s,t}\\) la suma preliminar comunal y \\(PM_{x,s,t}\\) el total de Cali; el factor de ajuste y el resultado conciliado son:</p>
<p>\\[ A_{x,s,t} \\;=\\; \\frac{PM_{x,s,t}}{\\sum_i \\hat{P}_{i,x,s,t}} \\qquad\\qquad P^{c}_{i,x,s,t} \\;=\\; A_{x,s,t} \\times \\hat{P}_{i,x,s,t} \\]</p>
<p style="text-align:left">Si el ajuste requerido es grande, no debe aceptarse automáticamente: puede revelar errores en \\(K\\), en la codificación de edades o en el control superior. La conciliación es un cierre contable, no un mecanismo para ocultar problemas del modelo. Las estimaciones quinquenales se desagregan a edades simples por estructura de referencia, interpolación o splines, y el redondeo a personas enteras debe preservar los controles.</p>
"""),

6: dict(contenido="""
<h3>6.1. Fuentes de información</h3>
<p>La población base histórica proviene del Censo General 2005 y del Censo Nacional de Población y Vivienda 2018, desagregados por comuna, sexo y edad. Estos censos permiten calcular relaciones intercensales y evaluar la estructura inicial; las bases deben armonizarse a una geografía común antes de estimar cambios. El control del área mayor corresponde a las proyecciones y estimaciones demográficas del DANE actualizadas después de la pandemia, conservando versión, fecha de descarga y definición geográfica.</p>
<p>Los insumos de fecundidad incluyen hijos nacidos vivos, hijos nacidos durante el último año y mujeres por edad de los censos, así como nacimientos de Estadísticas Vitales clasificados por edad y residencia de la madre. Los insumos de mortalidad incluyen defunciones por sexo, edad y residencia habitual, junto con poblaciones expuestas; las tasas observadas se evalúan por cobertura, omisión y fluctuación temporal.</p>
<p>El archivo de salida analizado contiene una hoja por año entre 2019 y 2030, 22 comunas, dos sexos y edades simples hasta el grupo abierto de 80 o más, con valores enteros y decimales previos al redondeo.</p>
""" + TABLA_FUENTES + """
<h3>6.2. Preparación de los datos</h3>
<p>La preparación comienza con un diccionario único de variables y categorías: códigos de comuna estables, codificación inequívoca de sexo y edades en años cumplidos; los registros con edad desconocida se redistribuyen mediante una regla documentada. La armonización geográfica asigna ambas estructuras censales a límites comparables mediante tablas de correspondencia, microdatos georreferenciados o ponderadores.</p>
<p>Los controles iniciales incluyen duplicados, valores negativos, edades fuera de rango, celdas vacías y discrepancias entre sumas. Para cada año se verifica que hombres más mujeres sea igual al total, que las edades simples reproduzcan los grupos quinquenales y que la suma de comunas coincida con el agregado urbano. Los nacimientos y defunciones se organizan por residencia, no por lugar de ocurrencia.</p>
<p>Una vez depurados, los insumos se transforman al formato requerido por la herramienta R-Cohortes o por el código equivalente. La automatización genera bitácoras de filas leídas, registros excluidos, ajustes aplicados y totales antes y después de cada fase: trazabilidad que permite reproducir y auditar el ejercicio.</p>
<h3>6.3. Flujo operativo</h3>
<ol>
<li>Definir la geografía urbana de 22 comunas y construir correspondencias 2005–2018.</li>
<li>Preparar estructuras censales por comuna, sexo y edad; evaluar calidad y omisión.</li>
<li>Preparar nacimientos, defunciones y exposiciones del área mayor.</li>
<li>Suavizar y proyectar patrones de fecundidad y mortalidad mediante TOPALS.</li>
<li>Calcular relaciones de crecimiento de cohortes del área mayor y de cada comuna.</li>
<li>Obtener factores diferenciales K e índices de fecundidad para 0–4 años.</li>
<li>Aplicar contracción bayesiana empírica y revisar valores extremos.</li>
<li>Proyectar cohortes y nuevas generaciones por sexo y edad.</li>
<li>Conciliar cada año, sexo y edad con el control del área mayor.</li>
<li>Desagregar a edades simples, redondear preservando totales y generar salidas.</li>
<li>Ejecutar controles estructurales y producir indicadores territoriales.</li>
<li>Documentar versión, responsables, supuestos, incidencias y aprobación técnica.</li>
</ol>
<p>El flujo no es una cadena irreversible: los diagnósticos de una etapa pueden obligar a regresar a la preparación o a recalibrar la suavización. La implementación separa datos originales, transformados, parámetros y salidas, y cada ejecución recibe un identificador de versión. Para Cali se recomienda una matriz de control de 12 años × 22 comunas × 2 sexos × 81 posiciones de edad, con totales paralelos de decimales y enteros.</p>
<p>La colaboración interdisciplinaria interviene en puntos definidos: demografía valida métodos y componentes; estadística revisa estimación e incertidumbre; sistemas garantiza reproducibilidad; planeación interpreta transformaciones urbanas; y los equipos sectoriales evalúan plausibilidad frente a registros administrativos. La decisión final queda consignada en acta técnica.</p>
"""),

7: dict(contenido="""
<h3>7.1. Controles de consistencia</h3>
<p><strong>Completitud.</strong> Cada año debe contener exactamente las 22 comunas, ambos sexos y todas las edades previstas. En el libro utilizado, cada hoja anual contiene 1.782 filas, consistentes con 22 comunas por 81 edades; los dos sexos se encuentran en columnas separadas. La ausencia o duplicación de una combinación invalida los agregados.</p>
<p><strong>Coherencia aritmética.</strong> Para cada comuna y edad, la suma de hombres y mujeres debe coincidir con el total calculado; las edades deben reproducir los grupos quinquenales y las comunas deben reproducir el área mayor. Las columnas decimales permiten diferenciar errores de redondeo de errores sustantivos.</p>
<p><strong>Longitudinalidad.</strong> Se examinan variaciones interanuales, continuidad de cohortes y cambios en las edades modales. Una cohorte amplia debe desplazarse progresivamente a edades mayores, salvo que exista un saldo migratorio considerable. Saltos aislados de una edad a otra suelen indicar problemas de desagregación o codificación.</p>
<p><strong>Indicadores demográficos.</strong> Participación infantil, población mayor, dependencia y relación de masculinidad. Valores extremos pueden ser reales, pero requieren explicación territorial y contraste externo; en particular, estructuras muy concentradas en edades avanzadas o relaciones de masculinidad superiores a 120 deben revisarse con detalle.</p>
<p><strong>Contraste externo.</strong> Matrícula, afiliación a salud, nacimientos, defunciones, registros de servicios y actividad edificadora como señales auxiliares. La validación no exige igualdad exacta, sino coherencia de orden de magnitud, dirección y distribución espacial.</p>
<h3>7.2. Incertidumbre y escenarios</h3>
<p>Las proyecciones de pequeñas áreas acumulan incertidumbre de la población base, los componentes demográficos, la redistribución territorial y los supuestos de continuidad. La restricción al área mayor elimina inconsistencias aditivas, pero no elimina la incertidumbre sobre cómo se distribuirá la población entre comunas. Esta diferencia debe comunicarse de manera explícita.</p>
<p>La contracción bayesiana trata la incertidumbre de los factores locales al reducir el peso de valores poco precisos. Sin embargo, el archivo final presenta una única trayectoria y no contiene intervalos; en consecuencia, las cifras deben evitar una apariencia de exactitud excesiva, aun cuando se publiquen como personas enteras.</p>
<p>Una mejora futura consiste en producir escenarios bajo, medio y alto asociados con fecundidad, mortalidad y, principalmente, redistribución residencial. Los escenarios no deben construirse como porcentajes arbitrarios alrededor del resultado central; deben corresponder a supuestos demográficos y urbanos explícitos, como ritmos de construcción de vivienda o convergencia de factores K.</p>
<p>Otra opción es el <em>backtesting</em>: proyectar desde un año histórico hacia un censo o padrón conocido y calcular errores absolutos y relativos por comuna, sexo y edad. Brito et al. (2010) y Wilson et al. (2022) enfatizan la importancia de evaluar precisión en lugar de elegir métodos solo por complejidad.</p>
<p>La comunicación de incertidumbre debe acompañar los usos. Para decisiones robustas se recomienda trabajar con rangos y tendencias —crecimiento, estabilidad, envejecimiento— antes que con diferencias pequeñas entre cifras puntuales. Las proyecciones son más útiles cuando apoyan decisiones adaptables y sujetas a actualización periódica.</p>
"""),

# 8: grafico_indicador → solo cambia el indicador vinculado (sin contenido de texto)
8: dict(indicador=IND_SEXO),

# 9: tabla dinámica → indicador de comuna (264 filas, lectura territorial clara)
9: dict(indicador=IND_COMUNA),

10: dict(contenido="""
<h3>9.1. Usos de planeación</h3>
<p><strong>Educación.</strong> La base permite estimar poblaciones en edades asociadas con primera infancia, primaria, secundaria y educación media. La proyección no equivale a matrícula porque intervienen asistencia, cobertura, sector público/privado y movilidad escolar entre comunas. Su uso adecuado consiste en combinar denominadores demográficos con registros de estudiantes y capacidad instalada.</p>
<p><strong>Salud.</strong> Las edades simples permiten construir denominadores para tasas, anticipar demanda materno-infantil y dimensionar servicios para enfermedades crónicas y personas mayores. Las comunas con envejecimiento avanzado requieren fortalecer atención domiciliaria, rehabilitación y prevención de dependencia. Los resultados deben contrastarse con afiliación y residencia efectiva de usuarios.</p>
<p><strong>Cuidado y protección social.</strong> El crecimiento relativo de 65 años o más orienta redes de cuidado, apoyos a cuidadores y accesibilidad. Al mismo tiempo, las comunas jóvenes mantienen demanda de cuidado infantil y programas juveniles. La sustitución de dependencia infantil por dependencia en edades mayores implica reconfigurar servicios, no simplemente reducirlos.</p>
<p><strong>Planeación urbana.</strong> Las diferencias entre comunas pueden relacionarse con vivienda, renovación, movilidad y localización de equipamientos. Las proyecciones sirven para explorar capacidad futura, pero no sustituyen escenarios de desarrollo urbano. Todo proyecto de vivienda de gran escala debe incorporarse como supuesto adicional y someterse a pruebas de sensibilidad.</p>
<p><strong>Seguimiento de políticas.</strong> La serie ofrece denominadores comparables por año, sexo y edad. Para preservar esa función, las actualizaciones no deben sobrescribir versiones anteriores; deben publicarse con metadatos y notas de revisión. Las rupturas metodológicas deben cuantificarse para distinguir cambio poblacional de cambio de método.</p>
"""),

11: dict(titulo='Recomendaciones técnicas y gobernanza', contenido="""
<h3>9.2. Recomendaciones técnicas</h3>
<p><strong>1. Versión maestra del control del área mayor.</strong> Formalizar una versión maestra del control y registrar su correspondencia con las 22 comunas. La cobertura debe declararse como urbana y diferenciarse del total municipal. Cualquier actualización del DANE debe activar una evaluación de impacto y no reemplazarse de manera silenciosa.</p>
<p><strong>2. Backtesting.</strong> Realizar pruebas retrospectivas con estructuras históricas y calcular errores por comuna y edad. Los resultados permitirán comparar el método de Duchesne con alternativas como Hamilton–Perry, extrapolación de participaciones o promedios de modelos. La selección futura debería basarse en precisión observada y no solo en continuidad institucional.</p>
<p><strong>3. Revisión prioritaria de comunas extremas.</strong> Revisar comunas con estructuras extremas en 2030 —especialmente 2, 3, 9, 19 y 21— así como relaciones de masculinidad fuera del rango histórico. La revisión debe contrastar cohortes, población institucional, proyectos de vivienda y posibles efectos del ajuste bayesiano. Confirmar un valor extremo es tan importante como corregirlo.</p>
<p><strong>4. Intervalos y escenarios.</strong> Desarrollar intervalos o escenarios mediante simulación de factores K, variación de tendencias migratorias o combinación de modelos. Los intervalos deben preservarse durante la conciliación, evitando presentar únicamente un margen uniforme alrededor del total.</p>
<p><strong>5. Gobernanza de la serie.</strong> Institucionalizar un protocolo de actualización bienal o posterior a eventos demográficos relevantes, con responsables, calendario, fuentes, código versionado, revisión por pares y aprobación. La sostenibilidad de la serie depende más de esta gobernanza que de una ejecución aislada.</p>
"""),

12: dict(contenido="""
<p>El ejercicio proporciona una serie coherente de población por sexo y edad simple para las 22 comunas de Santiago de Cali durante 2019–2030. La combinación de relación de cohortes, patrones TOPALS, contracción bayesiana y conciliación al área mayor es adecuada para enfrentar la escasez e inestabilidad de información de pequeñas áreas. Su principal fortaleza es integrar heterogeneidad local y coherencia urbana.</p>
<p>Los resultados agregados muestran una ciudad prácticamente estable en volumen entre 2019 y 2030, pero con un máximo en 2022 y descenso posterior. Esa estabilidad esconde una transformación etaria sustantiva: disminuye la población infantil y aumenta la participación de personas mayores hasta superar, en el agregado, la cantidad de menores de 15 años. <strong>El cambio estructural es más relevante para la política pública que la pequeña variación del total.</strong></p>
<p>Las trayectorias comunales son divergentes. Siete comunas crecen y quince disminuyen, mientras los perfiles de edad oscilan entre estructuras jóvenes y envejecimiento avanzado. La distribución espacial de estas transformaciones exige políticas diferenciadas y cuestiona el uso de promedios municipales como único criterio de asignación.</p>
<p>El documento también identifica límites que deben acompañar la difusión: cobertura exclusivamente urbana, grupo abierto en 80 años o más, ausencia de intervalos y sensibilidad a supuestos de redistribución residencial. Las proyecciones son experimentales y no deben presentarse como cifras oficiales sin validación y adopción institucional. El uso responsable requiere conservar esta nota en todos los productos derivados.</p>
<p>La actualización futura debe priorizar pruebas retrospectivas, escenarios de migración intraurbana, integración con vivienda y revisión de comunas extremas. Con estas mejoras, la base puede convertirse en un sistema permanente de información demográfica para apoyar decisiones territoriales, sectoriales y presupuestales de Santiago de Cali.</p>
"""),

13: dict(tipo_bloque='texto', contenido="""
<p>Lista de referencias en formato APA empleadas por el documento metodológico y el ejercicio de proyección:</p>
""" + REFERENCIAS),

14: dict(tipo_bloque='texto', contenido="""
<h3>Anexo A. Diccionario de salida</h3>
""" + TABLA_DICCIONARIO + """
<h3>Anexo B. Indicadores</h3>
<ul>
<li><strong>Proporción infantil</strong> = población de 0 a 14 años / población total × 100.</li>
<li><strong>Proporción de personas mayores</strong> = población de 65 años o más / población total × 100.</li>
<li><strong>Índice de envejecimiento</strong> = población de 65 años o más / población de 0 a 14 años × 100.</li>
<li><strong>Relación de dependencia total</strong> = (población 0–14 + población 65 o más) / población 15–64 × 100.</li>
<li><strong>Relación de masculinidad</strong> = población masculina / población femenina × 100.</li>
<li><strong>Cambio relativo 2019–2030</strong> = (población 2030 − población 2019) / población 2019 × 100.</li>
</ul>
<p>Los indicadores son descriptivos y dependen de las convenciones de edad adoptadas. No representan por sí mismos relaciones económicas, necesidades efectivas ni causalidad territorial. Su interpretación debe combinarse con registros sectoriales y conocimiento de las comunas.</p>
<h3>Anexo C. Integración SIIED</h3>
""" + TABLA_SIIED + """
<p><em>Documento asociado: <code>Paper_Academico_Proyecciones_Comunas_Cali_2019-2030.md</code> (forma paper completo) y <code>Ficha_Producto_Estadistico_Proyecciones_Comunas_Cali_2019-2030.md</code> (forma ficha de producto), ambos en la carpeta documento academico del repositorio.</em></p>
"""),
}

print('Actualizando secciones de', P.titulo[:60], '...')
n = 0
for orden, cfg in CONTENIDO.items():
    s = SeccionPaper.objects.get(producto=P, numero_orden=orden)
    changed = []
    if 'titulo' in cfg and s.titulo != cfg['titulo']:
        s.titulo = cfg['titulo']; changed.append('titulo')
    if 'tipo_bloque' in cfg and s.tipo_bloque != cfg['tipo_bloque']:
        s.tipo_bloque = cfg['tipo_bloque']; changed.append('tipo_bloque')
    if 'indicador' in cfg and s.indicador_vinculado_id != cfg['indicador'].id:
        s.indicador_vinculado = cfg['indicador']; changed.append('indicador')
    if 'contenido' in cfg and s.contenido != cfg['contenido'].strip():
        s.contenido = cfg['contenido'].strip(); changed.append('contenido(%d chars)' % len(cfg['contenido'].strip()))
    if changed:
        s.save(); n += 1
        print('  [%2d] %-45s → %s' % (orden, s.titulo[:42], ', '.join(changed)))
print('secciones actualizadas:', n, '/ 15')
