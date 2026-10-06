# SISTEMA INTEGRADO DE INFORMACIÓN ESTADÍSTICA DISTRITAL - SIIED
## Plan de Pruebas FICED v2

**ALCALDÍA DE SANTIAGO DE CALI**
**DEPARTAMENTO ADMINISTRATIVO DE PLANEACIÓN**
**SUBDIRECCIÓN DE DESARROLLO INTEGRAL**

# PLAN DE PRUEBAS

## ADAPTACIÓN DEL FORMULARIO DEL ÍNDICE DE CAPACIDAD ESTADÍSTICA DISTRITAL (FICED) EN LA PLATAFORMA DEL SISTEMA INTEGRADO DE INFORMACIÓN ESTADÍSTICA DISTRITAL (SIIED)

*Documento de diseño y planificación de las pruebas*

**No contiene resultados de ejecución**

**Santiago de Cali, 2026**

**Versión 1.1**

---

## CONTROL DOCUMENTAL

| Campo | Descripción |
| --- | --- |
| **Nombre del documento** | Plan de pruebas para la adaptación del FICED en la plataforma SIIED |
| **Código documental** | Pendiente de asignación por el Sistema Integrado de Gestión |
| **Versión** | 1.1 |
| **Estado** | Formulado para revisión y aprobación |
| **Responsable metodológico** | Equipo responsable de la operación estadística ICED |
| **Responsable técnico** | Equipo de desarrollo y administración de la plataforma SIIED |
| **Fecha de elaboración** | 2026 |
| **Periodo de aplicación** | Vigencia definida para la puesta en producción del FICED v2 |

## HISTORIAL DE CAMBIOS

| Versión | Fecha | Descripción del cambio | Responsable |
| --- | --- | --- | --- |
| 1.0 | 2026 | Formulación inicial del plan de pruebas del instrumento de captura FICED v2 y sus componentes asociados. | Equipo ICED-SIIED |
| 1.1 | 2026 | Actualización de la línea base contra la verificación técnica del código fuente: el motor de medición se encuentra implementado (pendiente de aprobación metodológica); la exportación implementada es CSV; se incorporan el guardado parcial vía API, el filtro de exportación por estado, casos de prueba nuevos (CP-P06, CP-X04, CP-I04, CP-S04, CP-M07, CP-M08), el protocolo de doble corrida Excel↔web para los casos patrón del motor, riesgos R-11 a R-13 e incidencias conocidas en la ficha de versión. | Equipo ICED-SIIED |

## REVISIÓN Y APROBACIÓN

| Rol | Nombre / cargo | Concepto | Firma / fecha |
| --- | --- | --- | --- |
| Elaboró | Equipo técnico y metodológico ICED-SIIED | Pendiente de diligenciamiento | |
| Revisó - componente metodológico | Responsable de la operación estadística ICED | Pendiente de diligenciamiento | |
| Revisó - componente tecnológico | Responsable técnico de la plataforma SIIED | Pendiente de diligenciamiento | |
| Aprobó | Instancia definida para autorizar la ejecución del plan | Pendiente de diligenciamiento | |

> **Precisión documental.** Este documento corresponde al diseño del Plan de Pruebas. La evidencia de su aplicación se generará posteriormente mediante casos diligenciados, registros de hallazgos, actas, informes de observación e informe final de resultados.

---

## CONTENIDO

1. Introducción
2. Antecedentes
3. Naturaleza y propósito del documento
4. Marco normativo y metodológico
5. Objetivos
6. Alcance y exclusiones
7. Línea base y objeto de prueba
8. Estrategia general de pruebas
9. Tipos de prueba previstos
10. Metodología de ejecución
11. Ambiente, datos y recursos
12. Organización, roles y responsabilidades
13. Criterios de entrada, suspensión, reanudación y cierre
14. Gestión de hallazgos y no conformidades
15. Trazabilidad y evidencias
16. Riesgos del plan de pruebas
17. Cronograma de referencia
18. Productos esperados
19. Mecanismo de aprobación
20. Referencias

**Anexo A.** Matriz de trazabilidad normativa y funcional
**Anexo B.** Inventario inicial de casos de prueba
**Anexo C.** Formato de caso de prueba
**Anexo D.** Formato de observación
**Anexo E.** Formato de registro de hallazgos
**Anexo F.** Estructura del informe de resultados
**Anexo G.** Protocolo de doble corrida para casos patrón del motor de medición

---

## SIGLAS Y ABREVIATURAS

| Sigla | Definición |
| --- | --- |
| API | Interfaz de programación de aplicaciones |
| CSV | Valores separados por comas (formato de exportación) |
| DANE | Departamento Administrativo Nacional de Estadística |
| FICED | Formulario del Índice de Capacidad Estadística Distrital |
| ICED | Índice de Capacidad Estadística Distrital |
| JSON | Notación de objetos de JavaScript (formato de almacenamiento de respuestas) |
| NTC PE 1000 | Norma Técnica de la Calidad del Proceso Estadístico |
| QA | Aseguramiento de la calidad del software |
| SEN | Sistema Estadístico Nacional |
| SIIED | Sistema Integrado de Información Estadística Distrital |
| UAT | Pruebas de aceptación de usuario |

---

## 1. INTRODUCCIÓN

El presente Plan de Pruebas define la estrategia, los métodos, los responsables, los recursos, los criterios y los productos necesarios para verificar la adaptación del Formulario del Índice de Capacidad Estadística Distrital (FICED) en la plataforma del Sistema Integrado de Información Estadística Distrital (SIIED).

El documento se formula como parte de la fase de diseño del proceso estadístico y orienta la ejecución posterior de las pruebas durante la fase de construcción. En consecuencia, establece qué se probará, cómo se realizará la prueba, quiénes intervendrán, cuáles serán los resultados esperados y qué evidencias deberán conservarse, sin presentar resultados de ejecución.

La formulación se sustenta en la NTC PE 1000:2020, los Lineamientos para el proceso estadístico en el Sistema Estadístico Nacional y la Guía para la definición y la aplicación de pruebas en las operaciones estadísticas del DANE. Estos referentes requieren que las pruebas mantengan trazabilidad sobre las actividades, los métodos, los instrumentos y el software aplicativo, y que sus resultados y conclusiones queden documentados.

La versión 1.1 actualiza la línea base del objeto de prueba con fundamento en la verificación directa del código fuente del módulo, con el fin de que los casos de prueba correspondan al estado real del desarrollo y no exclusivamente a los informes de avance.

## 2. ANTECEDENTES

El ICED es la operación estadística mediante la cual se evalúa la capacidad estadística de los organismos de la Alcaldía de Santiago de Cali. Su instrumento de recolección fue inicialmente desarrollado en Microsoft Excel y aplicado mediante diligenciamiento asistido. La adaptación al SIIED busca disponer de un instrumento electrónico que facilite la captura, el guardado, la validación, la administración y el procesamiento de la información.

La documentación técnica disponible reporta una versión web del FICED estructurada como formulario tipo wizard, con 42 preguntas principales organizadas en cinco módulos temáticos y diez pasos de navegación. La verificación técnica realizada sobre el código fuente para la versión 1.1 de este plan confirma que el desarrollo actual incluye, adicionalmente a lo reportado en los informes de avance:

- Motor de medición automatizado **implementado** (36 indicadores individuales, 9 subdimensiones, 4 dimensiones y puntaje global ponderado), pendiente de aprobación metodológica formal.
- API de guardado parcial (borrador) invocable desde el wizard en cualquier paso.
- Materialización de registros auxiliares de personas de contacto y de recurso humano a partir de las respuestas en formato JSON.
- Exportación de resultados en formato **CSV oficial**, restringida a formularios en estado *validado*.
- Panel de validación con acciones de revisión, cálculo y decisión sobre los formularios enviados.
- Acceso del delegado mediante redirección automática según el estado del formulario de su organismo y periodo.

Estas referencias se emplean para definir el universo de pruebas, sin sustituir la validación funcional y metodológica que debe efectuarse antes de la ejecución.

