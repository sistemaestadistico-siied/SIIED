import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
import django
django.setup()
from indicadores.models import ElementoGeo, CapaGeo
from django.db.models import Count

print('ElementoGeo total:', ElementoGeo.objects.count())
capas = (CapaGeo.objects
         .annotate(n=Count('elementogeo'))
         .order_by('-n')[:20])
for c in capas:
    print(f'Capa {c.id} - {c.nombre}: elementos={c.n}')
