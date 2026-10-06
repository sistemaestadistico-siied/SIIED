**ALCALDÍA DE SANTIAGO DE CALI**

**DEPARTAMENTO ADMINISTRATIVO DE PLANEACIÓN**

**SUBDIRECCIÓN DE DESARROLLO INTEGRAL**

**PLAN DE PRUEBAS**

**ADAPTACIÓN DEL FORMULARIO DEL ÍNDICE DE CAPACIDAD**  
**ESTADÍSTICA DISTRITAL (FICED) EN LA PLATAFORMA DEL**  
**SISTEMA INTEGRADO DE INFORMACIÓN ESTADÍSTICA DISTRITAL (SIIED)**

*Documento de diseño y planificación de las pruebas*

**No contiene resultados de ejecución**

**Santiago de Cali, Agosto 2026**

Versión 1.1

## **Control documental** {#control-documental}

| Campo | Descripción |
| :---- | :---- |
| **Nombre del documento** | Plan de pruebas para la adaptación del FICED en la plataforma SIIED |
| **Código documental** | Pendiente de asignación por el Sistema Integrado de Gestión |
| **Versión** | 1.1 |
| **Estado** | Formulado para revisión y aprobación |
| **Responsable metodológico** | Equipo responsable de la operación estadística ICED |
| **Responsable técnico** | Equipo de desarrollo y administración de la plataforma SIIED |
| **Fecha de elaboración** | 2026 |
| **Periodo de aplicación** | Vigencia definida para la puesta en producción del FICED  |

## **Historial de cambios** {#historial-de-cambios}

| Versión | Fecha | Descripción del cambio | Responsable |
| :---- | :---- | :---- | :---- |
| 1.0 | 2026 | Formulación inicial del plan de pruebas del instrumento de captura FICED v2 y sus componentes asociados. | Equipo ICED-SIIED |
| 1.1 | 2026 | Actualización de la línea base conforme al estado real del desarrollo: el motor de medición se encuentra implementado y su ciclo de prueba queda condicionado a la aprobación metodológica de las reglas; alineación de las salidas con la exportación real (CSV consolidado); incorporación del protocolo de casos patrón mediante doble corrida Excel↔web; registro de inconsistencias conocidas del código como riesgos e hallazgos anticipados; precisiones sobre matriz de requisitos, tratamiento de "no aplica", reproducibilidad y selección de organismos para la prueba piloto. | Equipo ICED-SIIED |

## **Revisión y aprobación[^1]** {#revisión-y-aprobación}

| Rol | Nombre / cargo | Concepto | Firma / fecha |
| :---- | :---- | :---- | :---- |
| Elaboró | Equipo técnico y metodológico ICED-SIIED | Pendiente de diligenciamiento |  |
| Revisó \- componente metodológico | Responsable de la operación estadística ICED | Pendiente de diligenciamiento |  |
| Revisó \- componente tecnológico | Responsable técnico de la plataforma SIIED | Pendiente de diligenciamiento |  |
| Aprobó | Instancia definida para autorizar la ejecución del plan | Pendiente de diligenciamiento |  |

**Tabla de contenido**