> **Criterio de línea base.** Para la ejecución del presente plan deberá emitirse un acta o ficha de versión que identifique el formulario, el ambiente y los componentes tecnológicos que serán sometidos a prueba. Cualquier modificación posterior activará pruebas de regresión sobre los componentes afectados.

## 3. NATURALEZA Y PROPÓSITO DEL DOCUMENTO

Este documento constituye el soporte de que la operación estadística diseñó y planificó las pruebas aplicables al nuevo formulario. No equivale al informe de ejecución de pruebas ni acredita por sí solo que el aplicativo fue aprobado para producción.

La documentación completa del ciclo de pruebas estará conformada por:

- Plan de Pruebas aprobado (este documento).
- Matriz de requisitos y trazabilidad.
- Casos de prueba diligenciados y evidencias.
- Registros de hallazgos, incidencias y acciones correctivas.
- Informes de observación de pruebas cognitivas, de usabilidad y piloto.
- Informe de validación del motor de medición con la comparación contra casos patrón.
- Informe final de resultados, conclusiones y recomendaciones.
- Acta o mecanismo de aprobación para la puesta en producción.

## 4. MARCO NORMATIVO Y METODOLÓGICO

| Referente | Aplicación en el Plan de Pruebas |
| --- | --- |
| NTC PE 1000:2020, numeral 7.7 | Establece la ejecución y documentación de pruebas a lo diseñado. |
| NTC PE 1000:2020, numeral 7.7.1 | Exige un plan que permita identificar afectaciones, mantener trazabilidad, documentar resultados y conclusiones, y conservar evidencias. |
| NTC PE 1000:2020, numerales 7.3.1 y 7.3.3 | Orienta la comprobación de reglas de validación y consistencia, y la documentación de manuales de uso y mantenimiento del software aplicativo. |
| Lineamientos para el proceso estadístico en el SEN, subproceso 3.6 | Orienta las pruebas al sistema de producción, incluidos instrumentos electrónicos, aplicativos, procesamiento y generación de resultados. |
| Lineamientos para el proceso estadístico en el SEN, subprocesos 3.7 a 3.9 | Orienta la prueba piloto, la evaluación del diseño y la construcción, y el mecanismo de aprobación para la puesta en producción. |
| Guía para la definición y la aplicación de pruebas, DANE, 2020, capítulo 5 | Define que el plan debe incluir elementos a probar, objetivos, alcance, metodología, recursos, cronograma, productos y perfiles del equipo. |

## 5. OBJETIVOS

### 5.1 Objetivo general

Definir la estrategia para verificar que la adaptación del FICED en la plataforma SIIED corresponda al diseño metodológico aprobado, aplique correctamente las reglas funcionales y de validación, preserve la integridad de los datos, reproduzca fielmente los resultados del instrumento original en Excel y permita ejecutar de manera controlada el flujo de diligenciamiento, revisión, corrección, cierre y generación de productos.

### 5.2 Objetivos específicos

- Verificar la correspondencia entre el formulario metodológico aprobado y su versión electrónica.
- Comprobar el funcionamiento de la navegación, las preguntas condicionales, las validaciones, las tablas dinámicas y las opciones excluyentes.
- Verificar el guardado, la recuperación, la integridad, la actualización y la persistencia de las respuestas, incluido el guardado parcial vía API y el guardado por sesión del wizard.
- Comprobar los permisos, estados y flujos de administración, envío, validación, devolución y corrección.
- Evaluar la comprensión, usabilidad, accesibilidad y carga de diligenciamiento del formulario.
- Verificar las salidas, exportaciones (CSV) y mecanismos de auditoría definidos para el módulo, y registrar la brecha frente a salidas previstas y no implementadas (PDF/Excel).
- Verificar el motor de medición implementado contra casos patrón obtenidos del instrumento original en Excel (doble corrida), una vez las reglas de cálculo cuenten con aprobación metodológica formal.
- Verificar la consistencia interna de las reglas de cálculo dentro del propio aplicativo (única fuente de verdad para ponderaciones y niveles de clasificación).
- Establecer los criterios de aceptación, los productos, las evidencias y el mecanismo de aprobación para la puesta en producción.

## 6. ALCANCE Y EXCLUSIONES

### 6.1 Alcance

El plan comprende las pruebas aplicables a los siguientes componentes:

- Instrumento estadístico FICED y su correspondencia conceptual con la versión electrónica.
- Formulario web tipo wizard y sus cinco módulos temáticos (A-E), distribuidos en diez pasos de navegación confirmados en el código fuente (A, B, C1-C3, D1-D4, E).
- Preguntas P1 a P42, subpreguntas, campos de especificación y reglas condicionales.
- Guardado como borrador (incluido el guardado parcial vía API desde cualquier paso), avance entre pasos, recuperación de borradores y envío definitivo.
- Flujo de estados implementado: borrador, enviado, validado y devuelto para corrección.
- Almacenamiento de respuestas por módulo en campos JSON, tablas auxiliares de personas de contacto y recurso humano, integridad y auditoría de datos.
- Regla de unicidad organismo-periodo (un formulario por organismo por vigencia).
- Panel de validación del equipo técnico SIIED: revisión, ejecución del cálculo y decisión (validar/devolver) con observaciones.
- Acceso del delegado y redirección automática según el estado del formulario.
- Exportación de resultados en formato CSV oficial y su restricción por estado y por organismo del usuario.
- Usabilidad, accesibilidad, compatibilidad, seguridad básica, rendimiento y recuperación.
- Motor automatizado de medición implementado (36 indicadores, 9 subdimensiones, 4 dimensiones, puntaje global y clasificación por nivel), en un ciclo condicionado a la aprobación metodológica de las reglas.
- Prueba piloto integral del operativo de diligenciamiento y validación.

### 6.2 Exclusiones

- La ejecución efectiva de los casos de prueba, la cual será documentada en los formatos anexos.
- La certificación de seguridad informática especializada o pruebas de penetración, salvo que sean contratadas o asignadas a un equipo competente.
- La aprobación de la metodología de cálculo del ICED, que corresponde al responsable metodológico.
- La modificación del código fuente durante la prueba; los ajustes serán gestionados por el equipo de desarrollo.
- Las exportaciones en formatos PDF y Excel, que no se encuentran implementadas en la versión actual; su eventual incorporación activará casos de prueba adicionales mediante actualización de este plan.
- La publicación de resultados oficiales obtenidos con datos de prueba o con la prueba piloto.

## 7. LÍNEA BASE Y OBJETO DE PRUEBA

### 7.1 Documentos de referencia

| Documento | Uso en el plan |
| --- | --- |
| Ficha metodológica y documento metodológico del ICED | Definición del objetivo, alcance, dimensiones, subdimensiones, preguntas y reglas metodológicas. |
| Formulario ICED vigente | Línea base del texto de preguntas, opciones, instrucciones y estructura del instrumento. |
| Instrumento original en Excel con procesamiento histórico | Línea base de comparación para los casos patrón del motor de medición (doble corrida). |
| Informe de Avance - Módulo ICED (FICED v2), febrero de 2026 | Identificación de componentes técnicos reportados: modelos, estados, persistencia, administración, exportación y propuesta de cálculo. |
| Informe de Avance - Instrumento de Captura FICED v2, abril de 2026 | Inventario de 42 preguntas, cinco módulos, diez pasos, tipos de respuesta, condicionales y persistencia. |
| Verificación técnica del código fuente del módulo (2026) | Confirmación del estado real de los componentes: motor implementado, guardado parcial, exportación CSV, panel de validación e incidencias conocidas. |
| NTC PE 1000:2020, Lineamientos SEN y Guía DANE | Criterios normativos y metodológicos para planificar, ejecutar, documentar y aprobar pruebas. |

### 7.2 Configuración verificada del objeto de prueba

