# indicadores/search.py
from django.db import connection
import numpy as np
from .embeddings import get_embedding_service
from pgvector.django import CosineDistance

class SemanticSearch:
    def __init__(self):
        # Singleton: reutiliza el modelo ya cargado en el proceso
        self.embedding_service = get_embedding_service()
    
    def buscar_similar(self, consulta, tipo_doc=None, top_k=5, umbral=0.6, referencia_ids=None):
        """Busca documentos similares a la consulta
        
        Args:
            consulta: Texto de búsqueda
            tipo_doc: Tipo de documento (ej: 'indicador')
            top_k: Número máximo de resultados
            umbral: Umbral mínimo de similitud (0-1)
            referencia_ids: Lista de IDs de referencia para filtrar (NUEVO)
        """
        try:
            # Generar embedding de la consulta
            query_embedding = self.embedding_service.get_embedding(consulta)
            
            # Usar el ORM de Django para la consulta
            from .models import DocumentoVector
            from django.db.models import Q
            
            # Crear la consulta base
            query = DocumentoVector.objects.annotate(
                distancia=CosineDistance('embedding', query_embedding)
            ).order_by('distancia')
            
            # Filtrar por tipo si se especifica
            if tipo_doc:
                query = query.filter(tipo=tipo_doc)
            
            # NUEVO: Filtrar por IDs de referencia si se especifica
            if referencia_ids is not None and len(referencia_ids) > 0:
                query = query.filter(referencia_id__in=referencia_ids)
            
            # Limitar resultados
            resultados_db = query[:top_k]
            
            # Formatear resultados
            resultados = []
            for doc in resultados_db:
                similitud = 1 - float(doc.distancia)
                if similitud >= umbral:
                    resultados.append({
                        'id': doc.id,
                        'tipo': doc.tipo,
                        'referencia_id': doc.referencia_id,
                        'contenido': doc.contenido[:200] + '...' if len(doc.contenido) > 200 else doc.contenido,
                        'similitud': round(similitud, 4),
                        'metadata': doc.metadata or {}
                    })
            
            return resultados
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return []

            