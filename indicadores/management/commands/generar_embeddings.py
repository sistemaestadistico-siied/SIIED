# management/commands/generar_embeddings.py
from django.core.management.base import BaseCommand
from indicadores.embeddings import EmbeddingService
from indicadores.models import Indicador, DocumentoVector
from django.db import connection, transaction
import json
import re

class Command(BaseCommand):
    help = 'Genera o actualiza los embeddings para búsqueda semántica'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Tamaño del lote para procesar indicadores'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar regeneración de todos los embeddings'
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Iniciando generación de embeddings...')
        
        # Crear la extensión vector si no existe
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE EXTENSION IF NOT EXISTS vector;
                CREATE TABLE IF NOT EXISTS indicadores_documentovector (
                    id SERIAL PRIMARY KEY,
                    tipo VARCHAR(20),
                    referencia_id INTEGER,
                    contenido TEXT,
                    embedding vector(384),
                    metadata JSONB,
                    fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_documentovector_embedding 
                ON indicadores_documentovector USING ivfflat (embedding vector_cosine_ops);
            """)
        
        # Inicializar el servicio de embeddings
        service = EmbeddingService()
        
        if not service.model:
            self.stderr.write(
                self.style.ERROR('No se pudo inicializar el modelo de embeddings')
            )
            return
        
        try:
            batch_size = options['batch_size']
            force = options['force']
            
            # Obtener indicadores a procesar
            if force:
                indicadores = Indicador.objects.all()
                self.stdout.write(f'Procesando todos los indicadores ({indicadores.count()})')
            else:
                # Solo procesar indicadores sin embedding o actualizados recientemente
                indicadores_con_embedding = DocumentoVector.objects.filter(
                    tipo='indicador'
                ).values_list('referencia_id', flat=True)
                indicadores = Indicador.objects.exclude(id__in=indicadores_con_embedding)
                self.stdout.write(f'Procesando {indicadores.count()} indicadores sin embeddings')
            
            total = indicadores.count()
            procesados = 0
            errores = 0
            
            # Procesar en lotes
            for i in range(0, total, batch_size):
                batch = indicadores[i:i+batch_size]
                
                with transaction.atomic():
                    for indicador in batch:
                        try:
                            # Construir el contenido para el embedding
                            contenido_parts = [
                                f"Nombre: {indicador.nombre}",
                            ]
                            
                            # Códigos e identificadores
                            if indicador.codigo_indicador:
                                contenido_parts.append(f"Código: {indicador.codigo_indicador}")
                            
                            if indicador.sigla:
                                contenido_parts.append(f"Sigla: {indicador.sigla}")
                            
                            # Definiciones y conceptos (sin HTML tags)
                            if indicador.descripcion_indicador:
                                # Remover tags HTML y limitar a 200 caracteres
                                def_limpio = re.sub(r'<[^>]+>', '', str(indicador.descripcion_indicador))
                                def_limpio = def_limpio[:200] + "..." if len(def_limpio) > 200 else def_limpio
                                contenido_parts.append(f"Definiciones: {def_limpio}")
                            
                            # Objetivo (sin HTML tags si es CKEditor)
                            if indicador.objetivo:
                                # Remover tags HTML básicos
                                objetivo_limpio = re.sub(r'<[^>]+>', '', str(indicador.objetivo))
                                objetivo_limpio = objetivo_limpio[:150] + "..." if len(objetivo_limpio) > 150 else objetivo_limpio
                                contenido_parts.append(f"Objetivo: {objetivo_limpio}")
                            
                            # Justificación (sin HTML tags)
                            if indicador.comentarios_adicionales:
                                comentarios_limpio = re.sub(r'<[^>]+>', '', str(indicador.comentarios_adicionales))
                                comentarios_limpio = comentarios_limpio[:150] + "..." if len(comentarios_limpio) > 150 else comentarios_limpio
                                contenido_parts.append(f"Comentarios adicionales: {comentarios_limpio}")
                            
                            # Unidad de medida
                            if indicador.unidad_medida:
                                contenido_parts.append(f"Unidad: {indicador.unidad_medida}")
                            
                            # Fuente de datos
                            if indicador.fuente_datos:
                                contenido_parts.append(f"Fuente: {indicador.fuente_datos}")
                            
                            # Desagregaciones (texto descriptivo)
                            if indicador.alcance_tematico:
                                contenido_parts.append(f"Alcance temático: {indicador.alcance_tematico[:100]}")
                            
                            if indicador.cobertura_geografica:
                                contenido_parts.append(f"Cobertura geográfica: {indicador.cobertura_geografica[:100]}")
                            
                            # Agregar información jerárquica
                            if hasattr(indicador, 'subtema') and indicador.subtema:
                                contenido_parts.append(f"Subtema: {indicador.subtema.nombre}")
                                if hasattr(indicador.subtema, 'tema') and indicador.subtema.tema:
                                    contenido_parts.append(f"Tema: {indicador.subtema.tema.nombre}")
                                    if hasattr(indicador.subtema.tema, 'dominio') and indicador.subtema.tema.dominio:
                                        contenido_parts.append(f"Dominio: {indicador.subtema.tema.dominio.nombre}")
                            # Subtemas adicionales (M2M): el indicador también es
                            # encontrable por sus otras clasificaciones
                            for st in indicador.subtemas_adicionales.select_related('tema__dominio'):
                                contenido_parts.append(f"Subtema adicional: {st.nombre}")
                                if st.tema:
                                    contenido_parts.append(f"Tema: {st.tema.nombre}")
                                    if st.tema.dominio:
                                        contenido_parts.append(f"Dominio: {st.tema.dominio.nombre}")
                            
                            contenido = " | ".join(contenido_parts)
                            
                            # Generar embedding
                            embedding = service.get_embedding(contenido)
                            
                            if embedding:
                                # Crear o actualizar el documento vector
                                metadata = {
                                    'nombre': indicador.nombre,
                                    'unidad_medida': indicador.unidad_medida or '',
                                }
                                
                                # Savepoint propio: un fallo no contamina el batch
                                with transaction.atomic():
                                    if force:
                                        # Eliminar embedding existente si existe
                                        DocumentoVector.objects.filter(
                                            tipo='indicador',
                                            referencia_id=indicador.id
                                        ).delete()

                                    DocumentoVector.objects.create(
                                        tipo='indicador',
                                        referencia_id=indicador.id,
                                        contenido=contenido,
                                        embedding=embedding,
                                        metadata=metadata
                                    )
                                
                                procesados += 1
                                
                                if procesados % 10 == 0:
                                    self.stdout.write(f'Procesados: {procesados}/{total}')
                            else:
                                errores += 1
                                self.stderr.write(
                                    self.style.WARNING(
                                        f'No se pudo generar embedding para indicador {indicador.id}: {indicador.nombre}'
                                    )
                                )
                                
                        except Exception as e:
                            errores += 1
                            self.stderr.write(
                                self.style.ERROR(
                                    f'Error procesando indicador {indicador.id}: {str(e)}'
                                )
                            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n¡Indicadores completados!\n'
                    f'Procesados: {procesados}\n'
                    f'Errores: {errores}\n'
                    f'Total: {total}'
                )
            )

            # ================================================================
            # INDEXAR MÓDULOS EXTENDIDOS (Productos Académicos + Infraestructura)
            # ================================================================
            self.stdout.write('\n--- Indexando módulos extendidos ---')
            res_pa = service.indexar_productos_academicos(force=force)
            self.stdout.write(
                f"  Productos académicos: {res_pa.get('procesados', 0)}/{res_pa.get('total', 0)}"
            )
            res_doc = service.indexar_documentos_infraestructura(force=force)
            self.stdout.write(
                f"  Documentos infraestructura: {res_doc.get('procesados', 0)}/{res_doc.get('total', 0)}"
            )
            res_cat = service.indexar_catalogo_consulta(force=force)
            self.stdout.write(
                f"  Catálogo de consulta: {res_cat.get('procesados', 0)}/{res_cat.get('total', 0)}"
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n¡Proceso global completado!'
                )
            )

        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'Error al generar embeddings: {str(e)}')
            )
            raise