| Componente | Configuración verificada en el código fuente |
| --- | --- |
| **Formulario** | FICED v2, 42 preguntas principales P1-P42. |
| **Módulos** | A. Identificación; B. Entorno institucional; C. Infraestructura; D. Metodología estadística; E. Accesibilidad y uso. |
| **Navegación** | Diez pasos confirmados: Identificación, Entorno, Infraestructura C1-C3, Metodología D1-D4, Accesibilidad. Wizard por sesión (formtools SessionWizardView). |
| **Persistencia** | Cinco grupos de respuestas JSON por módulo (respuestas_a a respuestas_e). Los pasos C1-C3 comparten el campo del módulo C y los pasos D1-D4 el del módulo D. Tablas auxiliares para personas de contacto y recurso humano (P19), materializadas al envío. |
| **Guardado parcial** | API de guardado de borrador invocable desde el wizard en cualquier paso; registra el paso actual y actualiza el campo JSON del módulo completo. |
| **Estados** | Borrador, enviado, validado y devuelto para corrección. Unicidad organismo-periodo a nivel de base de datos. |
| **Cálculo** | Motor implementado: 36 indicadores → 9 subdimensiones → 4 dimensiones → puntaje global ponderado y clasificación por nivel. Persistencia de puntajes en escala 0-1 con detalle granular en JSON. Ciclo de prueba condicionado a aprobación metodológica. |
| **Validación** | Panel del equipo técnico: revisión del formulario, ejecución del cálculo y decisión con observaciones del validador. |
| **Salidas** | Confirmación de envío (sin puntajes), vista de resultado detallado y exportación CSV oficial restringida a formularios en estado validado, con segregación por organismo para usuarios no administradores. Exportaciones PDF/Excel: **no implementadas**. |

### 7.3 Ficha de versión requerida antes de ejecutar

| Campo | Contenido a diligenciar |
| --- | --- |
| Versión funcional del formulario | |
| Fecha y hora del despliegue | |
| Ambiente y URL | |
| Versión del código / commit | |
| Base de datos de prueba | |
| Módulos habilitados | |
| Motor de cálculo habilitado | Sí (implementado; reglas pendientes de aprobación metodológica) |
| Exportaciones habilitadas | CSV (PDF/Excel no implementadas) |
| Responsable de entrega | |
| Incidencias conocidas | Ver numeral 7.4 |

### 7.4 Incidencias conocidas de la línea base

Las siguientes situaciones fueron identificadas en la verificación técnica del código fuente y deberán tratarse como hallazgos anticipados. Su existencia no invalida la ejecución del plan, pero los casos de prueba asociados deberán confirmarlas, dimensionarlas y verificar su corrección:

| ID | Descripción | Caso de prueba asociado |
| --- | --- | --- |
| IC-01 | Inconsistencia documental de ponderaciones: el modelo de datos define ICED = B×25% + C×25% + D×25% + E×25%, mientras que la definición de formularios documenta el Módulo E con peso 20%. El responsable metodológico debe dirimir la ponderación aprobada antes del Ciclo 5. | CP-M08 |
| IC-02 | Doble definición de la regla de clasificación por nivel: existe una función de determinación de nivel en el motor de cálculo y, por separado, una propiedad de nivel global en el modelo de datos con cortes 0.90/0.75/0.60. Dos fuentes de verdad para la misma regla constituyen riesgo de divergencia. | CP-M07 |
| IC-03 | El guardado parcial sobrescribe el campo JSON del módulo completo: dado que los pasos C1-C3 y D1-D4 comparten campo de almacenamiento, el guardado parcial de un paso puede eliminar respuestas previamente guardadas de otro paso del mismo módulo. | CP-P06 |
| IC-04 | La exportación CSV silencia excepciones de cálculo: un formulario con error desaparece del consolidado sin registro ni alerta, afectando la completitud del producto. | CP-I04, CP-X04 |
| IC-05 | Trazas de depuración activas en el código del wizard que vuelcan contenido de respuestas a los registros del servidor, con potencial exposición de información en logs. | CP-S04 |
| IC-06 | La brecha entre salidas previstas en informes de avance (PDF/Excel) y la salida implementada (CSV) debe resolverse formalmente: ajustar el requisito o programar el desarrollo. | CP-X01 |

## 8. ESTRATEGIA GENERAL DE PRUEBAS

La estrategia combina pruebas del instrumento estadístico, pruebas del aplicativo, la validación del motor de medición mediante doble corrida contra el instrumento original en Excel y una prueba piloto integral. Se aplicará un enfoque incremental, basado en riesgo y con trazabilidad entre cada requisito, el caso de prueba, la evidencia, el hallazgo y la nueva prueba.

### 8.1 Ciclos de prueba

| Ciclo | Contenido | Condición de inicio | Producto |
| --- | --- | --- | --- |
| Ciclo 1. Revisión documental y de escritorio | Correspondencia del instrumento, estructura, redacción, opciones, reglas, condicionales y ayudas. Incluye la resolución de las incidencias conocidas IC-01 e IC-06. | Formulario metodológico y versión electrónica identificados. | Lista de chequeo e informe de revisión. |
| Ciclo 2. Pruebas funcionales del formulario | Módulos, navegación, validaciones, tablas, guardado (sesión y parcial vía API), recuperación y envío. | Ambiente estable y usuarios de prueba. | Casos de prueba y evidencias. |
| Ciclo 3. Integración y administración | Estados, roles, panel de validación, devolución, corrección, auditoría, exportación CSV y datos. | Ciclo 2 sin defectos críticos. | Casos de integración y registro de hallazgos. |
| Ciclo 4. Usabilidad, accesibilidad y compatibilidad | Comprensión, navegación, mensajes, teclado, navegadores y carga de respuesta. | Versión funcional estable. | Informe de observación y recomendaciones. |
| Ciclo 5. Motor de medición | Puntuación por indicador, subdimensión, dimensión, resultado global, tratamiento de no aplica, clasificación, consistencia interna de las reglas y reproducibilidad, mediante doble corrida contra casos patrón del Excel original (Anexo G). | Reglas metodológicas aprobadas (incluida la resolución de IC-01 e IC-02) y motor identificado en la ficha de versión. | Informe de validación del cálculo. |
| Ciclo 6. Prueba piloto integral | Simulación del operativo completo con perfiles representativos. | Ciclos previos aprobados y manuales disponibles. | Informe de prueba piloto y recomendación. |
| Ciclo 7. Regresión y cierre | Repetición de casos afectados por ajustes y verificación final. | Correcciones desplegadas. | Informe final y mecanismo de aprobación. |

### 8.2 Enfoque basado en riesgo

Tendrán prioridad alta los casos cuya falla pueda ocasionar pérdida de información (en particular la sobrescritura entre pasos del mismo módulo, IC-03), alteración del resultado del ICED, acceso no autorizado, imposibilidad de enviar el formulario, incoherencia entre preguntas y datos almacenados, omisión silenciosa de registros en las salidas (IC-04) o generación de resultados no reproducibles.

### 8.3 Principios de ejecución

- Toda prueba debe tener un requisito y un resultado esperado identificados.
- Los datos de prueba no deben utilizar información personal real innecesaria.
- Cada hallazgo debe incluir evidencia suficiente para su reproducción.
- Los ajustes deben ser sometidos a nueva prueba y, cuando corresponda, a regresión.
- Las pruebas cognitivas y de usabilidad deben observar el comportamiento del usuario sin inducir la respuesta.
- La validación del motor de medición se realizará exclusivamente por comparación contra casos patrón aprobados; ningún resultado del motor se aceptará sin contraparte patrón.
- La prueba piloto no generará resultados oficiales ni sustituirá la medición anual del ICED.
- La salida a producción solo podrá autorizarse mediante el mecanismo de aprobación definido.

## 9. TIPOS DE PRUEBA PREVISTOS

