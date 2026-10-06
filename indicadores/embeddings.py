# services/embeddings.py
import numpy as np
from sentence_transformers import SentenceTransformer
from django.db import transaction
from indicadores.models import DocumentoVector, Indicador
import os
from pathlib import Path
import logging
import json
from datetime import date, datetime
from typing import Optional, List, Dict, Any


logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)

class EmbeddingService:
    def __init__(self, model_name='all-MiniLM-L6-v2', local_model_path=None):
        self.model = None
        self.model_name = model_name
        self.local_model_path = local_model_path or os.path.join(Path.home(), '.cache', 'sentence-transformers', model_name)
        
        try:
            # Try to load from local path first
            if os.path.exists(self.local_model_path):
                self.log(f"Loading model from local path: {self.local_model_path}", 'info')
                self.model = SentenceTransformer(self.local_model_path)
            else:
                # Fall back to online download with timeout
                self.log(f"Downloading model {model_name}...", 'info')
                self.model = SentenceTransformer(model_name)
                # Save the model locally for future use
                os.makedirs(self.local_model_path, exist_ok=True)
                self.model.save(self.local_model_path)
        except Exception as e:
            self.log(f"Failed to load model: {e}", 'error')
            self.model = None

    def log(self, message, level='info'):
        """Método de registro flexible"""
        if hasattr(logger, level) and callable(getattr(logger, level)):
            getattr(logger, level)(message)
        else:
            print(f"[{level.upper()}] {message}")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Obtiene el embedding para un texto dado.
        
        Args:
            text: Texto a convertir en embedding
            
        Returns:
            Lista de floats con el embedding o None en caso de error
        """
        if not text or not isinstance(text, str):
            return None
            
        try:
            # Si el modelo es un callable (como los de sentence-transformers)
            if callable(self.model):
                # Asegurarse de que el texto sea una cadena
                text = str(text).strip()
                if not text:
                    return None
                    
                # Obtener el embedding
                embedding = self.model.encode(text)
                
                # Asegurarse de que el resultado sea una lista de números
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()  # Convertir numpy array a lista
                elif not isinstance(embedding, list):
                    return None
                    
                return embedding
                
            return None
            
        except Exception as e:
            logger.error(f"Error al generar embedding: {str(e)}")
            return None

    def search_relevant_data(self, query, top_k=5, threshold=0.6):
        """Search for relevant data using embeddings - AÑADIDO threshold"""
        try:
            if not query or not self.model:
                return {"results": [], "error": "Model not initialized"}

            # Generate query embedding
            query_embedding = self.get_embedding(query)
            if not query_embedding:
                return {"results": [], "error": "Failed to generate query embedding"}

            # Search in DocumentoVector
            results = []
            for doc in DocumentoVector.objects.all():
                try:
                    # Get the embedding - prefer the embedding field if available, otherwise use vector
                    if hasattr(doc, 'embedding') and doc.embedding is not None:
                        doc_embedding = doc.embedding
                    else:
                        # Fallback to vector field if embedding is not available
                        if doc.vector is None:
                            continue
                        # If vector is a string, try to parse it as JSON
                        if isinstance(doc.vector, str):
                            try:
                                doc_embedding = json.loads(doc.vector)
                            except json.JSONDecodeError:
                                self.log(f"Invalid JSON in vector field for document {doc.id}", 'error')
                                continue
                        else:
                            doc_embedding = doc.vector
                    
                    # Ensure we have a list/array for the embedding
                    if not isinstance(doc_embedding, (list, np.ndarray)):
                        self.log(f"Invalid embedding format for document {doc.id}", 'error')
                        continue
                        
                    # Convert to numpy array if it's a list
                    if isinstance(doc_embedding, list):
                        doc_embedding = np.array(doc_embedding)
                    
                    # Calculate cosine similarity
                    similarity = np.dot(query_embedding, doc_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
                    )
                    
                    # NUEVO: Aplicar threshold aquí
                    if similarity >= threshold:
                        # NUEVO: Obtener información adicional basada en el tipo
                        result = {
                            'id': doc.id,
                            'contenido': doc.contenido,
                            'tipo': doc.tipo,
                            'similarity': float(similarity),
                            'referencia_id': getattr(doc, 'referencia_id', None)
                        }
                        
                        # Enriquecer con datos específicos del tipo
                        result.update(self._enrich_result_data(doc))
                        results.append(result)
                        
                except Exception as e:
                    self.log(f"Error processing document {doc.id}: {str(e)}", 'error')

            # Sort by similarity and return top_k results
            results = sorted(results, key=lambda x: x['similarity'], reverse=True)[:top_k]
            
            return {
                "results": results,
                "query": query,
                "threshold_applied": threshold,
                "total_found": len(results)
            }

        except Exception as e:
            self.log(f"Error in search_relevant_data: {str(e)}", 'error')
            return {"results": [], "error": str(e)}

    def _enrich_result_data(self, doc):
        """NUEVO: Enriquece los resultados con datos específicos del tipo de documento"""
        enriched = {}
        
        try:
            if doc.tipo == 'indicador' and hasattr(doc, 'referencia_id') and doc.referencia_id:
                try:
                    indicador = Indicador.objects.get(id=doc.referencia_id)
                    # Extraer texto limpio de descripcion_indicador (CKEditor field)
                    import re
                    definiciones = ''
                    if indicador.descripcion_indicador:
                        definiciones = re.sub(r'<[^>]+>', '', str(indicador.descripcion_indicador))
                    
                    enriched.update({
                        'nombre': indicador.nombre,
                        'descripcion': definiciones or '',
                        'unidad_medida': indicador.unidad_medida or '',
                        'fuente': getattr(indicador, 'fuente_datos', '') or '',
                    })
                    
                    # Información jerárquica
                    if hasattr(indicador, 'subtema') and indicador.subtema:
                        enriched['subtema'] = indicador.subtema.nombre
                        if hasattr(indicador.subtema, 'tema') and indicador.subtema.tema:
                            enriched['tema'] = indicador.subtema.tema.nombre
                            if hasattr(indicador.subtema.tema, 'dominio') and indicador.subtema.tema.dominio:
                                enriched['dominio'] = indicador.subtema.tema.dominio.nombre
                                
                except Indicador.DoesNotExist:
                    self.log(f"Indicador {doc.referencia_id} no encontrado", 'warning')
                except Exception as e:
                    self.log(f"Error obteniendo datos del indicador {doc.referencia_id}: {e}", 'warning')
                    
            elif doc.tipo == 'tema' and hasattr(doc, 'referencia_id') and doc.referencia_id:
                try:
                    from indicadores.models import MenuTema
                    tema = MenuTema.objects.get(id=doc.referencia_id)
                    enriched.update({
                        'nombre': tema.nombre,
                        'descripcion': tema.descripcion or '',
                    })
                    if hasattr(tema, 'dominio') and tema.dominio:
                        enriched['dominio'] = tema.dominio.nombre
                except Exception as e:
                    self.log(f"Error obteniendo datos del tema {doc.referencia_id}: {e}", 'warning')
                    
            elif doc.tipo == 'dominio' and hasattr(doc, 'referencia_id') and doc.referencia_id:
                try:
                    from indicadores.models import MenuDominio
                    dominio = MenuDominio.objects.get(id=doc.referencia_id)
                    enriched.update({
                        'nombre': dominio.nombre,
                        'descripcion': dominio.descripcion or '',
                    })
                except Exception as e:
                    self.log(f"Error obteniendo datos del dominio {doc.referencia_id}: {e}", 'warning')
                    
        except Exception as e:
            self.log(f"Error general enriqueciendo datos: {e}", 'warning')
            
        return enriched

    # ====================================================================
    # INDEXACIÓN DE MÓDULOS EXTENDIDOS (RAG)
    # ====================================================================

    def indexar_productos_academicos(self, force=False, batch_size=20):
        """Genera embeddings para Productos Académicos publicados."""
        try:
            from indicadores.models import ProductoAcademico
            from django.db import transaction
            import re

            qs = ProductoAcademico.objects.filter(estado='publicado')
            if not force:
                existentes = DocumentoVector.objects.filter(tipo='producto_academico').values_list('referencia_id', flat=True)
                qs = qs.exclude(id__in=existentes)

            total = qs.count()
            if total == 0:
                self.log('No hay productos académicos nuevos para indexar', 'info')
                return {'procesados': 0, 'total': 0}

            procesados = 0
            for prod in qs:
                try:
                    contenido_parts = [
                        f"Título: {prod.titulo}",
                        f"Autor: {prod.autor or ''}",
                        f"Área temática: {prod.area_tematica or ''}",
                        f"Palabras clave: {prod.palabras_clave or ''}",
                    ]
                    if prod.resumen:
                        resumen_limpio = re.sub(r'<[^>]+>', '', str(prod.resumen))
                        contenido_parts.append(f"Resumen: {resumen_limpio[:500]}")

                    contenido = " | ".join(contenido_parts)
                    embedding = self.get_embedding(contenido)

                    if embedding:
                        if force:
                            DocumentoVector.objects.filter(tipo='producto_academico', referencia_id=prod.id).delete()
                        DocumentoVector.objects.create(
                            tipo='producto_academico',
                            referencia_id=prod.id,
                            contenido=contenido,
                            embedding=embedding,
                            metadata={'titulo': prod.titulo, 'autor': prod.autor or '', 'slug': prod.slug}
                        )
                        procesados += 1
                except Exception as e:
                    self.log(f"Error indexando producto {prod.id}: {e}", 'error')

            self.log(f'Productos académicos indexados: {procesados}/{total}', 'info')
            return {'procesados': procesados, 'total': total}
        except Exception as e:
            self.log(f"Error indexando productos académicos: {e}", 'error')
            return {'procesados': 0, 'total': 0, 'error': str(e)}

    def indexar_documentos_infraestructura(self, force=False, batch_size=20):
        """Genera embeddings para Documentos de Infraestructura publicados."""
        try:
            from indicadores.models import DocumentoInfraestructura
            from django.db import transaction
            import re

            qs = DocumentoInfraestructura.objects.filter(activo=True, estado='publicado')
            if not force:
                existentes = DocumentoVector.objects.filter(tipo='documento_infraestructura').values_list('referencia_id', flat=True)
                qs = qs.exclude(id__in=existentes)

            total = qs.count()
            if total == 0:
                self.log('No hay documentos de infraestructura nuevos para indexar', 'info')
                return {'procesados': 0, 'total': 0}

            procesados = 0
            for doc in qs.select_related('grupo_documento__subcategoria__categoria__area'):
                try:
                    contenido_parts = [
                        f"Nombre: {doc.nombre}",
                        f"Tipo: {doc.get_tipo_documento_display()}",
                        f"Descripción: {doc.descripcion or ''}",
                    ]
                    if doc.resumen_ejecutivo:
                        resumen_limpio = re.sub(r'<[^>]+>', '', str(doc.resumen_ejecutivo))
                        contenido_parts.append(f"Resumen ejecutivo: {resumen_limpio[:500]}")
                    if doc.contenido:
                        contenido_limpio = re.sub(r'<[^>]+>', '', str(doc.contenido))
                        contenido_parts.append(f"Contenido: {contenido_limpio[:1000]}")
                    if doc.palabras_clave:
                        contenido_parts.append(f"Palabras clave: {doc.palabras_clave}")

                    ruta = (
                        f"{doc.grupo_documento.subcategoria.categoria.area.nombre} > "
                        f"{doc.grupo_documento.subcategoria.categoria.nombre} > "
                        f"{doc.grupo_documento.subcategoria.nombre} > "
                        f"{doc.grupo_documento.nombre}"
                    )
                    contenido_parts.append(f"Ruta: {ruta}")

                    contenido = " | ".join(contenido_parts)
                    embedding = self.get_embedding(contenido)

                    if embedding:
                        if force:
                            DocumentoVector.objects.filter(tipo='documento_infraestructura', referencia_id=doc.id).delete()
                        DocumentoVector.objects.create(
                            tipo='documento_infraestructura',
                            referencia_id=doc.id,
                            contenido=contenido,
                            embedding=embedding,
                            metadata={'nombre': doc.nombre, 'tipo': doc.tipo_documento, 'slug': doc.slug}
                        )
                        procesados += 1
                except Exception as e:
                    self.log(f"Error indexando documento {doc.id}: {e}", 'error')

            self.log(f'Documentos de infraestructura indexados: {procesados}/{total}', 'info')
            return {'procesados': procesados, 'total': total}
        except Exception as e:
            self.log(f"Error indexando documentos infraestructura: {e}", 'error')
            return {'procesados': 0, 'total': 0, 'error': str(e)}

    def _semantic_search(self, query, top_k=5):
        """Internal method for semantic search"""
        return self.search_relevant_data(query, top_k)

    def _keyword_search(self, query, top_k=5):
        """Fallback keyword search"""
        try:
            from django.db.models import Q
            from indicadores.models import Documento

            # Simple keyword search in Documento model
            keywords = query.lower().split()
            q_objects = Q()
            for keyword in keywords:
                q_objects |= Q(titulo__icontains=keyword) | \
                            Q(descripcion__icontains=keyword) | \
                            Q(contenido__icontains=keyword)

            results = []
            for doc in Documento.objects.filter(q_objects)[:top_k]:
                results.append({
                    'id': doc.id,
                    'tipo': 'documento',
                    'titulo': doc.titulo,
                    'descripcion': doc.descripcion[:200] if doc.descripcion else '',
                    'similarity': 0.5  # Default similarity for keyword matches
                })

            return results

        except Exception as e:
            self.log(f"Error in keyword search: {str(e)}", 'error')
            return []

    def indexar_catalogo_consulta(self, force=False, batch_size=20):
        """Genera embeddings para conjuntos del Catálogo de Consulta."""
        try:
            from indicadores.models import CatalogoConsulta
            import re

            qs = CatalogoConsulta.objects.filter(activo=True)
            if not force:
                existentes = DocumentoVector.objects.filter(
                    tipo='catalogo_consulta'
                ).values_list('referencia_id', flat=True)
                qs = qs.exclude(id__in=existentes)

            total = qs.count()
            if total == 0:
                self.log('No hay conjuntos del catálogo nuevos para indexar', 'info')
                return {'procesados': 0, 'total': 0}

            procesados = 0
            for c in qs.select_related('dominio'):
                try:
                    desc_limpia = re.sub(r'<[^>]+>', '', str(c.descripcion or '')).strip()
                    contenido_parts = [
                        f"Nombre: {c.nombre}",
                        f"Tipo de consulta: {c.get_tipo_consulta_display()}",
                        f"Descripción: {desc_limpia[:300]}",
                        f"Dominio: {c.dominio.nombre if c.dominio else ''}",
                        "Es un conjunto del catálogo de consulta: datos de "
                        "referencia (directorios, listados, nomencladores), no "
                        "una serie estadística.",
                    ]
                    if c.columnas:
                        contenido_parts.append(
                            f"Columnas del cuadro: {', '.join(str(x) for x in c.columnas[:15])}"
                        )
                    # Muestra de valores para que entidades concretas
                    # (teatros, bancos, barrios) también embejan bien
                    if c.filas:
                        muestras = set()
                        for fila in (c.filas or [])[:40]:
                            for v in fila.values():
                                if isinstance(v, str) and 3 < len(v) < 60:
                                    muestras.add(v)
                                if len(muestras) >= 40:
                                    break
                            if len(muestras) >= 40:
                                break
                        if muestras:
                            contenido_parts.append(
                                f"Ejemplos de contenido: {', '.join(sorted(muestras))}"
                            )

                    contenido = " | ".join(contenido_parts)
                    embedding = self.get_embedding(contenido)

                    if embedding:
                        if force:
                            DocumentoVector.objects.filter(
                                tipo='catalogo_consulta', referencia_id=c.id
                            ).delete()
                        DocumentoVector.objects.create(
                            tipo='catalogo_consulta',
                            referencia_id=c.id,
                            contenido=contenido,
                            embedding=embedding,
                            metadata={
                                'nombre': c.nombre,
                                'tipo_consulta': c.tipo_consulta,
                                'dominio': c.dominio.nombre if c.dominio else '',
                            },
                        )
                        procesados += 1
                except Exception as e:
                    self.log(f"Error indexando conjunto catálogo {c.id}: {e}", 'error')

            self.log(f'Conjuntos catálogo de consulta indexados: {procesados}/{total}', 'info')
            return {'procesados': procesados, 'total': total}

        except Exception as e:
            self.log(f"Error indexando catálogo de consulta: {e}", 'error')
            return {'procesados': 0, 'total': 0, 'error': str(e)}


# Singleton lazy: el modelo (all-MiniLM-L6-v2, ~400MB) se carga una sola
# vez por proceso. Antes se instanciaba EmbeddingService() por request,
# cargando el modelo repetidamente y provocando OOM/SIGKILL en workers
# de gunicorn bajo carga.
_embedding_service_instance = None


def get_embedding_service():
    """Devuelve la instancia única de EmbeddingService del proceso."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance
