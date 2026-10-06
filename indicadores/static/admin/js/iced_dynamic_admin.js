/**
 * Admin dinámico para ICED Preguntas y Respuestas
 * Muestra/oculta campos según el tipo de pregunta/respuesta seleccionado
 */
(function($) {
    'use strict';
    
    $(document).ready(function() {
        // ========== PARA ICEDPREGUNTA ==========
        function updatePreguntaFields() {
            var tipoRespuesta = $('#id_tipo_respuesta').val();
            
            // Tipos que necesitan opciones
            var tiposConOpciones = [
                'opcion_multiple',
                'opcion_multiple_detalle', 
                'checkbox_multiple',
                'checkbox_tabla'
            ];
            
            // Mostrar/ocultar sección de opciones
            if (tiposConOpciones.includes(tipoRespuesta)) {
                $('.field-opciones').show();
                $('#id_opciones_from').prop('disabled', false);
                $('#id_opciones_to').prop('disabled', false);
            } else {
                $('.field-opciones').hide();
                $('#id_opciones_from').prop('disabled', true);
                $('#id_opciones_to').prop('disabled', true);
            }
        }
        
        // Ejecutar al cargar y al cambiar
        if ($('#id_tipo_respuesta').length) {
            updatePreguntaFields();
            $('#id_tipo_respuesta').on('change', updatePreguntaFields);
        }
        
    });
})(django.jQuery);