| Código | Tipo | Objeto | Propósito |
| --- | --- | --- | --- |
| PT-01 | Prueba de escritorio | Instrumento y documentación | Revisar coherencia temática, estructura, redacción, opciones, universos, periodos y reglas. |
| PT-02 | Grupo de expertos | Instrumento y reglas | Validar pertinencia conceptual, suficiencia y consistencia con la metodología del ICED. |
| PT-03 | Entrevista cognitiva | Comprensión del formulario | Observar cómo los participantes interpretan, recuperan, deciden y registran las respuestas. |
| PT-04 | Usabilidad | Interfaz y flujo | Evaluar navegación, claridad, carga, mensajes, tablas y facilidad de diligenciamiento. |
| PT-05 | Accesibilidad | Interfaz | Comprobar operación por teclado, etiquetas, foco, contraste y comprensión de errores. |
| PT-06 | Funcional | Campos y reglas | Comprobar que cada función responda al requisito y resultado esperado. |
| PT-07 | Integración | Módulos y servicios | Comprobar interacción entre formulario, persistencia (sesión y API), estados, administración y exportación. |
| PT-08 | Integridad de datos | Base de datos | Comprobar correspondencia, completitud, conservación y actualización de respuestas en los campos JSON y las tablas auxiliares. |
| PT-09 | Roles y seguridad básica | Accesos | Verificar autenticación, autorización y restricciones por perfil y organismo, incluida la exposición de datos en registros técnicos. |
| PT-10 | Compatibilidad | Navegadores y dispositivos | Comprobar el funcionamiento en configuraciones institucionales definidas. |
| PT-11 | Rendimiento y concurrencia | Aplicativo | Medir tiempos y estabilidad bajo el volumen previsto. Umbrales sujetos a aprobación técnica. |
| PT-12 | Recuperación y contingencia | Persistencia | Comprobar la conservación de información ante interrupciones y la restauración del servicio. |
| PT-13 | Motor de medición | Cálculo | Comparar los resultados del motor con casos patrón aprobados mediante doble corrida Excel↔web. |
| PT-14 | Prueba piloto | Proceso integral | Validar el operativo completo en condiciones controladas. |
| PT-15 | Regresión | Componentes ajustados | Confirmar que las correcciones no afecten funciones previamente aprobadas. |

## 10. METODOLOGÍA DE EJECUCIÓN

### 10.1 Preparación

- Aprobar el Plan de Pruebas y la ficha de versión.
- Consolidar la matriz de requisitos funcionales y metodológicos, derivada del documento metodológico ICED, del formulario vigente y de la verificación técnica del código, con responsable y fecha asignados.
- Resolver formalmente las incidencias conocidas IC-01 (ponderación) e IC-06 (formatos de salida) o registrar su tratamiento.
- Configurar el ambiente, usuarios y datos de prueba.
- Asignar responsables y observadores.
- Capacitar al equipo en el protocolo y los formatos.
- Confirmar la disponibilidad de manuales e instructivos.

### 10.2 Ejecución de casos

- Registrar la identificación del caso, versión y precondiciones.
- Ingresar los datos definidos y ejecutar los pasos sin omitir acciones.
- Comparar el resultado observado con el resultado esperado.
- Capturar evidencia: imagen, archivo exportado, registro de base de datos o bitácora.
- Clasificar el caso como aprobado, no aprobado, bloqueado o no ejecutado.
- Registrar y asignar el hallazgo cuando exista una diferencia.

### 10.3 Revisión y nueva prueba

El equipo de desarrollo analizará los hallazgos, realizará los ajustes autorizados y entregará una nueva versión. El equipo de pruebas repetirá los casos fallidos y los casos de regresión asociados. El cierre se producirá únicamente cuando el resultado observado corresponda al esperado o cuando la instancia responsable acepte formalmente una desviación documentada.

### 10.4 Metodología específica para pruebas cognitivas y de usabilidad

Se seleccionarán participantes con perfiles similares a las personas que diligencian y validan el FICED. La sesión utilizará tareas o escenarios previamente definidos, observación directa, pensamiento en voz alta cuando sea pertinente y preguntas de sondeo posteriores. El moderador no explicará la respuesta correcta durante la tarea. El observador registrará dificultades de interpretación, navegación, recuperación de información, decisión y registro de la respuesta.

### 10.5 Metodología del ciclo del motor de medición (doble corrida)

La validación del motor implementado seguirá el protocolo del Anexo G: el responsable metodológico definirá y aprobará un conjunto de casos patrón diligenciados en el instrumento original en Excel con su procesamiento histórico; los mismos casos serán diligenciados en el FICED web; y se compararán, indicador por indicador, subdimensión por subdimensión, dimensión por dimensión y a nivel global, los resultados de ambas corridas. Toda diferencia deberá ser explicada, clasificada (defecto del motor, diferencia de redondeo, cambio metodológico autorizado) y resuelta o aceptada formalmente.

### 10.6 Metodología de la prueba piloto

La prueba piloto simulará el flujo completo: sensibilización, acceso, prevalidación, diligenciamiento, guardado, envío, revisión, devolución, corrección, validación, exportación y cálculo. La selección de organismos deberá representar diferentes niveles de complejidad, experiencia y volumen de información, e incluir como mínimo un organismo por cada nivel de capacidad observado en mediciones históricas. El tamaño definitivo será aprobado según disponibilidad operativa y diversidad de perfiles.

## 11. AMBIENTE, DATOS Y RECURSOS

### 11.1 Ambiente

| Elemento | Requisito |
| --- | --- |
| Ambiente de pruebas | Separado del ambiente productivo y con versión identificable (commit/etiqueta del código). |
| Base de datos | Exclusiva o segregada para pruebas, con respaldo y posibilidad de reinicio. |
| Usuarios | Perfiles de delegado de organismo, validador del equipo técnico, administrador y otros definidos. |
| Navegadores | Versiones institucionales aprobadas por el equipo técnico. |
| Registro técnico | Disponibilidad de logs de aplicación, errores, auditoría y transacciones cuando aplique. Las trazas de depuración deberán desactivarse o controlarse antes de la prueba piloto (IC-05). |
| Conectividad | Condiciones similares a las de los organismos participantes. |

### 11.2 Datos de prueba

- Caso mínimo: información básica y respuestas de menor complejidad.
- Caso completo: diligenciamiento de todos los campos y tablas aplicables.
- Caso condicional: combinación que active y desactive subpreguntas.
- Caso de borde: máximos de filas, longitudes, porcentajes y listas.
- Caso inválido: formatos incorrectos, campos obligatorios vacíos y opciones incompatibles.
- Caso patrón: respuestas diligenciadas y procesadas en el Excel original, con resultados aprobados por el responsable metodológico, para la doble corrida del motor (Anexo G).
- Caso de recuperación: interrupción y reingreso después del guardado.
- Caso de módulo compartido: guardado parcial de pasos distintos que comparten campo de almacenamiento (C1-C3, D1-D4), para verificar la no sobrescritura (IC-03).

### 11.3 Recursos

| Recurso | Descripción |
| --- | --- |
| Talento humano | Responsable metodológico, responsable técnico, analista QA, desarrollador, administrador, moderador, observador y participantes. |
| Tecnología | Ambiente SIIED, equipos de cómputo, navegadores, conectividad, sistema de incidencias y almacenamiento de evidencias. |
| Documentación | Formulario, ficha y documento metodológico, instrumento Excel original, informes de avance, manuales, matriz de requisitos y formatos anexos. |
| Logística | Agenda, convocatorias, sala física o virtual, acceso a participantes y mecanismos de soporte. |

## 12. ORGANIZACIÓN, ROLES Y RESPONSABILIDADES

| Rol | Responsabilidades principales |
| --- | --- |
| Responsable metodológico del ICED | Aprobar la línea base, reglas, ponderaciones, casos patrón y criterios metodológicos; dirimir las incidencias IC-01 e IC-02; validar los hallazgos que afecten el instrumento o el cálculo. |
| Responsable técnico SIIED | Entregar la versión, ambiente y documentación técnica; coordinar ajustes y respaldos; validar criterios técnicos. |
| Líder de pruebas / QA | Administrar el plan, asignar casos, controlar trazabilidad, consolidar evidencias y elaborar el informe final. |
| Ejecutor de pruebas | Aplicar los casos, registrar resultados y evidencias, y reportar hallazgos. |
| Desarrollador | Analizar y corregir defectos; documentar cambios; entregar versiones para nueva prueba. |
| Moderador | Conducir entrevistas cognitivas y sesiones de usabilidad sin inducir respuestas. |
| Observador | Registrar comportamientos, tiempos, dificultades y desviaciones del protocolo. |
| Participante / usuario | Ejecutar las tareas asignadas y aportar retroalimentación sobre comprensión y uso. |
| Instancia de aprobación | Revisar los resultados, condiciones pendientes y autorizar o negar la puesta en producción. |