**[Control documental	2](#control-documental)**

[**Historial de cambios	2**](#historial-de-cambios)

[**Revisión y aprobación	4**](#revisión-y-aprobación)

[**Siglas y abreviaturas	7**](#siglas-y-abreviaturas)

[**1\. Introducción	8**](#1.-introducción)

[**2\. Antecedentes	8**](#2.-antecedentes)

[**3\. Naturaleza y propósito del documento	9**](#3.-naturaleza-y-propósito-del-documento)

[**4\. Marco normativo y metodológico	9**](#4.-marco-normativo-y-metodológico)

[**5\. Objetivos	10**](#5.-objetivos)  
[5.1 Objetivo general	10](#5.1-objetivo-general)  
[5.2 Objetivos específicos	10](#5.2-objetivos-específicos)

[**6\. Alcance y exclusiones	11**](#6.-alcance-y-exclusiones)  
[6.1 Alcance	11](#6.1-alcance)  
[6.2 Exclusiones	11](#6.2-exclusiones)

[**7\. Línea base y objeto de prueba	12**](#7.-línea-base-y-objeto-de-prueba)  
[7.1 Documentos de referencia	12](#7.1-documentos-de-referencia)  
[7.2 Configuración prevista del objeto de prueba	12](#heading)  
[7.3 Ficha de versión requerida antes de ejecutar	13](#heading-1)  
[7.4 Incidencias conocidas del objeto de prueba (hallazgos anticipados)	14](#heading-2)

[**8\. Estrategia general de pruebas	15**](#heading-3)  
[8.1 Ciclos de prueba	16](#8.1-ciclos-de-prueba)  
[8.2 Enfoque basado en riesgo	17](#.)  
[8.3 Principios de ejecución	17](#8.3-principios-de-ejecución)

[**9\. Tipos de prueba previstos	17**](#9.-tipos-de-prueba-previstos)

[**10\. Metodología de ejecución	20**](#10.-metodología-de-ejecución)  
[10.1 Preparación	20](#10.1-preparación)  
[10.2 Ejecución de casos	20](#10.2-ejecución-de-casos)  
[10.3 Revisión y nueva prueba	20](#10.3-revisión-y-nueva-prueba)  
[10.4 Metodología específica para pruebas cognitivas y de usabilidad	20](#10.4-metodología-específica-para-pruebas-cognitivas-y-de-usabilidad)  
[10.5 Metodología de la prueba piloto	20](#10.5-metodología-de-la-prueba-piloto)  
[10.6 Metodología de validación del motor de medición	21](#10.6-metodología-de-validación-del-motor-de-medición)

[**11\. Ambiente, datos y recursos	21**](#11.-ambiente,-datos-y-recursos)  
[11.1 Ambiente	21](#11.1-ambiente)  
[11.2 Datos de prueba	22](#heading-4)  
[11.3 Recursos	22](#11.3-recursos)

[**12\. Organización, roles y responsabilidades	23**](#12.-organización,-roles-y-responsabilidades)

[**13\. Criterios de entrada, suspensión, reanudación y cierre	23**](#heading-5)  
[13.1 Criterios de entrada	23](#13.1-criterios-de-entrada)  
[13.2 Criterios de suspensión	24](#13.2-criterios-de-suspensión)  
[13.3 Criterios de reanudación	24](#13.3-criterios-de-reanudación)  
[13.4 Criterios de cierre	24](#13.4-criterios-de-cierre)

[**14\. Gestión de hallazgos y no conformidades	25**](#14.-gestión-de-hallazgos-y-no-conformidades)

[**15\. Trazabilidad y evidencias	25**](#15.-trazabilidad-y-evidencias)

[**16\. Riesgos del plan de pruebas	26**](#16.-riesgos-del-plan-de-pruebas)

[**17\. Cronograma de referencia	28**](#17.-cronograma-de-referencia)

[**18\. Productos esperados	29**](#18.-productos-esperados)

[**19\. Mecanismo de aprobación	30**](#19.-mecanismo-de-aprobación)

[**20\. Referencias	30**](#20.-referencias)

[**ANEXO A. Matriz de trazabilidad normativa y funcional	1**](#anexo-a.-matriz-de-trazabilidad-normativa-y-funcional)

[**ANEXO B. Inventario inicial de casos de prueba	3**](#anexo-b.-inventario-inicial-de-casos-de-prueba)

[**ANEXO C. Formato de caso de prueba	17**](#anexo-c.-formato-de-caso-de-prueba)

[**ANEXO D. Formato de observación	18**](#anexo-d.-formato-de-observación)

[**ANEXO E. Formato de registro de hallazgos	19**](#anexo-e.-formato-de-registro-de-hallazgos)

[**ANEXO F. Estructura del informe de resultados	21**](#anexo-f.-estructura-del-informe-de-resultados)

[**ANEXO G. Protocolo de casos patrón — doble corrida excel↔web	22**](#anexo-g.-protocolo-de-casos-patrón-—-doble-corrida-excel↔web)  
[G.1 Propósito	22](#g.1-propósito)  
[G.2 Insumos	22](#g.2-insumos)  
[G.3 Conjunto mínimo de casos patrón	23](#g.3-conjunto-mínimo-de-casos-patrón)  
[G.4 Procedimiento	23](#g.4-procedimiento)  
[G.5 Matriz comparativa (formato)	24](#g.5-matriz-comparativa-\(formato\))  
[G.6 Criterio de aceptación	24](#g.6-criterio-de-aceptación)

## **Siglas y abreviaturas** {#siglas-y-abreviaturas}

| Sigla | Definición |
| :---- | :---- |
| CSV | Valores separados por comas (formato de exportación de datos) |
| DANE | Departamento Administrativo Nacional de Estadística |
| FICED | Formulario del Índice de Capacidad Estadística Distrital |
| ICED | Índice de Capacidad Estadística Distrital |
| NTC PE 1000 | Norma Técnica de la Calidad del Proceso Estadístico |
| QA | Aseguramiento de la calidad del software |
| SEN | Sistema Estadístico Nacional |
| SIIED | Sistema Integrado de Información Estadística Distrital |
| UAT | Pruebas de aceptación de usuario |

## **1\. Introducción** {#1.-introducción}

El presente Plan de Pruebas define la estrategia, los métodos, los responsables, los recursos, los criterios y los productos necesarios para verificar la adaptación del Formulario del Índice de Capacidad Estadística Distrital (FICED) en la plataforma del Sistema Integrado de Información Estadística Distrital (SIIED).

El documento se formula como parte de la fase de diseño del proceso estadístico y orienta la ejecución posterior de las pruebas durante la fase de construcción. En consecuencia, establece qué se probará, cómo se realizará la prueba, quiénes intervendrán, cuáles serán los resultados esperados y qué evidencias deberán conservarse, sin presentar resultados de ejecución.

La formulación se sustenta en la NTC PE 1000:2020, los Lineamientos para el proceso estadístico en el Sistema Estadístico Nacional y la Guía para la definición y la aplicación de pruebas en las operaciones estadísticas del DANE. Estos referentes requieren que las pruebas mantengan trazabilidad sobre las actividades, los métodos, los instrumentos y el software aplicativo, y que sus resultados y conclusiones queden documentados.

## **2\. Antecedentes** {#2.-antecedentes}

El ICED es la operación estadística mediante la cual se evalúa la capacidad estadística de los organismos de la Alcaldía de Santiago de Cali. Su instrumento de recolección fue inicialmente desarrollado en Microsoft Excel y aplicado mediante diligenciamiento asistido, con procesamiento manual apoyado en código. La adaptación al SIIED busca disponer de un instrumento electrónico que facilite la captura, el guardado, la validación, la administración y el procesamiento de la información.

La versión web del FICED se encuentra estructurada como formulario tipo wizard, con 42 preguntas principales (P1-P42) organizadas en cinco módulos temáticos (A-E) y distribuidas en diez pasos de navegación. La verificación directa del código fuente de la plataforma confirma que, a la fecha de formulación de esta versión del plan, se encuentran implementados:

- El formulario wizard de diez pasos con persistencia progresiva por módulo (campos JSON `respuestas_a` a `respuestas_e`) y guardado parcial.

- El flujo de estados: borrador, enviado, validado y devuelto para corrección, con restricción de unicidad organismo-periodo.

- Las tablas auxiliares de personas de contacto (Módulo A) y recurso humano (P19), materializadas desde las respuestas del formulario.

- El panel de validación para el equipo técnico SIIED (revisión, cálculo y decisión sobre formularios).

- El motor automatizado de medición, que calcula 36 indicadores individuales, 9 subdimensiones, 4 dimensiones y el puntaje global con ponderación 25% por dimensión, junto con la clasificación por nivel de capacidad.

- La exportación consolidada en formato CSV por periodo, con encabezados que incluyen puntaje global, dimensiones, subdimensiones e indicadores individuales.

En consecuencia, a diferencia de lo reportado en el informe de avance de abril de 2026, el motor de medición no es un desarrollo pendiente sino un desarrollo implementado cuyas reglas están pendientes de aprobación metodológica formal. El Ciclo 5 de este plan queda condicionado exclusivamente a dicha aprobación y a la disponibilidad de los casos patrón definidos en el Anexo G.

Para la ejecución del presente plan deberá emitirse un acta o ficha de versión que identifique el formulario, el ambiente y los componentes tecnológicos que serán sometidos a prueba, incluyendo el identificador de versión del código (commit o etiqueta). Cualquier modificación posterior activará pruebas de regresión sobre los componentes afectados.

## **3\. Naturaleza y propósito del documento** {#3.-naturaleza-y-propósito-del-documento}

Este documento constituye el soporte de que la operación estadística diseñó y planificó las pruebas aplicables al nuevo formulario. No equivale al informe de ejecución de pruebas ni acredita por sí solo que el aplicativo fue aprobado para producción.

La documentación completa del ciclo de pruebas estará conformada por:

- Plan de Pruebas aprobado (este documento).

- Matriz de requisitos y trazabilidad.

- Casos de prueba diligenciados y evidencias.

- Casos patrón de doble corrida Excel↔web (Anexo G).

- Registros de hallazgos, incidencias y acciones correctivas.

- Informes de observación de pruebas cognitivas, de usabilidad y piloto.

- Informe final de resultados, conclusiones y recomendaciones.

- Acta o mecanismo de aprobación para la puesta en producción.

## **4\. Marco normativo y metodológico** {#4.-marco-normativo-y-metodológico}

| Referente | Aplicación en el Plan de Pruebas |
| :---- | :---- |
| NTC PE 1000:2020, numeral 7.7 | Establece la ejecución y documentación de pruebas a lo diseñado. |
| NTC PE 1000:2020, numeral 7.7.1 | Exige un plan que permita identificar afectaciones, mantener trazabilidad, documentar resultados y conclusiones, y conservar evidencias. |
| NTC PE 1000:2020, numerales 7.3.1 y 7.3.3 | Orienta la comprobación de reglas de validación y consistencia, y la documentación de manuales de uso y mantenimiento del software aplicativo. |
| Lineamientos para el proceso estadístico en el SEN, subproceso 3.6 | Orienta las pruebas al sistema de producción, incluidos instrumentos electrónicos, aplicativos, procesamiento y generación de resultados. |
| Lineamientos para el proceso estadístico en el SEN, subprocesos 3.7 a 3.9 | Orienta la prueba piloto, la evaluación del diseño y la construcción, y el mecanismo de aprobación para la puesta en producción. |
| Guía para la definición y la aplicación de pruebas, DANE, 2020, capítulo 5 | Define que el plan debe incluir elementos a probar, objetivos, alcance, metodología, recursos, cronograma, productos y perfiles del equipo. |

## **5\. Objetivos** {#5.-objetivos}

### 5.1 Objetivo general {#5.1-objetivo-general}

Definir la estrategia para verificar que la adaptación del FICED en la plataforma SIIED corresponda al diseño metodológico aprobado, aplique correctamente las reglas funcionales y de validación, preserve la integridad de los datos, garantice la equivalencia de resultados con el instrumento Excel de referencia y permita ejecutar de manera controlada el flujo de diligenciamiento, revisión, corrección, cierre y generación de productos.

### 5.2 Objetivos específicos {#5.2-objetivos-específicos}

- Verificar la correspondencia entre el formulario metodológico aprobado y su versión electrónica.

- Comprobar el funcionamiento de la navegación, las preguntas condicionales, las validaciones, las tablas dinámicas y las opciones excluyentes.

- Verificar el guardado, la recuperación, la integridad, la actualización y la persistencia de las respuestas.

- Comprobar los permisos, estados y flujos de administración, envío, validación, devolución y corrección.

- Evaluar la comprensión, usabilidad, accesibilidad y carga de diligenciamiento del formulario.

- Verificar las salidas y exportaciones reales del módulo (exportación CSV consolidada por periodo) y los mecanismos de auditoría definidos.

- Verificar la equivalencia del motor de medición implementado frente a casos patrón generados con el instrumento Excel de referencia, una vez las reglas de cálculo cuenten con aprobación metodológica formal.

- Establecer los criterios de aceptación, los productos, las evidencias y el mecanismo de aprobación para la puesta en producción.

## **6\. Alcance y exclusiones** {#6.-alcance-y-exclusiones}

### 6.1 Alcance {#6.1-alcance}

El plan comprende las pruebas aplicables a los siguientes componentes:

- Instrumento estadístico FICED y su correspondencia conceptual con la versión electrónica.

- Formulario web tipo wizard y sus cinco módulos temáticos.

- Diez pasos de navegación, confirmados en el código fuente y sujetos a ratificación en la ficha de versión.

- Preguntas P1 a P42, subpreguntas, campos de especificación y reglas condicionales.

- Guardado como borrador, guardado parcial, avance entre pasos, recuperación y envío definitivo.

- Flujo de estados: borrador, enviado, validado y devuelto para corrección.

- Almacenamiento por módulos (JSON por módulo A-E), tablas auxiliares de personas de contacto y recurso humano, integridad y auditoría de datos.

- Panel de administración y validación del equipo técnico SIIED.

- Exportación CSV consolidada por periodo, incluyendo la verificación de que ningún formulario quede excluido del consolidado sin registro del motivo.

- Usabilidad, accesibilidad, compatibilidad, seguridad básica, rendimiento y recuperación.

- Motor automatizado de medición (ya implementado), en un ciclo condicionado a la aprobación metodológica de las reglas de cálculo y a la disponibilidad de casos patrón.

- Prueba piloto integral del operativo de diligenciamiento y validación.

### 6.2 Exclusiones {#6.2-exclusiones}

- La ejecución efectiva de los casos de prueba, la cual será documentada en los formatos anexos.

- La certificación de seguridad informática especializada o pruebas de penetración, salvo que sean contratadas o asignadas a un equipo competente.

- La aprobación de la metodología de cálculo del ICED, que corresponde al responsable metodológico.

- Las exportaciones en formatos PDF y Excel, que no forman parte de la versión implementada; si se desarrollan posteriormente, requerirán adición de casos de prueba y regresión.

- La modificación del código fuente durante la prueba; los ajustes serán gestionados por el equipo de desarrollo.

- La publicación de resultados oficiales obtenidos con datos de prueba o con la prueba piloto.

## **7\. Línea base y objeto de prueba** {#7.-línea-base-y-objeto-de-prueba}

### 7.1 Documentos de referencia {#7.1-documentos-de-referencia}

| Documento | Uso en el plan |
| :---- | :---- |
| Ficha metodológica y documento metodológico del ICED | Definición del objetivo, alcance, dimensiones, subdimensiones, preguntas y reglas metodológicas. |
| Formulario ICED vigente (instrumento Excel de referencia) | Línea base del texto de preguntas, opciones, instrucciones, estructura del instrumento y **fuente de los casos patrón de cálculo (Anexo G)**. |
| Informe de Avance \- Módulo ICED (FICED v2), febrero de 2026 | Identificación de componentes técnicos reportados: modelos, estados, persistencia, administración, exportación y propuesta de cálculo. |
| Informe de Avance \- Instrumento de Captura FICED v2, abril de 2026 | Inventario de 42 preguntas, cinco módulos, diez pasos, tipos de respuesta, condicionales y persistencia. Se precisa que el estado del motor reportado en dicho informe fue superado: el motor está implementado. |
| Código fuente de la plataforma SIIED (módulo FICED v2) | Verificación directa del estado real de los componentes: wizard, persistencia, estados, motor de cálculo, exportación CSV y panel de validación. |
| NTC PE 1000:2020, Lineamientos SEN y Guía DANE | Criterios normativos y metodológicos para planificar, ejecutar, documentar y aprobar pruebas. |

###  {#heading}

### 7.2 Configuración prevista del objeto de prueba

| Componente | Configuración prevista para la prueba |
| :---- | :---- |
| **Formulario** | FICED v2, 42 preguntas principales P1-P42. |
| **Módulos** | A. Identificación; B. Entorno institucional; C. Infraestructura; D. Metodología estadística; E. Accesibilidad y uso. |
| **Navegación** | Diez pasos: A, B, C1, C2, C3, D1, D2, D3, D4, E. Confirmados en código; ratificar en ficha de versión. |
| **Persistencia** | Cinco grupos de respuestas por módulo (JSON) y tablas auxiliares de personas de contacto y recurso humano (P19). |
| **Estados** | Borrador, enviado, validado y devuelto para corrección, con unicidad organismo-periodo. |
| **Cálculo** | Motor implementado: 36 indicadores, 9 subdimensiones, 4 dimensiones, ponderación 25% por dimensión, clasificación por nivel. Ciclo de prueba condicionado a la aprobación metodológica de las reglas y a los casos patrón del Anexo G. |
| **Salidas** | Página de confirmación de envío, consulta de resultado detallado y **exportación CSV consolidada por periodo** (puntaje global, 4 dimensiones, 9 subdimensiones y 36 indicadores por organismo). |

###  {#heading-1}

### 7.3 Ficha de versión requerida antes de ejecutar

| Campo | Contenido a diligenciar |
| :---- | :---- |
| Versión funcional del formulario |  |
| Fecha y hora del despliegue |  |
| Ambiente y URL |  |
| Versión del código / commit o etiqueta |  |
| Base de datos de prueba |  |
| Módulos habilitados |  |
| Motor de cálculo habilitado | Sí (implementado; pendiente versión de reglas) |
| Exportaciones habilitadas | CSV consolidado por periodo |
| Responsable de entrega |  |
| Incidencias conocidas | Ver numeral 7.4 |

###  {#heading-2}

### 7.4 Incidencias conocidas del objeto de prueba (hallazgos anticipados)

La verificación de escritorio del código fuente identificó las siguientes situaciones, que deberán registrarse en la ficha de versión y resolverse o dirimirse antes o durante los ciclos correspondientes:

| ID | Descripción | Ciclo / caso afectado | Instancia que dirime |
| :---- | :---- | :---- | :---- |
| IC-01 | Inconsistencia documental de ponderaciones: el modelo de datos y el motor aplican 25% a cada dimensión (B, C, D, E), mientras que la documentación interna del formulario refiere un peso de 20% para el Módulo E. Debe confirmarse la ponderación metodológicamente aprobada. | Ciclo 5 / CP-M03 | Responsable metodológico |
| IC-02 | Doble definición de la regla de clasificación por nivel: existe una regla en el motor de cálculo y otra independiente en el modelo de datos (cortes 0.90 / 0.75 / 0.60). Dos fuentes de verdad para la misma regla constituyen riesgo de divergencia. | Ciclo 5 / CP-M05 | Responsables metodológico y técnico |
| IC-03 | La exportación CSV consolidada omite silenciosamente los formularios que generan error durante el cálculo, sin registro del motivo, lo que puede producir consolidados incompletos sin alerta. | Ciclo 3 / CP-X01, CP-I01 | Responsable técnico |
| IC-04 | Existen trazas de depuración en el código del wizard que vuelcan contenido de respuestas a los registros del servidor, con potencial exposición de información en logs. | Ciclo 3 / CP-S03, CP-X03; riesgo R-09 | Responsable técnico |

##  {#heading-3}

## **8\. Estrategia general de pruebas**

La estrategia combina pruebas del instrumento estadístico, pruebas del aplicativo, la validación de equivalencia del motor de medición frente al instrumento Excel de referencia y una prueba piloto integral. Se aplicará un enfoque incremental, basado en riesgo y con trazabilidad entre cada requisito, el caso de prueba, la evidencia, el hallazgo y la nueva prueba.

### 8.1 Ciclos de prueba {#8.1-ciclos-de-prueba}

| Ciclo | Contenido | Condición de inicio | Producto |
| :---- | :---- | :---- | :---- |
| Ciclo 1\. Revisión documental y de escritorio | Correspondencia del instrumento, estructura, redacción, opciones, reglas, condicionales y ayudas. | Formulario metodológico y versión electrónica identificados. | Lista de chequeo e informe de revisión. |
| Ciclo 2\. Pruebas funcionales del formulario | Módulos, navegación, validaciones, tablas, guardado, recuperación y envío. | Ambiente estable y usuarios de prueba. | Casos de prueba y evidencias. |
| Ciclo 3\. Integración y administración | Estados, roles, validación, devolución, corrección, auditoría, exportación CSV y datos. | Ciclo 2 sin defectos críticos. | Casos de integración y registro de hallazgos. |
| Ciclo 4\. Usabilidad, accesibilidad y compatibilidad | Comprensión, navegación, mensajes, teclado, navegadores y carga de respuesta. | Versión funcional estable. | Informe de observación y recomendaciones. |
| Ciclo 5\. Motor de medición | Puntuación por pregunta, subdimensión, dimensión, resultado global, no aplica, clasificación, redondeo y reproducibilidad, mediante comparación con casos patrón de doble corrida (Anexo G). | Reglas metodológicas aprobadas (incluida resolución de IC-01 e IC-02) y casos patrón disponibles. El motor ya está implementado. | Informe de validación del cálculo. |
| Ciclo 6\. Prueba piloto integral | Simulación del operativo completo con perfiles representativos. | Ciclos previos aprobados y manuales disponibles. | Informe de prueba piloto y recomendación. |
| Ciclo 7\. Regresión y cierre | Repetición de casos afectados por ajustes y verificación final. | Correcciones desplegadas. | Informe final y mecanismo de aprobación. |

### . {#.}

### 8.2 Enfoque basado en riesgo

Tendrán prioridad alta los casos cuya falla pueda ocasionar pérdida de información, alteración del resultado del ICED, acceso no autorizado, imposibilidad de enviar el formulario, incoherencia entre preguntas y datos almacenados, exclusión silenciosa de organismos del consolidado, o generación de resultados no reproducibles.

### 8.3 Principios de ejecución {#8.3-principios-de-ejecución}

- Toda prueba debe tener un requisito y un resultado esperado identificados.

- Los datos de prueba no deben utilizar información personal real innecesaria.

- Cada hallazgo debe incluir evidencia suficiente para su reproducción.

- Los ajustes deben ser sometidos a nueva prueba y, cuando corresponda, a regresión.

- Las pruebas cognitivas y de usabilidad deben observar el comportamiento del usuario sin inducir la respuesta.

- La validación del motor de medición se realizará exclusivamente por comparación contra casos patrón aprobados, generados con el instrumento Excel de referencia congelado (Anexo G).

- La prueba piloto no generará resultados oficiales ni sustituirá la medición anual del ICED.

- La salida a producción solo podrá autorizarse mediante el mecanismo de aprobación definido.

## **9\. Tipos de prueba previstos** {#9.-tipos-de-prueba-previstos}

| Código | Tipo | Objeto | Propósito |
| :---- | :---- | :---- | :---- |
| PT-01 | Prueba de escritorio | Instrumento y documentación | Revisar coherencia temática, estructura, redacción, opciones, universos, periodos y reglas. |
| PT-02 | Grupo de expertos | Instrumento y reglas | Validar pertinencia conceptual, suficiencia y consistencia con la metodología del ICED. |
| PT-03 | Entrevista cognitiva | Comprensión del formulario | Observar cómo los participantes interpretan, recuperan, deciden y registran las respuestas. |
| PT-04 | Usabilidad | Interfaz y flujo | Evaluar navegación, claridad, carga, mensajes, tablas y facilidad de diligenciamiento. |
| PT-05 | Accesibilidad | Interfaz | Comprobar operación por teclado, etiquetas, foco, contraste y comprensión de errores. |
| PT-06 | Funcional | Campos y reglas | Comprobar que cada función responda al requisito y resultado esperado. |
| PT-07 | Integración | Módulos y servicios | Comprobar interacción entre formulario, persistencia, estados, administración y exportación CSV. |
| PT-08 | Integridad de datos | Base de datos | Comprobar correspondencia, completitud, conservación y actualización de respuestas. |
| PT-09 | Roles y seguridad básica | Accesos | Verificar autenticación, autorización y restricciones por perfil y organismo. |
| PT-10 | Compatibilidad | Navegadores y dispositivos | Comprobar el funcionamiento en configuraciones institucionales definidas. |
| PT-11 | Rendimiento y concurrencia | Aplicativo | Medir tiempos y estabilidad bajo el volumen previsto. Umbrales sujetos a aprobación técnica. |
| PT-12 | Recuperación y contingencia | Persistencia | Comprobar la conservación de información ante interrupciones y la restauración del servicio. |
| PT-13 | Motor de medición | Cálculo | Comparar los resultados del motor con casos patrón de doble corrida Excel↔web aprobados. |
| PT-14 | Prueba piloto | Proceso integral | Validar el operativo completo en condiciones controladas. |
| PT-15 | Regresivo | Componentes ajustados | Confirmar que las correcciones no afecten funciones previamente aprobadas. |

## **10\. Metodología de ejecución** {#10.-metodología-de-ejecución}

### 10.1 Preparación {#10.1-preparación}

- Aprobar el Plan de Pruebas y la ficha de versión.

- Consolidar la matriz de requisitos funcionales y metodológicos, elaborada por el líder de pruebas con insumo del documento metodológico ICED, el formulario vigente, los informes de avance y la verificación del código fuente; su aprobación corresponde a los responsables metodológico y técnico.

- Configurar el ambiente, usuarios y datos de prueba.

- Elaborar y aprobar los casos patrón de doble corrida (Anexo G), cuando el Ciclo 5 esté habilitado.

- Asignar responsables y observadores.

- Capacitar al equipo en el protocolo y los formatos.

- Confirmar la disponibilidad de manuales e instructivos.

### 10.2 Ejecución de casos {#10.2-ejecución-de-casos}

- Registrar la identificación del caso, versión y precondiciones.

- Ingresar los datos definidos y ejecutar los pasos sin omitir acciones.

- Comparar el resultado observado con el resultado esperado.

- Capturar evidencia: imagen, archivo exportado, registro de base de datos o bitácora.

- Clasificar el caso como aprobado, no aprobado, bloqueado o no ejecutado.

- Registrar y asignar el hallazgo cuando exista una diferencia.

### 10.3 Revisión y nueva prueba {#10.3-revisión-y-nueva-prueba}

El equipo de desarrollo analizará los hallazgos, realizará los ajustes autorizados y entregará una nueva versión identificada por commit o etiqueta. El equipo de pruebas repetirá los casos fallidos y los casos de regresión asociados. El cierre se producirá únicamente cuando el resultado observado corresponda al esperado o cuando la instancia responsable acepte formalmente una desviación documentada.

### 10.4 Metodología específica para pruebas cognitivas y de usabilidad {#10.4-metodología-específica-para-pruebas-cognitivas-y-de-usabilidad}

Se seleccionarán participantes con perfiles similares a las personas que diligencian y validan el FICED. La sesión utilizará tareas o escenarios previamente definidos, observación directa, pensamiento en voz alta cuando sea pertinente y preguntas de sondeo posteriores. El moderador no explicará la respuesta correcta durante la tarea. El observador registrará dificultades de interpretación, navegación, recuperación de información, decisión y registro de la respuesta.

### 10.5 Metodología de la prueba piloto {#10.5-metodología-de-la-prueba-piloto}

La prueba piloto simulará el flujo completo: sensibilización, acceso, prevalidación, diligenciamiento, guardado, envío, revisión, devolución, corrección, validación, exportación CSV y, cuando el Ciclo 5 esté aprobado, cálculo. La selección de organismos deberá incluir, como mínimo, un organismo por cada nivel de capacidad observado en la medición histórica más reciente, y representar diferentes niveles de complejidad, experiencia y volumen de información. El tamaño definitivo será aprobado según disponibilidad operativa y diversidad de perfiles.

### 10.6 Metodología de validación del motor de medición {#10.6-metodología-de-validación-del-motor-de-medición}

La validación del Ciclo 5 se realizará mediante doble corrida controlada, conforme al Anexo G:

1. El responsable metodológico selecciona y aprueba un conjunto de casos patrón (mínimo: un caso mínimo, un caso completo, casos condicionales por dimensión, casos límite de clasificación y al menos dos casos históricos reales anonimizados).

2. Cada caso se procesa en el instrumento Excel de referencia congelado (versión identificada) y se documentan los resultados por indicador, subdimensión, dimensión, global y nivel.

3. El mismo caso se diligencia en el FICED web y se ejecuta el motor sobre la versión de código identificada en la ficha de versión.

4. Se comparan los resultados con tolerancia cero, salvo diferencias de redondeo explícitamente aceptadas y documentadas por el responsable metodológico.

5. Toda diferencia no aceptada constituye hallazgo y se trata conforme al numeral 14\.

## **11\. Ambiente, datos y recursos** {#11.-ambiente,-datos-y-recursos}

### 11.1 Ambiente {#11.1-ambiente}

| Elemento | Requisito |
| :---- | :---- |
| Ambiente de pruebas | Separado del ambiente productivo y con versión identificable (commit o etiqueta). |
| Base de datos | Exclusiva o segregada para pruebas, con respaldo y posibilidad de reinicio. |
| Usuarios | Perfiles de delegado de organismo, validador del equipo técnico SIIED y administrador. |
| Navegadores | Versiones institucionales aprobadas por el equipo técnico. |
| Registro técnico | Disponibilidad de logs de aplicación, errores, auditoría y transacciones cuando aplique. Verificar previamente que las trazas de depuración identificadas (IC-04) hayan sido retiradas o controladas. |
| Conectividad | Condiciones similares a las de los organismos participantes. |

###  {#heading-4}

### 11.2 Datos de prueba

- Caso mínimo: información básica y respuestas de menor complejidad.

- Caso completo: diligenciamiento de todos los campos y tablas aplicables.

- Caso condicional: combinación que active y desactive subpreguntas.

- Caso de borde: máximos de filas, longitudes, porcentajes y listas.

- Caso inválido: formatos incorrectos, campos obligatorios vacíos y opciones incompatibles.

- Caso patrón: respuestas procesadas en paralelo en el instrumento Excel de referencia para comparar el cálculo (Anexo G).

- Caso de recuperación: interrupción y reingreso después del guardado.

### 11.3 Recursos {#11.3-recursos}

| Recurso | Descripción |
| :---- | :---- |
| Talento humano | Responsable metodológico, responsable técnico, analista QA, desarrollador, administrador, moderador, observador y participantes. |
| Tecnología | Ambiente SIIED, equipos de cómputo, navegadores, conectividad, sistema de incidencias, instrumento Excel de referencia congelado y almacenamiento de evidencias. |
| Documentación | Formulario, ficha y documento metodológico, informes de avance, manuales, matriz de requisitos y formatos anexos. |
| Logística | Agenda, convocatorias, sala física o virtual, acceso a participantes y mecanismos de soporte. |

## **12\. Organización, roles y responsabilidades** {#12.-organización,-roles-y-responsabilidades}

| Rol | Responsabilidades principales |
| :---- | :---- |
| Responsable metodológico del ICED | Aprobar la línea base, reglas, ponderaciones (resolución de IC-01), casos patrón y criterios metodológicos; validar los hallazgos que afecten el instrumento o el cálculo. |
| Responsable técnico SIIED | Entregar la versión, ambiente y documentación técnica; coordinar ajustes y respaldos; resolver IC-03 e IC-04; validar criterios técnicos. |
| Líder de pruebas / QA | Administrar el plan, elaborar la matriz de requisitos, asignar casos, controlar trazabilidad, consolidar evidencias y elaborar el informe final. |
| Ejecutor de pruebas | Aplicar los casos, registrar resultados y evidencias, y reportar hallazgos. |
| Desarrollador | Analizar y corregir defectos; documentar cambios; entregar versiones identificadas para nueva prueba. |
| Moderador | Conducir entrevistas cognitivas y sesiones de usabilidad sin inducir respuestas. |
| Observador | Registrar comportamientos, tiempos, dificultades y desviaciones del protocolo. |
| Participante / usuario | Ejecutar las tareas asignadas y aportar retroalimentación sobre comprensión y uso. |
| Instancia de aprobación | Revisar los resultados, condiciones pendientes y autorizar o negar la puesta en producción. |

##  {#heading-5}

## **13\. Criterios de entrada, suspensión, reanudación y cierre**

### 13.1 Criterios de entrada {#13.1-criterios-de-entrada}

- Plan de Pruebas revisado y aprobado.

- Ficha de versión diligenciada, incluyendo el registro de las inconsistencias conocidas (7.4).

- Formulario y documentación metodológica disponibles.

- Ambiente de pruebas estable y accesible.

- Usuarios, roles y datos de prueba configurados.

- Matriz de requisitos y casos de prueba aprobados.

- Reglas de cálculo aprobadas metodológicamente, IC-01 e IC-02 resueltos y casos patrón del Anexo G.

- Responsables y participantes confirmados.

### 13.2 Criterios de suspensión {#13.2-criterios-de-suspensión}

- Indisponibilidad persistente del ambiente.

- Defecto crítico que impida continuar la mayoría de los casos.

- Pérdida o corrupción de datos de prueba.

- Cambio de versión no informado durante la ejecución.

- Riesgo de exposición de información personal o acceso no autorizado.

- Ausencia de la especificación necesaria para determinar el resultado esperado.

### 13.3 Criterios de reanudación {#13.3-criterios-de-reanudación}

La ejecución se reanudará cuando la causa de suspensión haya sido corregida, la versión esté identificada, el ambiente haya sido estabilizado y el líder de pruebas confirme la validez de los datos y casos pendientes.

### 13.4 Criterios de cierre[^2] {#13.4-criterios-de-cierre}

- Todos los casos críticos y de prioridad alta fueron ejecutados.

- No existen hallazgos críticos abiertos.

- Los hallazgos altos fueron corregidos o aceptados formalmente con plan de tratamiento.

- Los casos afectados por ajustes superaron la nueva prueba y la regresión.

- Las inconsistencias del numeral 7.4 fueron resueltas o aceptadas formalmente con tratamiento documentado.

- Las evidencias están completas y organizadas.

- El informe final contiene resultados, conclusiones y recomendaciones.

- La instancia competente emitió el concepto de aprobación, aprobación condicionada o no aprobación.

## **14\. Gestión de hallazgos y no conformidades** {#14.-gestión-de-hallazgos-y-no-conformidades}

Cada hallazgo será registrado, asignado, analizado, corregido y sometido a nueva prueba. Cuando la causa corresponda a una inconsistencia de la especificación, la decisión será tomada por el responsable metodológico o técnico, según su naturaleza, y quedará documentada. Los hallazgos anticipados del numeral 7.4 ingresan al registro con su identificador desde el inicio de la ejecución.

| Severidad | Definición |
| :---- | :---- |
| Crítica | Impide el diligenciamiento o envío; causa pérdida/corrupción de datos; altera el resultado del índice; excluye organismos del consolidado sin registro; permite acceso no autorizado; o bloquea el proceso integral sin alternativa. |
| Alta | Afecta una función principal, regla metodológica o flujo relevante y no existe alternativa razonable, aunque el sistema siga parcialmente disponible. |
| Media | Afecta una función secundaria, comprensión o eficiencia; existe alternativa temporal y no compromete la integridad del resultado. |
| Baja | Defecto de presentación, redacción o mejora que no impide la operación ni altera datos o resultados. |

## **15\. Trazabilidad y evidencias** {#15.-trazabilidad-y-evidencias}

La trazabilidad se mantendrá mediante un identificador único que relacione requisito, caso de prueba, ejecución, evidencia, hallazgo, ajuste y nueva prueba.

| Evidencia | Ejemplo |
| :---- | :---- |
| Captura de pantalla | Formulario, mensaje, estado, error o resultado visible. |
| Archivo | Exportación CSV, log o reporte generado. |
| Registro de datos | Consulta o extracto controlado que demuestre la persistencia y estructura. |
| Bitácora técnica | Fecha, usuario, evento, excepción o transacción. |
| Hoja patrón | Resultado del instrumento Excel de referencia para comparación de cálculo. |
| Formato de observación | Comportamientos, tiempos y dificultades del participante. |
| Acta o correo | Decisiones, aprobaciones y autorizaciones. |
| Caso de prueba diligenciado | Resultado observado, estado, evidencia y responsable. |

La carpeta de evidencias deberá organizarse por ciclo, fecha, versión y código de caso. Se conservará conforme a los controles documentales y de seguridad de la entidad.

## **16\. Riesgos del plan de pruebas** {#16.-riesgos-del-plan-de-pruebas}

| ID | Riesgo | Nivel | Tratamiento |
| :---- | :---- | :---- | :---- |
| R-01 | Cambio del formulario durante la ejecución | Alta | Congelar la versión y registrar cambios; aplicar regresión. |
| R-02 | Reglas de cálculo implementadas sin aprobación metodológica formal (incluye IC-01 e IC-02) | Alta | Condicionar el Ciclo 5 a la aprobación de reglas y a la resolución de las inconsistencias; no emitir aceptación sobre cálculo antes de ello. |
| R-03 | Ambiente inestable o diferente de producción | Alta | Definir configuración, monitorear y documentar diferencias. |
| R-04 | Datos de prueba insuficientes | Media | Diseñar casos mínimos, completos, inválidos, condicionales, de borde y patrón. |
| R-05 | Participantes no representativos | Media | Seleccionar perfiles y organismos con diversidad funcional, de experiencia y de nivel de capacidad histórico. |
| R-06 | Pérdida de evidencias | Alta | Repositorio controlado, nomenclatura y respaldo diario. |
| R-07 | Confusión entre plan y resultados | Media | Mantener separados el Plan, los registros de ejecución y el informe final. |
| R-08 | Hallazgos sin responsable o fecha | Media | Asignación obligatoria y seguimiento periódico. |
| R-09 | Exposición de información personal (incluye trazas de depuración en logs, IC-04) | Alta | Usar datos sintéticos, retirar o controlar las trazas de depuración y limitar accesos. |
| R-10 | Prueba piloto utilizada como medición oficial | Alta | Rotular bases y productos como prueba; restringir difusión. |
| R-11 | Consolidado CSV incompleto por exclusión silenciosa de formularios con error (IC-03) | Alta | Verificar en CP-X01 la completitud del consolidado contra el inventario de formularios; exigir registro del motivo de exclusión. |
| R-12 | Pérdida del instrumento Excel de referencia o uso de una versión no congelada | Alta | Identificar, congelar y custodiar la versión del Excel patrón antes del Ciclo 5\. |

## **17\. Cronograma de referencia** {#17.-cronograma-de-referencia}

El siguiente cronograma se expresa en semanas relativas y deberá convertirse en fechas una vez se apruebe la disponibilidad del ambiente y del equipo.

| Periodo | Actividad | Responsable |
| :---- | :---- | :---- |
| Semana 1 | Aprobación del plan, ficha de versión, matriz de requisitos y preparación del ambiente. | Líder de pruebas / responsables metodológico y técnico |
| Semana 2 | Prueba de escritorio, grupo de expertos, resolución de IC-01 e IC-02 y configuración de datos/usuarios. | Equipo metodológico y QA |
| Semana 3 | Pruebas funcionales de módulos A, B y C; persistencia y navegación. | QA / equipo técnico |
| Semana 4 | Pruebas funcionales de módulos D y E; integración, estados, exportación CSV y datos. | QA / equipo técnico |
| Semana 5 | Usabilidad, accesibilidad, compatibilidad, recuperación y prueba piloto controlada. | Moderador, observadores y usuarios |
| Semana 6 | Correcciones, nueva prueba, regresión, consolidación e informe final. | Equipo ICED-SIIED |
| Ciclo condicionado | Pruebas del motor de medición una vez aprobadas las reglas y disponibles los casos patrón. | Metodología, QA y desarrollo |

## **18\. Productos esperados** {#18.-productos-esperados}

| Código | Producto |
| :---- | :---- |
| P-01 | Plan de Pruebas aprobado. |
| P-02 | Ficha de versión y matriz de requisitos. |
| P-03 | Matriz de trazabilidad. |
| P-04 | Casos de prueba diligenciados. |
| P-05 | Repositorio de evidencias. |
| P-06 | Registro de hallazgos y acciones correctivas. |
| P-07 | Informe de prueba de escritorio y grupo de expertos. |
| P-08 | Informe de entrevistas cognitivas, usabilidad y accesibilidad. |
| P-09 | Informe de prueba piloto. |
| P-10 | Informe de validación del motor de medición con las matrices de doble corrida (Anexo G). |
| P-11 | Informe final de pruebas, conclusiones y recomendaciones. |
| P-12 | Mecanismo de aprobación para la puesta en producción. |

## **19\. Mecanismo de aprobación** {#19.-mecanismo-de-aprobación}

Concluidos los ciclos aplicables, el líder de pruebas presentará el informe final y la matriz de hallazgos a las instancias metodológica y técnica. La decisión se registrará en acta o formato de aprobación con una de las siguientes categorías:

- **Aprobado para producción:** no existen hallazgos críticos o altos abiertos y se cumplen los criterios de cierre.

- **Aprobado con condiciones:** existen asuntos no críticos con tratamiento, responsable y fecha acordados, sin impacto sobre la integridad del instrumento o los resultados.

- **No aprobado:** persisten defectos que impiden la operación segura, íntegra o metodológicamente válida.

- **No evaluable:** no fue posible determinar el resultado por falta de versión, especificación, acceso o evidencia suficiente.

| Concepto final | Justificación | Condiciones / pendientes | Responsables | Firmas / fecha |
| :---- | :---- | :---- | :---- | :---- |
|  |  |  |  |  |

## **20\. Referencias** {#20.-referencias}

- Departamento Administrativo Nacional de Estadística (DANE) e ICONTEC. (2020). *Norma Técnica de la Calidad del Proceso Estadístico.* NTC PE 1000:2020.

- Departamento Administrativo Nacional de Estadística (DANE). (2020). *Lineamientos para el proceso estadístico en el Sistema Estadístico Nacional.* Versión 2.0.

- Departamento Administrativo Nacional de Estadística (DANE). (2020). *Guía para la definición y la aplicación de pruebas en las operaciones estadísticas.* Versión 2\.

- Alcaldía de Santiago de Cali, Departamento Administrativo de Planeación. *Documento metodológico del Índice de Capacidad Estadística Distrital (ICED).*

- Alcaldía de Santiago de Cali, SIIED. (2026). *Informe de Avance \- Módulo ICED (FICED v2).*

- Alcaldía de Santiago de Cali, SIIED. (2026). *Informe de Avance \- Instrumento de Captura FICED v2.*

- Alcaldía de Santiago de Cali, SIIED. (2026). *Código fuente del módulo FICED v2 de la plataforma SIIED* (versión identificada en la ficha de versión).

## **ANEXO A. Matriz de trazabilidad normativa y funcional** {#anexo-a.-matriz-de-trazabilidad-normativa-y-funcional}

| ID | Fuente | Requisito | Prueba asociada | Evidencia prevista |
| :---- | :---- | :---- | :---- | :---- |
| N-01 | NTC PE 1000:2020, 7.7 | Ejecutar y documentar pruebas a lo diseñado. | Todos los ciclos | Plan, casos e informes |
| N-02 | NTC PE 1000:2020, 7.7.1 a) | Identificar afectaciones en el desarrollo de la operación. | Registro de hallazgos | Matriz de hallazgos |
| N-03 | NTC PE 1000:2020, 7.7.1 b) | Mantener trazabilidad sobre actividades, métodos, instrumentos y software. | Todos los casos | Matriz de trazabilidad |
| N-04 | NTC PE 1000:2020, 7.7.1 c-d | Documentar resultados y conclusiones; conservar evidencia. | Cierre | Informes y repositorio |
| N-05 | Lineamientos SEN, 3.6 | Comprobar instrumentos electrónicos y sistema de producción. | Funcional e integración | Casos y evidencias |
| N-06 | Lineamientos SEN, 3.7 | Definir y aplicar prueba piloto y observación estandarizada. | Piloto | Protocolo e informe |
| N-07 | Lineamientos SEN, 3.8 | Evaluar el diseño y la construcción con base en resultados. | Cierre | Informe de evaluación |
| N-08 | Lineamientos SEN, 3.9 | Establecer mecanismo de aprobación para producción. | Aprobación | Acta o formato firmado |
| F-01 | Informe captura 2026 / código fuente | 42 preguntas en cinco módulos y diez pasos. | Funcional y escritorio | Casos por módulo |
| F-02 | Informe captura 2026 / código fuente | Mínimo una persona de contacto con campos obligatorios. | Funcional módulo A | CP-A01 a CP-A03 |
| F-03 | Informe captura 2026 / código fuente | Reglas condicionales, opciones excluyentes y tablas dinámicas. | Funcional | CP-B/C/D/E |
| F-04 | Informe captura 2026 / código fuente | Guardado borrador, guardado parcial, guardado al avanzar y envío definitivo. | Persistencia | CP-P01 a CP-P05 |
| F-05 | Informe módulo 2026 / código fuente | Estados y panel de validación/devolución. | Integración | CP-W01 a CP-W04 |
| F-06 | Código fuente | Exportación CSV consolidada por periodo y auditoría. | Integración y datos | CP-X01 a CP-X03 |
| F-07 | Documento metodológico ICED | Correspondencia de variables, preguntas y dimensiones. | Escritorio y expertos | CP-E01 a CP-E06 |
| F-08 | Metodología de cálculo aprobada \+ motor implementado | Puntajes, ponderaciones, no aplica, clasificación y reproducibilidad. | Motor | CP-M01 a CP-M09 |
| F-09 | Código fuente / tablas auxiliares | Materialización de personas de contacto y recurso humano desde las respuestas. | Integración y datos | CP-I03 |

## **ANEXO B. Inventario inicial de casos de prueba** {#anexo-b.-inventario-inicial-de-casos-de-prueba}

| ID | Componente | Caso previsto | Tipo | Prioridad | Resultado esperado | Evidencia | Ciclo |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| CP-E01 | Instrumento | Correspondencia entre preguntas del formulario aprobado y la versión web. | Escritorio | Alta | No existen omisiones, duplicidades ni cambios no autorizados. | Lista de chequeo | 1 |
| CP-E02 | Instrumento | Orden de módulos, pasos y numeración P1-P42. | Escritorio | Alta | La secuencia corresponde a la ficha de versión aprobada. | Capturas y matriz | 1 |
| CP-E03 | Instrumento | Opciones de respuesta, escalas y campos "Otro/Especifique". | Escritorio | Alta | Las opciones y ayudas corresponden al instrumento aprobado. | Lista de chequeo | 1 |
| CP-E04 | Instrumento | Reglas condicionales y preguntas no aplicables. | Escritorio | Alta | Cada regla tiene condición, acción y tratamiento definido. | Matriz de reglas | 1 |
| CP-E05 | Instrumento | Claridad de definiciones, instrucciones y periodos de referencia. | Expertos | Media | Los términos son comprensibles y consistentes. | Acta/informe | 1 |
| CP-E06 | Instrumento | Carga y disponibilidad de información solicitada. | Expertos | Media | La información puede ser suministrada por los perfiles previstos. | Acta/informe | 1 |
| CP-E07 | Instrumento / reglas | Verificación documental de la ponderación de dimensiones (resolución de IC-01). | Escritorio | Alta | La ponderación aprobada queda consignada y coincide en documentación, modelo y motor. | Acta metodológica | 1 |
| CP-A01 | Módulo A | Prediligenciamiento y bloqueo del nombre del organismo. | Funcional | Alta | P1 muestra el organismo del usuario y no permite modificación no autorizada. | Captura/log | 2 |
| CP-A02 | Módulo A | Registro de personas de contacto. | Funcional | Alta | Permite agregar/editar/eliminar contactos según la especificación. | Capturas/datos | 2 |
| CP-A03 | Módulo A | Obligatoriedad y formato de nombre, cargo y correo. | Funcional negativo | Alta | Impide continuar o enviar con campos obligatorios vacíos o correo inválido. | Captura de mensaje | 2 |
| CP-B01 | Módulo B | Condicional de P10: motivo o tabla de actividades. | Funcional | Alta | Se muestra el campo correspondiente a la opción elegida y se oculta el no aplicable. | Capturas | 2 |
| CP-B02 | Módulo B | Condicional de P12: descripción del mecanismo. | Funcional | Alta | La descripción se exige solo para las opciones definidas. | Capturas | 2 |
| CP-B03 | Módulo B | Opciones excluyentes en P8, P9 y P11. | Funcional negativo | Alta | "No se incluyen/no participa" no coexiste con otras opciones. | Capturas/datos | 2 |
| CP-B04 | Módulo B | Tablas jerárquicas y dinámicas: filas, edición y límites. | Funcional de borde | Media | Conserva jerarquía, permite edición y respeta límites. | Capturas/datos | 2 |
| CP-C01 | Módulo C | Exclusividad de "Ninguna/Ninguno" en herramientas. | Funcional negativo | Alta | La opción exclusiva desmarca o bloquea opciones incompatibles. | Capturas | 2 |
| CP-C02 | Módulo C | P15 activa P15.1 y P16. | Funcional | Alta | Las preguntas se muestran y validan únicamente cuando P15=Sí. | Capturas | 2 |
| CP-C03 | Módulo C | P18 controla la disponibilidad de P19. | Funcional | Alta | P19 se oculta/no aplica cuando no existe estructura y se habilita en los demás casos. | Capturas | 2 |
| CP-C04 | Módulo C | P19: alta, edición, eliminación y máximo de registros. | Funcional de borde | Alta | Las personas se gestionan sin duplicación y el límite se respeta. | Capturas/datos | 2 |
| CP-C05 | Módulo C | P21: validación de campos porcentuales. | Funcional negativo | Alta | Solo acepta formato y rango aprobados; informa errores de forma clara. | Capturas | 2 |
| CP-C06 | Módulo C | Campos "Otro/propias" activan detalle. | Funcional | Media | El detalle aparece solo cuando corresponde y se conserva. | Capturas/datos | 2 |
| CP-D01 | Módulo D | P23: carga y edición de operaciones estadísticas. | Funcional | Alta | Las filas se cargan para el organismo y conservan las columnas definidas. | Capturas/datos | 2 |
| CP-D02 | Módulo D | P24: nomenclaturas y subtablas condicionales. | Funcional | Alta | Las subtablas se despliegan y validan según la selección. | Capturas | 2 |
| CP-D03 | Módulo D | P25: subcampos de proyectos y otros mecanismos. | Funcional | Media | Los campos se muestran solo ante las opciones correspondientes. | Capturas | 2 |
| CP-D04 | Módulo D | P27-P28: articulación y preguntas asociadas. | Funcional | Alta | Las preguntas dependientes siguen la condición aprobada. | Capturas | 2 |
| CP-D05 | Módulo D | Tablas y listas de observatorios/políticas. | Funcional | Media | Las opciones se cargan, seleccionan y conservan sin duplicidad. | Capturas/datos | 2 |
| CP-EA01 | Módulo E | Validación de preguntas de disponibilidad, uso, difusión y accesibilidad. | Funcional | Alta | Cada tipo de respuesta y condicional se comporta conforme a la especificación. | Capturas/datos | 2 |
| CP-EA02 | Módulo E | URLs, matrices y campos de satisfacción. | Funcional negativo | Media | Valida formatos y conserva la estructura de la matriz. | Capturas/datos | 2 |
| CP-P01 | Persistencia | Guardar borrador en cualquier paso (incluido el guardado parcial). | Integración | Crítica | La información queda almacenada sin cambiar a enviado. | Captura/datos/log | 2 |
| CP-P02 | Persistencia | Guardado automático al avanzar. | Integración | Crítica | Al presionar Siguiente se conserva el paso actual antes de navegar. | Datos/log | 2 |
| CP-P03 | Persistencia | Cerrar sesión y reanudar el diligenciamiento. | Recuperación | Crítica | El usuario recupera el último borrador íntegro, incluidas tablas auxiliares. | Capturas/datos | 2 |
| CP-P04 | Persistencia | Interrupción de red durante el guardado. | Contingencia | Alta | No se corrompen respuestas y el usuario recibe un mensaje controlado. | Video/log | 4 |
| CP-P05 | Persistencia | Unicidad organismo-periodo. | Integridad | Alta | No se crean formularios duplicados para el mismo organismo y periodo. | Consulta de datos | 3 |
| CP-W01 | Flujo | Envío definitivo con validación completa. | Integración | Crítica | Solo envía cuando todos los campos aplicables cumplen reglas. | Captura/log | 3 |
| CP-W02 | Flujo | Transición borrador-enviado-validado. | Integración | Crítica | Cada transición sigue los permisos y registra fechas. | Capturas/datos | 3 |
| CP-W03 | Flujo | Devolución para corrección y observaciones. | Integración | Alta | El organismo visualiza observaciones y puede corregir lo autorizado. | Capturas/datos | 3 |
| CP-W04 | Flujo | Restricción de edición después de validación. | Seguridad funcional | Alta | El formulario validado no se modifica sin procedimiento autorizado. | Captura/log | 3 |
| CP-I01 | Datos | Correspondencia entre respuesta visible y JSON almacenado. | Integridad | Crítica | Los datos almacenados corresponden exactamente a la respuesta. | Consulta controlada | 3 |
| CP-I02 | Datos | Caracteres especiales, tildes, longitud y saltos de línea. | Integridad de borde | Media | La información se conserva sin truncamiento o corrupción. | Datos/exportación | 3 |
| CP-I03 | Datos | Materialización de registros auxiliares de RRHH/contactos. | Integración | Alta | Los registros auxiliares coinciden con la información del formulario, incluida la recreación tras correcciones. | Consulta de datos | 3 |
| CP-X01 | Salidas | Exportación CSV consolidada por periodo. | Funcional | Crítica | El archivo incluye la totalidad de los formularios del periodo (o registra el motivo de exclusión de cada faltante), con puntaje global, dimensiones, subdimensiones e indicadores por organismo (verifica IC-03). | Archivo CSV / consulta | 3 |
| CP-X02 | Salidas | Estructura y codificación del CSV. | Funcional | Alta | Encabezados, orden de columnas, separadores, codificación de caracteres y formato porcentual corresponden a la especificación aprobada. | Archivo CSV | 3 |
| CP-X03 | Auditoría | Registro de usuario, fechas, estados y observaciones. | Integración | Alta | La trazabilidad de eventos está disponible según la especificación y los logs no exponen contenido de respuestas (verifica IC-04). | Log/consulta | 3 |
| CP-S01 | Seguridad | Acceso autenticado y segregación por organismo. | Seguridad básica | Crítica | Un usuario no accede a formularios de otro organismo. | Captura/log | 3 |
| CP-S02 | Seguridad | Permisos del validador y administrador. | Seguridad funcional | Alta | Cada rol ejecuta únicamente las acciones autorizadas. | Capturas | 3 |
| CP-S03 | Seguridad | Acceso directo mediante URL no autorizada. | Seguridad básica | Crítica | El sistema rechaza el acceso y no expone datos. | Captura/log | 3 |
| CP-U01 | Usabilidad | Comprensión de etiquetas, instrucciones y mensajes. | Cognitiva/usabilidad | Alta | Los participantes interpretan y completan las tareas sin ayuda indebida. | Formato observación | 4 |
| CP-U02 | Usabilidad | Navegación, progreso y retorno entre pasos. | Usabilidad | Media | El usuario identifica dónde está y puede avanzar/retroceder sin perder datos. | Formato observación | 4 |
| CP-U03 | Usabilidad | Uso de tablas complejas y dinámicas. | Usabilidad | Alta | Los participantes agregan y editan filas correctamente. | Video/notas | 4 |
| CP-A11Y01 | Accesibilidad | Operación por teclado y foco visible. | Accesibilidad | Media | Todos los controles esenciales son operables por teclado. | Lista de chequeo | 4 |
| CP-A11Y02 | Accesibilidad | Etiquetas, errores y contraste. | Accesibilidad | Media | Los campos y errores son identificables y comprensibles. | Lista/capturas | 4 |
| CP-COMP01 | Compatibilidad | Navegadores institucionales. | Compatibilidad | Alta | El formulario mantiene funciones y presentación en las versiones aprobadas. | Capturas | 4 |
| CP-R01 | Rendimiento | Carga, guardado y envío bajo volumen previsto. | Rendimiento | Media | Cumple los umbrales técnicos aprobados. | Medición/log | 4 |
| CP-M01 | Motor | Puntuación por pregunta e indicador individual (36 indicadores). | Cálculo | Crítica | Cada respuesta obtiene el valor de la doble corrida patrón. | Comparación patrón | 5 |
| CP-M02 | Motor | Agregación por subdimensión (9) y dimensión (4). | Cálculo | Crítica | Los resultados coinciden con la hoja patrón del Excel de referencia. | Matriz comparativa | 5 |
| CP-M03 | Motor | Ponderación y puntaje global. | Cálculo | Crítica | La fórmula y los pesos aprobados (tras resolución de IC-01) se aplican sin desviación en modelo, motor y exportación. | Matriz comparativa | 5 |
| CP-M04a | Motor | Tratamiento de "no aplica" y condicionales ocultos — Dimensión 1 (Entorno institucional). | Cálculo | Crítica | Los denominadores y puntajes de la dimensión no se alteran indebidamente. | Casos patrón | 5 |
| CP-M04b | Motor | Tratamiento de "no aplica" y condicionales ocultos — Dimensión 2 (Infraestructura). | Cálculo | Crítica | Ídem CP-M04a para la dimensión 2\. | Casos patrón | 5 |
| CP-M04c | Motor | Tratamiento de "no aplica" y condicionales ocultos — Dimensión 3 (Metodología estadística). | Cálculo | Crítica | Ídem CP-M04a para la dimensión 3\. | Casos patrón | 5 |
| CP-M04d | Motor | Tratamiento de "no aplica" y condicionales ocultos — Dimensión 4 (Accesibilidad y uso). | Cálculo | Crítica | Ídem CP-M04a para la dimensión 4\. | Casos patrón | 5 |
| CP-M05 | Motor | Clasificación por nivel, cortes y redondeo. | Cálculo de borde | Crítica | Los límites y redondeos coinciden con la regla aprobada y existe una única fuente de la regla de clasificación (verifica IC-02); se prueban valores exactamente en los cortes. | Casos límite | 5 |
| CP-M06 | Motor | Consistencia de escalas entre cálculo, almacenamiento y presentación. | Cálculo | Alta | La conversión entre la escala de cálculo (0-100) y la de almacenamiento (0-1) no introduce pérdida ni inconsistencia en resultado ni exportación. | Consulta/CSV | 5 |
| CP-M07 | Motor | Recálculo tras devolución y corrección. | Cálculo/regresión | Alta | El recálculo sobre respuestas corregidas reemplaza íntegramente los puntajes previos. | Datos/comparación | 5 |
| CP-M08 | Motor | Reproducibilidad: misma entrada y misma versión de código producen el mismo resultado. | Regresión | Alta | Resultados idénticos en corridas repetidas, con versión de código (commit/etiqueta) registrada en la evidencia. | Comparación de corridas | 5 |
| CP-M09 | Motor | Doble corrida integral Excel↔web sobre casos históricos anonimizados. | Cálculo | Crítica | El resultado del motor coincide con el procesamiento del instrumento Excel de referencia, salvo redondeos aceptados y documentados. | Matriz Anexo G | 5 |
| CP-PI01 | Proceso integral | Diligenciamiento de extremo a extremo. | Prueba piloto | Crítica | El proceso completo puede ejecutarse con los perfiles, tiempos y soportes definidos, incluyendo al menos un organismo por nivel de capacidad histórico. | Informe piloto | 6 |

## **ANEXO C. Formato de caso de prueba** {#anexo-c.-formato-de-caso-de-prueba}

| Campo | Registro |
| :---- | :---- |
| **ID del caso** |  |
| **Nombre** |  |
| **Versión / ambiente (commit o etiqueta)** |  |
| **Requisito asociado** |  |
| **Tipo y prioridad** |  |
| **Precondiciones** |  |
| **Datos de prueba** |  |
| **Pasos de ejecución** | 1\. 2\. 3\. |
| **Resultado esperado** |  |
| **Resultado observado** |  |
| **Evidencia** |  |
| **Estado** | Aprobado / No aprobado / Bloqueado / No ejecutado |
| **Hallazgo asociado** |  |
| **Ejecutor / fecha** |  |
| **Responsable de validación** |  |
| **Observaciones** |  |

## **ANEXO D. Formato de observación** {#anexo-d.-formato-de-observación}

| Campo | Registro |
| :---- | :---- |
| **Sesión / fecha** |  |
| **Versión** |  |
| **Perfil del participante** |  |
| **Escenario o tareas** |  |
| **Tiempo total** |  |
| **Dificultades de comprensión** |  |
| **Dificultades de recuperación de información** |  |
| **Dificultades de navegación o registro** |  |
| **Mensajes o ayudas requeridas** |  |
| **Errores observados** |  |
| **Comentarios del participante** |  |
| **Recomendaciones** |  |
| **Moderador / observador** |  |

## **ANEXO E. Formato de registro de hallazgos** {#anexo-e.-formato-de-registro-de-hallazgos}

| Campo | Registro |
| :---- | :---- |
| **ID del hallazgo** |  |
| **Fecha y versión (commit o etiqueta)** |  |
| **Caso de prueba** |  |
| **Requisito afectado** |  |
| **Descripción** |  |
| **Resultado esperado** |  |
| **Resultado observado** |  |
| **Evidencia** |  |
| **Severidad** | Crítica / Alta / Media / Baja |
| **Impacto metodológico** |  |
| **Impacto operativo** |  |
| **Impacto tecnológico** |  |
| **Responsable de análisis** |  |
| **Acción correctiva** |  |
| **Fecha compromiso** |  |
| **Estado** | Abierto / En análisis / Corregido / En nueva prueba / Cerrado / Aceptado |
| **Resultado de nueva prueba** |  |
| **Cierre y aprobación** |  |

## **ANEXO F. Estructura del informe de resultados** {#anexo-f.-estructura-del-informe-de-resultados}

- Identificación de la versión y el ambiente probado.

- Objetivo, alcance y pruebas ejecutadas.

- Equipo participante y fechas.

- Resumen de casos: aprobados, no aprobados, bloqueados y no ejecutados.

- Resultados por tipo de prueba y componente.

- Resultado de las inconsistencias conocidas (7.4): resueltas, aceptadas o pendientes.

- Hallazgos por severidad y estado.

- Ajustes efectuados y pruebas de regresión.

- Limitaciones de la ejecución.

- Conclusiones sobre el funcionamiento del instrumento y el sistema.

- Recomendaciones y asuntos pendientes.

- Concepto de aprobación para producción.

- Anexos de evidencias, actas y matrices.

## **ANEXO G. Protocolo de casos patrón — doble corrida excel↔web** {#anexo-g.-protocolo-de-casos-patrón-—-doble-corrida-excel↔web}

### G.1 Propósito {#g.1-propósito}

Garantizar la equivalencia de resultados entre el instrumento Excel de referencia (procesamiento histórico) y el motor de medición implementado en el SIIED, como condición de continuidad de la serie estadística del ICED.

### G.2 Insumos {#g.2-insumos}

| Insumo | Requisito |
| :---- | :---- |
| Instrumento Excel de referencia | Versión congelada, identificada y custodiada por el responsable metodológico. |
| Reglas de cálculo aprobadas | Ponderaciones, puntuaciones por respuesta, tratamiento de "no aplica", cortes de clasificación y regla de redondeo, formalmente aprobadas. |
| Motor implementado | Versión de código identificada por commit o etiqueta en la ficha de versión. |

### G.3 Conjunto mínimo de casos patrón {#g.3-conjunto-mínimo-de-casos-patrón}

| Código | Caso | Descripción |
| :---- | :---- | :---- |
| PAT-01 | Mínimo | Respuestas de menor puntuación posible en todas las dimensiones. |
| PAT-02 | Máximo | Respuestas de máxima puntuación posible en todas las dimensiones. |
| PAT-03 a PAT-06 | Condicional por dimensión | Un caso por dimensión que active y desactive las condicionales y opciones "no aplica" de esa dimensión. |
| PAT-07 y PAT-08 | Cortes de clasificación | Valores que caigan exactamente en los cortes entre niveles, para verificar límites y redondeo. |
| PAT-09 y PAT-10 | Históricos | Al menos dos formularios reales de mediciones anteriores, anonimizados, con resultado histórico documentado. |

El responsable metodológico podrá ampliar el conjunto. Ningún caso patrón podrá modificarse después de aprobado; las adiciones se registran como nuevos códigos.

### G.4 Procedimiento {#g.4-procedimiento}

1. Diligenciar cada caso en el Excel de referencia y documentar los resultados por indicador, subdimensión, dimensión, global y nivel (hoja patrón firmada o aprobada).

2. Diligenciar el mismo caso en el FICED web en el ambiente de pruebas.

3. Ejecutar el cálculo desde el panel de validación y registrar los resultados almacenados y los exportados en el CSV.

4. Diligenciar la matriz comparativa (G.5) valor a valor.

5. Clasificar cada comparación como: coincide / difiere por redondeo aceptado / difiere (hallazgo).

6. Registrar los hallazgos conforme al numeral 14 y repetir la corrida tras las correcciones.

### G.5 Matriz comparativa (formato) {#g.5-matriz-comparativa-(formato)}

| Caso patrón | Elemento (indicador / subdimensión / dimensión / global / nivel) | Valor Excel | Valor motor SIIED | Valor CSV exportado | Estado | Observación |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
|  |  |  |  |  | Coincide / Redondeo aceptado / Hallazgo |  |

### 

### G.6 Criterio de aceptación {#g.6-criterio-de-aceptación}

El Ciclo 5 se considera aprobado cuando el 100% de las comparaciones de todos los casos patrón se clasifica como "coincide" o "difiere por redondeo aceptado", y las diferencias por redondeo cuentan con aceptación escrita del responsable metodológico.

 

[^1]: >  **Precisión documental.** Este documento corresponde al diseño del Plan de Pruebas. La evidencia de su aplicación se generará posteriormente mediante casos diligenciados, registros de hallazgos, actas, informes de observación e informe final de resultados.



[^2]:  **Umbrales.** Los porcentajes mínimos de aprobación, tiempos de respuesta y niveles de concurrencia deberán ser definidos y aprobados antes de la ejecución. Mientras no exista esa definición, no se utilizarán umbrales arbitrarios. Se exceptúa el Ciclo 5, cuyo criterio es de tolerancia cero frente a los casos patrón, salvo redondeos aceptados.