## 13. CRITERIOS DE ENTRADA, SUSPENSIÓN, REANUDACIÓN Y CIERRE

### 13.1 Criterios de entrada

- Plan de Pruebas revisado y aprobado.
- Ficha de versión diligenciada, incluida la sección de incidencias conocidas.
- Formulario y documentación metodológica disponibles.
- Instrumento Excel original disponible para la generación de casos patrón (aplica al Ciclo 5).
- Ambiente de pruebas estable y accesible.
- Usuarios, roles y datos de prueba configurados.
- Matriz de requisitos y casos de prueba aprobados.
- Responsables y participantes confirmados.

### 13.2 Criterios de suspensión

- Indisponibilidad persistente del ambiente.
- Defecto crítico que impida continuar la mayoría de los casos.
- Pérdida o corrupción de datos de prueba.
- Cambio de versión no informado durante la ejecución.
- Riesgo de exposición de información personal o acceso no autorizado.
- Ausencia de la especificación necesaria para determinar el resultado esperado.

### 13.3 Criterios de reanudación

La ejecución se reanudará cuando la causa de suspensión haya sido corregida, la versión esté identificada, el ambiente haya sido estabilizado y el líder de pruebas confirme la validez de los datos y casos pendientes.

### 13.4 Criterios de cierre

- Todos los casos críticos y de prioridad alta fueron ejecutados.
- No existen hallazgos críticos abiertos.
- Los hallazgos altos fueron corregidos o aceptados formalmente con plan de tratamiento.
- Las incidencias conocidas del numeral 7.4 fueron confirmadas, corregidas o aceptadas con tratamiento documentado.
- Los casos afectados por ajustes superaron la nueva prueba y la regresión.
- Las evidencias están completas y organizadas.
- El informe final contiene resultados, conclusiones y recomendaciones.
- La instancia competente emitió el concepto de aprobación, aprobación condicionada o no aprobación.

> **Umbrales.** Los porcentajes mínimos de aprobación, tiempos de respuesta y niveles de concurrencia deberán ser definidos y aprobados antes de la ejecución. Mientras no exista esa definición, no se utilizarán umbrales arbitrarios.

## 14. GESTIÓN DE HALLAZGOS Y NO CONFORMIDADES

| Severidad | Definición |
| --- | --- |
| Crítica | Impide el diligenciamiento o envío; causa pérdida/corrupción de datos; altera el resultado del índice; permite acceso no autorizado; o bloquea el proceso integral sin alternativa. |
| Alta | Afecta una función principal, regla metodológica o flujo relevante y no existe alternativa razonable, aunque el sistema siga parcialmente disponible. |
| Media | Afecta una función secundaria, comprensión o eficiencia; existe alternativa temporal y no compromete la integridad del resultado. |
| Baja | Defecto de presentación, redacción o mejora que no impide la operación ni altera datos o resultados. |

Cada hallazgo será registrado, asignado, analizado, corregido y sometido a nueva prueba. Cuando la causa corresponda a una inconsistencia de la especificación, la decisión será tomada por el responsable metodológico o técnico, según su naturaleza, y quedará documentada. Las incidencias conocidas del numeral 7.4 ingresan al registro de hallazgos desde el inicio de la ejecución con estado *en análisis*.

## 15. TRAZABILIDAD Y EVIDENCIAS

La trazabilidad se mantendrá mediante un identificador único que relacione requisito, caso de prueba, ejecución, evidencia, hallazgo, ajuste y nueva prueba.

| Evidencia | Ejemplo |
| --- | --- |
| Captura de pantalla | Formulario, mensaje, estado, error o resultado visible. |
| Archivo | Exportación CSV, log o reporte generado. |
| Registro de datos | Consulta o extracto controlado que demuestre la persistencia y estructura JSON. |
| Bitácora técnica | Fecha, usuario, evento, excepción o transacción. |
| Matriz de doble corrida | Comparación Excel↔web por indicador, subdimensión, dimensión y global. |
| Formato de observación | Comportamientos, tiempos y dificultades del participante. |
| Acta o correo | Decisiones, aprobaciones y autorizaciones. |
| Caso de prueba diligenciado | Resultado observado, estado, evidencia y responsable. |

La carpeta de evidencias deberá organizarse por ciclo, fecha, versión y código de caso. Se conservará conforme a los controles documentales y de seguridad de la entidad.

## 16. RIESGOS DEL PLAN DE PRUEBAS

| ID | Riesgo | Nivel | Tratamiento |
| --- | --- | --- | --- |
| R-01 | Cambio del formulario durante la ejecución | Alta | Congelar la versión y registrar cambios; aplicar regresión. |
| R-02 | Reglas de cálculo sin aprobación metodológica formal pese a motor implementado | Alta | Separar el ciclo del motor; no emitir aceptación sobre cálculo hasta resolver IC-01 e IC-02 y aprobar los casos patrón. |
| R-03 | Ambiente inestable o diferente de producción | Alta | Definir configuración, monitorear y documentar diferencias. |
| R-04 | Datos de prueba insuficientes | Media | Diseñar casos mínimos, completos, inválidos, condicionales, de borde, de módulo compartido y patrón. |
| R-05 | Participantes no representativos | Media | Seleccionar perfiles y organismos con diversidad funcional y de experiencia. |
| R-06 | Pérdida de evidencias | Alta | Repositorio controlado, nomenclatura y respaldo diario. |
| R-07 | Confusión entre plan y resultados | Media | Mantener separados el Plan, los registros de ejecución y el informe final. |
| R-08 | Hallazgos sin responsable o fecha | Media | Asignación obligatoria y seguimiento periódico. |
| R-09 | Exposición de información personal | Alta | Usar datos sintéticos, limitar accesos y controlar trazas de depuración en registros del servidor (IC-05). |
| R-10 | Prueba piloto utilizada como medición oficial | Alta | Rotular bases y productos como prueba; restringir difusión. |
| R-11 | Divergencia entre reglas de clasificación duplicadas en el código (IC-02) | Alta | Exigir fuente única de verdad como condición del Ciclo 5; verificar con CP-M07. |
| R-12 | Pérdida de respuestas por sobrescritura entre pasos del mismo módulo en el guardado parcial (IC-03) | Alta | Priorizar CP-P06 en el Ciclo 2; tratar como hallazgo crítico si se confirma. |
| R-13 | Omisión silenciosa de formularios en la exportación CSV (IC-04) | Alta | Verificar completitud del consolidado con CP-X04; exigir registro o alerta ante errores de cálculo. |

## 17. CRONOGRAMA DE REFERENCIA

El siguiente cronograma se expresa en semanas relativas y deberá convertirse en fechas una vez se apruebe la disponibilidad del ambiente y del equipo.

| Periodo | Actividad | Responsable |
| --- | --- | --- |
| Semana 1 | Aprobación del plan, ficha de versión, matriz de requisitos, resolución de IC-01/IC-06 y preparación del ambiente. | Líder de pruebas / responsables metodológico y técnico |
| Semana 2 | Prueba de escritorio, grupo de expertos y configuración de datos/usuarios. | Equipo metodológico y QA |
| Semana 3 | Pruebas funcionales de módulos A, B y C; persistencia (sesión y API) y navegación. | QA / equipo técnico |
| Semana 4 | Pruebas funcionales de módulos D y E; integración, estados, exportación CSV y datos. | QA / equipo técnico |
| Semana 5 | Usabilidad, accesibilidad, compatibilidad, recuperación y prueba piloto controlada. | Moderador, observadores y usuarios |
| Semana 6 | Correcciones, nueva prueba, regresión, consolidación e informe final. | Equipo ICED-SIIED |
| Ciclo condicionado | Validación del motor de medición mediante doble corrida, una vez aprobadas las reglas metodológicas. | Metodología, QA y desarrollo |

## 18. PRODUCTOS ESPERADOS

| Código | Producto |
| --- | --- |
| P-01 | Plan de Pruebas aprobado. |
| P-02 | Ficha de versión y matriz de requisitos. |
| P-03 | Matriz de trazabilidad. |
| P-04 | Casos de prueba diligenciados. |
| P-05 | Repositorio de evidencias. |
| P-06 | Registro de hallazgos y acciones correctivas, incluido el tratamiento de las incidencias conocidas. |
| P-07 | Informe de prueba de escritorio y grupo de expertos. |
| P-08 | Informe de entrevistas cognitivas, usabilidad y accesibilidad. |
| P-09 | Informe de prueba piloto. |
| P-10 | Informe de validación del motor de medición con matriz de doble corrida Excel↔web. |
| P-11 | Informe final de pruebas, conclusiones y recomendaciones. |
| P-12 | Mecanismo de aprobación para la puesta en producción. |

## 19. MECANISMO DE APROBACIÓN

Concluidos los ciclos aplicables, el líder de pruebas presentará el informe final y la matriz de hallazgos a las instancias metodológica y técnica. La decisión se registrará en acta o formato de aprobación con una de las siguientes categorías:

- **Aprobado para producción:** no existen hallazgos críticos o altos abiertos y se cumplen los criterios de cierre.
- **Aprobado con condiciones:** existen asuntos no críticos con tratamiento, responsable y fecha acordados, sin impacto sobre la integridad del instrumento o los resultados.
- **No aprobado:** persisten defectos que impiden la operación segura, íntegra o metodológicamente válida.
- **No evaluable:** no fue posible determinar el resultado por falta de versión, especificación, acceso o evidencia suficiente.

| Concepto final | Justificación | Condiciones / pendientes | Responsables | Firmas / fecha |
| --- | --- | --- | --- | --- |
| | | | | |

## 20. REFERENCIAS

- Departamento Administrativo Nacional de Estadística (DANE) e ICONTEC. (2020). *Norma Técnica de la Calidad del Proceso Estadístico.* NTC PE 1000:2020.
- Departamento Administrativo Nacional de Estadística (DANE). (2020). *Lineamientos para el proceso estadístico en el Sistema Estadístico Nacional.* Versión 2.0.
- Departamento Administrativo Nacional de Estadística (DANE). (2020). *Guía para la definición y la aplicación de pruebas en las operaciones estadísticas.* Versión 2.
- Alcaldía de Santiago de Cali, Departamento Administrativo de Planeación. *Documento metodológico del Índice de Capacidad Estadística Distrital (ICED).*
- Alcaldía de Santiago de Cali, SIIED. (2026). *Informe de Avance - Módulo ICED (FICED v2).*
- Alcaldía de Santiago de Cali, SIIED. (2026). *Informe de Avance - Instrumento de Captura FICED v2.*
- Alcaldía de Santiago de Cali, SIIED. (2026). *Verificación técnica del código fuente del módulo FICED v2.*

---

## ANEXO A. MATRIZ DE TRAZABILIDAD NORMATIVA Y FUNCIONAL

| ID | Fuente | Requisito | Prueba asociada | Evidencia prevista |
| --- | --- | --- | --- | --- |
| N-01 | NTC PE 1000:2020, 7.7 | Ejecutar y documentar pruebas a lo diseñado. | Todos los ciclos | Plan, casos e informes |
| N-02 | NTC PE 1000:2020, 7.7.1 a) | Identificar afectaciones en el desarrollo de la operación. | Registro de hallazgos | Matriz de hallazgos |
| N-03 | NTC PE 1000:2020, 7.7.1 b) | Mantener trazabilidad sobre actividades, métodos, instrumentos y software. | Todos los casos | Matriz de trazabilidad |
| N-04 | NTC PE 1000:2020, 7.7.1 c-d | Documentar resultados y conclusiones; conservar evidencia. | Cierre | Informes y repositorio |
| N-05 | Lineamientos SEN, 3.6 | Comprobar instrumentos electrónicos y sistema de producción. | Funcional e integración | Casos y evidencias |
| N-06 | Lineamientos SEN, 3.7 | Definir y aplicar prueba piloto y observación estandarizada. | Piloto | Protocolo e informe |
| N-07 | Lineamientos SEN, 3.8 | Evaluar el diseño y la construcción con base en resultados. | Cierre | Informe de evaluación |
| N-08 | Lineamientos SEN, 3.9 | Establecer mecanismo de aprobación para producción. | Aprobación | Acta o formato firmado |
| F-01 | Informe captura 2026 / código verificado | 42 preguntas en cinco módulos y diez pasos. | Funcional y escritorio | Casos por módulo |
| F-02 | Informe captura 2026 / código verificado | Mínimo una persona de contacto con campos obligatorios. | Funcional módulo A | CP-A01 a CP-A03 |
| F-03 | Informe captura 2026 | Reglas condicionales, opciones excluyentes y tablas dinámicas. | Funcional | CP-B/C/D/E |
| F-04 | Informe captura 2026 / código verificado | Guardado borrador (sesión y API parcial), guardado al avanzar y envío definitivo. | Persistencia | CP-P01 a CP-P06 |
| F-05 | Informe módulo 2026 / código verificado | Estados (borrador/enviado/validado/devuelto) y panel de validación/devolución. | Integración | CP-W01 a CP-W04 |
| F-06 | Código verificado | Exportación CSV oficial restringida por estado y organismo; auditoría de fechas, usuario y observaciones. | Integración y datos | CP-X01, CP-X03, CP-X04 |
| F-07 | Documento metodológico ICED | Correspondencia de variables, preguntas y dimensiones. | Escritorio y expertos | CP-E01 a CP-E06 |
| F-08 | Metodología de cálculo aprobada / motor implementado | Puntajes por indicador, agregación, ponderaciones, no aplica y clasificación. | Motor | CP-M01 a CP-M08 |
| F-09 | Código verificado | Materialización de tablas auxiliares (personas de contacto y RRHH) coherente con las respuestas JSON. | Integración | CP-I03 |
| F-10 | Código verificado | Unicidad organismo-periodo y redirección del delegado según estado. | Integración | CP-P05, CP-W05 |

## ANEXO B. INVENTARIO INICIAL DE CASOS DE PRUEBA

| ID | Componente | Caso previsto | Tipo | Prioridad | Resultado esperado | Evidencia | Ciclo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CP-E01 | Instrumento | Correspondencia entre preguntas del formulario aprobado y la versión web. | Escritorio | Alta | No existen omisiones, duplicidades ni cambios no autorizados. | Lista de chequeo | 1 |
| CP-E02 | Instrumento | Orden de módulos, pasos y numeración P1-P42. | Escritorio | Alta | La secuencia corresponde a la ficha de versión aprobada. | Capturas y matriz | 1 |
| CP-E03 | Instrumento | Opciones de respuesta, escalas y campos "Otro/Especifique". | Escritorio | Alta | Las opciones y ayudas corresponden al instrumento aprobado. | Lista de chequeo | 1 |
| CP-E04 | Instrumento | Reglas condicionales y preguntas no aplicables. | Escritorio | Alta | Cada regla tiene condición, acción y tratamiento definido. | Matriz de reglas | 1 |
| CP-E05 | Instrumento | Claridad de definiciones, instrucciones y periodos de referencia. | Expertos | Media | Los términos son comprensibles y consistentes. | Acta/informe | 1 |
| CP-E06 | Instrumento | Carga y disponibilidad de información solicitada. | Expertos | Media | La información puede ser suministrada por los perfiles previstos. | Acta/informe | 1 |
| CP-E07 | Instrumento | Resolución documental de la ponderación del Módulo E (IC-01). | Escritorio | Alta | Existe una única ponderación aprobada y consignada en la documentación metodológica y el código. | Acta metodológica | 1 |
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
| CP-D01 | Módulo D | P23: carga y edición de operaciones estadísticas. | Funcional | Alta | Las filas se cargan para el organismo y conservan las nueve columnas definidas. | Capturas/datos | 2 |
| CP-D02 | Módulo D | P24: nomenclaturas y subtablas condicionales. | Funcional | Alta | Las subtablas se despliegan y validan según la selección. | Capturas | 2 |
| CP-D03 | Módulo D | P25: subcampos de proyectos y otros mecanismos. | Funcional | Media | Los campos se muestran solo ante las opciones correspondientes. | Capturas | 2 |
| CP-D04 | Módulo D | P27-P28: articulación y preguntas asociadas. | Funcional | Alta | Las preguntas dependientes siguen la condición aprobada. | Capturas | 2 |
| CP-D05 | Módulo D | Tablas y listas de observatorios/políticas. | Funcional | Media | Las opciones se cargan, seleccionan y conservan sin duplicidad. | Capturas/datos | 2 |
| CP-EA01 | Módulo E | Validación de preguntas de disponibilidad, uso, difusión y accesibilidad. | Funcional | Alta | Cada tipo de respuesta y condicional se comporta conforme a la especificación. | Capturas/datos | 2 |
| CP-EA02 | Módulo E | URLs, matrices y campos de satisfacción. | Funcional negativo | Media | Valida formatos y conserva la estructura de la matriz. | Capturas/datos | 2 |
| CP-P01 | Persistencia | Guardar borrador en cualquier paso mediante la API de guardado parcial. | Integración | Crítica | La información queda almacenada sin cambiar a enviado y registra el paso actual. | Captura/datos/log | 2 |
| CP-P02 | Persistencia | Guardado automático al avanzar. | Integración | Crítica | Al presionar Siguiente se conserva el paso actual antes de navegar. | Datos/log | 2 |
| CP-P03 | Persistencia | Cerrar sesión y reanudar el diligenciamiento. | Recuperación | Crítica | El usuario recupera el último borrador íntegro, incluidas las tablas auxiliares precargadas (contactos y RRHH). | Capturas/datos | 2 |
| CP-P04 | Persistencia | Interrupción de red durante el guardado. | Contingencia | Alta | No se corrompen respuestas y el usuario recibe un mensaje controlado. | Video/log | 4 |
| CP-P05 | Persistencia | Unicidad organismo-periodo. | Integridad | Alta | No se crean formularios duplicados para el mismo organismo y periodo, incluso ante guardado parcial y wizard simultáneos. | Consulta de datos | 3 |
| CP-P06 | Persistencia | Guardado parcial de pasos que comparten campo de módulo (C1-C3 y D1-D4). | Integridad negativa | Crítica | El guardado parcial de un paso no elimina ni sobrescribe las respuestas previamente guardadas de otro paso del mismo módulo (IC-03). | Consulta de datos | 2 |
| CP-W01 | Flujo | Envío definitivo con validación completa. | Integración | Crítica | Solo envía cuando todos los campos aplicables cumplen reglas; el estado pasa a enviado y se registra la fecha de envío. | Captura/log | 3 |
| CP-W02 | Flujo | Transición borrador-enviado-validado. | Integración | Crítica | Cada transición sigue los permisos y registra fechas de envío y validación. | Capturas/datos | 3 |
| CP-W03 | Flujo | Devolución para corrección y observaciones del validador. | Integración | Alta | El organismo visualiza las observaciones y puede corregir lo autorizado. | Capturas/datos | 3 |
| CP-W04 | Flujo | Restricción de edición después de validación. | Seguridad funcional | Alta | El formulario validado no se modifica sin procedimiento autorizado. | Captura/log | 3 |
| CP-W05 | Flujo | Redirección del delegado según estado del formulario. | Integración | Media | El acceso del delegado dirige a crear nuevo, retomar borrador o consultar resultado según el estado del formulario de su organismo y periodo. | Capturas | 3 |
| CP-W06 | Flujo | Confirmación de envío sin exposición de puntajes. | Integración | Media | La confirmación no muestra puntajes; el resultado se expone únicamente tras la validación conforme al procedimiento. | Capturas | 3 |
| CP-I01 | Datos | Correspondencia entre respuesta visible y JSON almacenado. | Integridad | Crítica | Los datos almacenados corresponden exactamente a la respuesta, incluido el manejo de prefijos de paso. | Consulta controlada | 3 |
| CP-I02 | Datos | Caracteres especiales, tildes, longitud y saltos de línea. | Integridad de borde | Media | La información se conserva sin truncamiento o corrupción. | Datos/exportación | 3 |
| CP-I03 | Datos | Materialización de registros auxiliares de RRHH/contactos al envío. | Integración | Alta | Los registros auxiliares coinciden con la información del formulario; la estrategia de borrado y recreación no genera pérdidas ni duplicados. | Consulta de datos | 3 |
| CP-I04 | Datos | Tratamiento de errores de cálculo en la generación del consolidado. | Integridad negativa | Alta | Un formulario con error de cálculo no desaparece silenciosamente del consolidado; se registra o alerta la omisión (IC-04). | Log/consulta | 3 |
| CP-X01 | Salidas | Exportación CSV oficial: estructura de encabezados, dimensiones, subdimensiones e indicadores. | Funcional | Alta | El archivo incluye el encabezado oficial y las filas con identificación, periodo y porcentajes definidos. Se registra formalmente la brecha PDF/Excel (IC-06). | Archivo CSV | 3 |
| CP-X02 | Salidas | Filtro de exportación por periodo. | Funcional | Media | El parámetro de periodo limita correctamente los formularios incluidos. | Archivo CSV | 3 |
| CP-X03 | Auditoría | Registro de usuario, fechas, estados y observaciones. | Integración | Alta | La trazabilidad de eventos está disponible según la especificación. | Log/consulta | 3 |
| CP-X04 | Salidas | Restricción de la exportación por estado y por organismo. | Seguridad funcional | Alta | Solo se exportan formularios validados; los usuarios no administradores solo obtienen los de su organismo; el consolidado es completo respecto de los formularios elegibles (IC-04). | Archivo CSV/datos | 3 |
| CP-S01 | Seguridad | Acceso autenticado y segregación por organismo. | Seguridad básica | Crítica | Un usuario no accede a formularios de otro organismo. | Captura/log | 3 |
| CP-S02 | Seguridad | Permisos del validador y administrador. | Seguridad funcional | Alta | Cada rol ejecuta únicamente las acciones autorizadas. | Capturas | 3 |
| CP-S03 | Seguridad | Acceso directo mediante URL no autorizada (confirmación, resultado, retomar borrador de otro organismo). | Seguridad básica | Crítica | El sistema rechaza el acceso y no expone datos. | Captura/log | 3 |
| CP-S04 | Seguridad | Contenido de respuestas en registros técnicos del servidor. | Seguridad básica | Alta | Los registros del servidor no exponen contenido de respuestas ni datos personales por trazas de depuración (IC-05). | Revisión de logs | 3 |
| CP-U01 | Usabilidad | Comprensión de etiquetas, instrucciones y mensajes. | Cognitiva/usabilidad | Alta | Los participantes interpretan y completan las tareas sin ayuda indebida. | Formato observación | 4 |
| CP-U02 | Usabilidad | Navegación, progreso y retorno entre pasos. | Usabilidad | Media | El usuario identifica dónde está y puede avanzar/retroceder sin perder datos. | Formato observación | 4 |
| CP-U03 | Usabilidad | Uso de tablas complejas y dinámicas. | Usabilidad | Alta | Los participantes agregan y editan filas correctamente. | Video/notas | 4 |
| CP-A11Y01 | Accesibilidad | Operación por teclado y foco visible. | Accesibilidad | Media | Todos los controles esenciales son operables por teclado. | Lista de chequeo | 4 |
| CP-A11Y02 | Accesibilidad | Etiquetas, errores y contraste. | Accesibilidad | Media | Los campos y errores son identificables y comprensibles. | Lista/capturas | 4 |
| CP-COMP01 | Compatibilidad | Navegadores institucionales. | Compatibilidad | Alta | El formulario mantiene funciones y presentación en las versiones aprobadas. | Capturas | 4 |
| CP-R01 | Rendimiento | Carga, guardado y envío bajo volumen previsto. | Rendimiento | Media | Cumple los umbrales técnicos aprobados. | Medición/log | 4 |
| CP-M01 | Motor | Puntuación por indicador individual (36 indicadores). | Cálculo | Crítica | Cada respuesta obtiene el valor aprobado, verificado contra el caso patrón del Excel original. | Matriz de doble corrida | 5 |
| CP-M02 | Motor | Agregación por subdimensión (9) y dimensión (4). | Cálculo | Crítica | Los resultados coinciden con la herramienta patrón. | Matriz de doble corrida | 5 |
| CP-M03 | Motor | Ponderación y puntaje global. | Cálculo | Crítica | La fórmula y los pesos aprobados (resueltos en IC-01) se aplican sin desviación. | Matriz de doble corrida | 5 |
| CP-M04 | Motor | Tratamiento de no aplica y condicionales ocultos, por dimensión. | Cálculo | Crítica | No altera indebidamente denominadores ni puntajes en ninguna de las cuatro dimensiones. | Casos patrón | 5 |
| CP-M05 | Motor | Clasificación por nivel, límites y redondeo, incluida la conversión de escalas (0-100 del cálculo a 0-1 de la persistencia). | Cálculo de borde | Alta | Los límites, redondeos y conversiones de escala coinciden con la regla aprobada en todas las vistas y salidas. | Casos límite | 5 |
| CP-M06 | Motor | Reproducibilidad histórica. | Regresión | Alta | La misma entrada y la misma versión del motor (commit identificado) producen el mismo resultado. | Comparación histórica | 5 |
| CP-M07 | Motor | Consistencia de la regla de clasificación entre el motor de cálculo y el modelo de datos. | Cálculo | Crítica | Existe una única fuente de verdad para los niveles de capacidad; el nivel mostrado es idéntico en toda vista, modelo y exportación (IC-02). | Consulta/capturas | 5 |
| CP-M08 | Motor | Verificación de la ponderación del Módulo E implementada frente a la aprobada. | Cálculo | Crítica | La ponderación implementada corresponde a la resolución formal de IC-01; no subsisten referencias contradictorias. | Matriz de doble corrida/código | 5 |
| CP-PI01 | Proceso integral | Diligenciamiento de extremo a extremo. | Prueba piloto | Crítica | El proceso completo puede ejecutarse con los perfiles, tiempos y soportes definidos. | Informe piloto | 6 |

## ANEXO C. FORMATO DE CASO DE PRUEBA

| Campo | Registro |
| --- | --- |
| **ID del caso** | |
| **Nombre** | |
| **Versión / ambiente** | |
| **Requisito asociado** | |
| **Tipo y prioridad** | |
| **Precondiciones** | |
| **Datos de prueba** | |
| **Pasos de ejecución** | 1. 2. 3. |
| **Resultado esperado** | |
| **Resultado observado** | |
| **Evidencia** | |
| **Estado** | Aprobado / No aprobado / Bloqueado / No ejecutado |
| **Hallazgo asociado** | |
| **Ejecutor / fecha** | |
| **Responsable de validación** | |
| **Observaciones** | |

## ANEXO D. FORMATO DE OBSERVACIÓN

| Campo | Registro |
| --- | --- |
| **Sesión / fecha** | |
| **Versión** | |
| **Perfil del participante** | |
| **Escenario o tareas** | |
| **Tiempo total** | |
| **Dificultades de comprensión** | |
| **Dificultades de recuperación de información** | |
| **Dificultades de navegación o registro** | |
| **Mensajes o ayudas requeridas** | |
| **Errores observados** | |
| **Comentarios del participante** | |
| **Recomendaciones** | |
| **Moderador / observador** | |

## ANEXO E. FORMATO DE REGISTRO DE HALLAZGOS

| Campo | Registro |
| --- | --- |
| **ID del hallazgo** | |
| **Fecha y versión** | |
| **Caso de prueba** | |
| **Requisito afectado** | |
| **Descripción** | |
| **Resultado esperado** | |
| **Resultado observado** | |
| **Evidencia** | |
| **Severidad** | Crítica / Alta / Media / Baja |
| **Impacto metodológico** | |
| **Impacto operativo** | |
| **Impacto tecnológico** | |
| **Responsable de análisis** | |
| **Acción correctiva** | |
| **Fecha compromiso** | |
| **Estado** | Abierto / En análisis / Corregido / En nueva prueba / Cerrado / Aceptado |
| **Resultado de nueva prueba** | |
| **Cierre y aprobación** | |

## ANEXO F. ESTRUCTURA DEL INFORME DE RESULTADOS

- Identificación de la versión y el ambiente probado.
- Objetivo, alcance y pruebas ejecutadas.
- Equipo participante y fechas.
- Resumen de casos: aprobados, no aprobados, bloqueados y no ejecutados.
- Resultados por tipo de prueba y componente.
- Hallazgos por severidad y estado, incluido el tratamiento de las incidencias conocidas del numeral 7.4.
- Ajustes efectuados y pruebas de regresión.
- Resultados de la doble corrida del motor de medición, cuando aplique.
- Limitaciones de la ejecución.
- Conclusiones sobre el funcionamiento del instrumento y el sistema.
- Recomendaciones y asuntos pendientes.
- Concepto de aprobación para producción.
- Anexos de evidencias, actas y matrices.

## ANEXO G. PROTOCOLO DE DOBLE CORRIDA PARA CASOS PATRÓN DEL MOTOR DE MEDICIÓN

### G.1 Propósito

Garantizar la continuidad metodológica de la serie del ICED verificando que el motor de medición implementado en el SIIED reproduce los resultados del instrumento original en Excel con su procesamiento histórico, o que toda diferencia corresponde a un cambio metodológico formalmente autorizado.

### G.2 Preparación de los casos patrón

| Paso | Actividad | Responsable |
| --- | --- | --- |
| 1 | Congelar la versión del Excel original y su código de procesamiento como línea base de comparación. | Responsable metodológico |
| 2 | Definir el conjunto de casos patrón. Mínimo sugerido: un caso mínimo, un caso completo, un caso con condicionales inactivos por dimensión, un caso en cada límite de nivel de clasificación y, cuando exista, al menos un caso real anonimizado de una medición histórica. | Responsable metodológico y QA |
| 3 | Diligenciar y procesar cada caso en el Excel original; documentar los resultados por indicador, subdimensión, dimensión, global y nivel. | Responsable metodológico |
| 4 | Aprobar formalmente los casos patrón y sus resultados esperados mediante acta. | Instancia metodológica |

### G.3 Ejecución de la doble corrida

| Paso | Actividad | Responsable |
| --- | --- | --- |
| 1 | Diligenciar cada caso patrón en el FICED web sobre la versión identificada en la ficha de versión. | Ejecutor de pruebas |
| 2 | Ejecutar el cálculo desde el panel de validación y registrar los resultados persistidos. | Ejecutor de pruebas |
| 3 | Diligenciar la matriz comparativa: 36 indicadores, 9 subdimensiones, 4 dimensiones, puntaje global y nivel, para cada caso. | QA |
| 4 | Clasificar cada diferencia como: defecto del motor, diferencia de redondeo/escala, o cambio metodológico autorizado con soporte documental. | Responsable metodológico y QA |
| 5 | Gestionar como hallazgo toda diferencia clasificada como defecto; repetir la doble corrida tras la corrección. | Desarrollador y QA |

### G.4 Criterio de aceptación del ciclo

El Ciclo 5 se considera aprobado cuando la totalidad de los casos patrón produce resultados idénticos entre ambas corridas, o cuando las diferencias remanentes se encuentran clasificadas, documentadas y formalmente aceptadas por la instancia metodológica. No se admite aceptación parcial sin acta.

> **Cierre del documento.** La aprobación de este Plan de Pruebas autoriza su ejecución, no la puesta en producción del FICED. La puesta en producción requerirá la ejecución documentada de los ciclos aplicables y el concepto final de las instancias responsables.

---
*Documento de planificación - Versión 1.1 | Página 1*
