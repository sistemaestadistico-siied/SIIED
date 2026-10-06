    # Sistema de Roles y Control de Acceso

    ## Descripción General

    El sistema SIIED cuenta con **3 módulos independientes** con diferentes niveles de acceso controlados por roles de usuario:

    1. **Módulo de Administración** - Acceso exclusivo para staff
    2. **Módulo de Recolección** - Para usuarios con rol de recolector
    3. **Módulo de Reportes** - Para usuarios con rol de consultor

    ---

    ## Tipos de Usuarios y Permisos

    ### 1. Administradores (Staff)
    **Campo:** `User.is_staff = True`

    **Permisos:**
    - ✅ Acceso total al panel de administración Django (`/admin/`)
    - ✅ Acceso al módulo de recolección (`/recoleccion/`)
    - ✅ Acceso al módulo de reportes (`/reportes/`)
    - ✅ Gestión completa de usuarios, indicadores, datos y configuraciones
    - ✅ Dashboard de cargas del equipo

    **Características:**
    - No requieren perfil adicional
    - Tienen acceso a todos los módulos del sistema
    - Pueden crear y gestionar perfiles de otros usuarios

    ---

    ### 2. Usuarios con Perfil (No-Staff)
    **Modelo:** `PerfilRecolector`

    Los usuarios no-staff deben tener un perfil asociado con un **rol específico** que determina sus permisos:

    #### **Rol: Recolector** (`rol='recolector'`)
    **Permisos:**
    - ✅ Acceso al módulo de recolección (`/recoleccion/`)
    - ✅ Cargar series de indicadores
    - ✅ Cargar archivos de microdata
    - ✅ Ver historial de sus propias cargas
    - ✅ Descargar plantillas y ver instrucciones
    - ❌ NO tiene acceso al módulo de reportes
    - ❌ NO tiene acceso al panel de administración

    **Uso típico:** Personal de campo o instituciones que recopilan datos

    ---

    #### **Rol: Consultor** (`rol='consultor'`)
    **Permisos:**
    - ✅ Acceso al módulo de reportes (`/reportes/`)
    - ✅ Descargar datos de indicadores (con desagregaciones)
    - ✅ Descargar metadata de indicadores
    - ✅ Descargar archivos de microdata
    - ✅ Descargar metadata de variables
    - ✅ Exportación masiva de datos
    - ❌ NO puede cargar datos
    - ❌ NO tiene acceso al módulo de recolección
    - ❌ NO tiene acceso al panel de administración

    **Uso típico:** Analistas, investigadores, consultores externos

    ---

    #### **Rol: Ambos** (`rol='ambos'`)
    **Permisos:**
    - ✅ Acceso al módulo de recolección (`/recoleccion/`)
    - ✅ Acceso al módulo de reportes (`/reportes/`)
    - ✅ Todos los permisos de recolector
    - ✅ Todos los permisos de consultor
    - ❌ NO tiene acceso al panel de administración

    **Uso típico:** Personal técnico que necesita tanto cargar como consultar datos

    ---

    ## Estructura del Modelo PerfilRecolector

    ```python
    class PerfilRecolector(models.Model):
        user = models.OneToOneField(User, on_delete=models.CASCADE)
        
        # Campo de rol (NUEVO)
        rol = models.CharField(
            max_length=20,
            choices=[
                ('recolector', 'Recolector de Datos'),
                ('consultor', 'Consultor de Reportes'),
                ('ambos', 'Recolector y Consultor'),
            ],
            default='recolector'
        )
        
        institucion = models.CharField(max_length=255)
        cargo = models.CharField(max_length=255, blank=True, null=True)
        telefono = models.CharField(max_length=20, blank=True, null=True)
        activo = models.BooleanField(default=True)
        fecha_creacion = models.DateTimeField(auto_now_add=True)
        fecha_actualizacion = models.DateTimeField(auto_now=True)
        
        def puede_recolectar(self):
            """Verifica si puede acceder al módulo de recolección"""
            return self.activo and self.rol in ['recolector', 'ambos']
        
        def puede_consultar_reportes(self):
            """Verifica si puede acceder al módulo de reportes"""
            return self.activo and self.rol in ['consultor', 'ambos']
    ```

    ---

    ## Decoradores de Control de Acceso

    ### `@recolector_required`
    Protege las vistas del módulo de recolección.

    **Permite acceso a:**
    - Usuarios staff (administradores)
    - Usuarios con `perfil.puede_recolectar() == True`

    **Redirige a:** `/recoleccion/login/` si no está autenticado

    ---

    ### `@consultor_reportes_required`
    Protege las vistas del módulo de reportes.

    **Permite acceso a:**
    - Usuarios staff (administradores)
    - Usuarios con `perfil.puede_consultar_reportes() == True`

    **Redirige a:** `/reportes/login/` si no está autenticado

    ---

    ### `@admin_required`
    Protege las vistas administrativas.

    **Permite acceso a:**
    - Solo usuarios con `is_staff = True`

    **Redirige a:** `/admin/login/` si no está autenticado

    ---

    ## Flujo de Autenticación

    ### Módulo de Recolección
    1. Usuario accede a `/recoleccion/login/`
    2. Ingresa credenciales
    3. Sistema verifica:
    - ¿Es staff? → Acceso directo ✅
    - ¿Tiene perfil activo con rol 'recolector' o 'ambos'? → Acceso ✅
    - De lo contrario → Acceso denegado ❌

    ### Módulo de Reportes
    1. Usuario accede a `/reportes/login/`
    2. Ingresa credenciales
    3. Sistema verifica:
    - ¿Es staff? → Acceso directo ✅
    - ¿Tiene perfil activo con rol 'consultor' o 'ambos'? → Acceso ✅
    - De lo contrario → Acceso denegado ❌

    ---

    ## Gestión de Usuarios (Para Administradores)

    ### Crear un Usuario Recolector

    1. Ir al panel de administración: `/admin/`
    2. Crear usuario en **Auth > Users**
    3. Establecer contraseña
    4. **NO** marcar `is_staff`
    5. Ir a **Indicadores > Perfiles de Usuarios**
    6. Crear perfil:
    - Seleccionar usuario
    - **Rol:** Recolector de Datos
    - Institución: (nombre de la institución)
    - Activo: ✅
    7. Guardar

    ### Crear un Usuario Consultor

    Mismo proceso, pero seleccionar **Rol:** Consultor de Reportes

    ### Crear un Usuario con Ambos Roles

    Mismo proceso, pero seleccionar **Rol:** Recolector y Consultor

    ---

    ## Migración de Datos Existentes

    Si ya tienes usuarios con `PerfilRecolector` sin el campo `rol`:

    ```bash
    # Ejecutar migración
    python3 manage.py migrate

    # Los perfiles existentes tendrán rol='recolector' por defecto
    # Actualizar manualmente desde el admin si necesitan otro rol
    ```

    ---

    ## Tabla Resumen de Permisos

    | Funcionalidad | Admin (Staff) | Recolector | Consultor | Ambos |
    |---------------|---------------|------------|-----------|-------|
    | Panel Admin Django | ✅ | ❌ | ❌ | ❌ |
    | Cargar Series | ✅ | ✅ | ❌ | ✅ |
    | Cargar Microdata | ✅ | ✅ | ❌ | ✅ |
    | Ver Historial Propio | ✅ | ✅ | ❌ | ✅ |
    | Dashboard Cargas Equipo | ✅ | ❌ | ❌ | ❌ |
    | Descargar Datos | ✅ | ❌ | ✅ | ✅ |
    | Descargar Metadata | ✅ | ❌ | ✅ | ✅ |
    | Reportes Masivos | ✅ | ❌ | ✅ | ✅ |
    | Gestionar Usuarios | ✅ | ❌ | ❌ | ❌ |

    ---

    ## URLs por Módulo

    ### Administración
    - Login: `/admin/login/`
    - Dashboard: `/admin/`

    ### Recolección
    - Login: `/recoleccion/login/`
    - Dashboard: `/recoleccion/`
    - Cargar Serie: `/recoleccion/cargar-serie/`
    - Cargar Microdata: `/recoleccion/cargar-microdata/`
    - Historial Series: `/recoleccion/historial-series/`
    - Historial Microdata: `/recoleccion/historial-microdata/`

    ### Reportes
    - Login: `/reportes/login/`
    - Dashboard: `/reportes/`
    - Reportes Indicadores: `/reportes/indicadores/`
    - Reportes Microdata: `/reportes/microdata/`

    ---

    ## Notas Importantes

    1. **Usuarios Staff:** Tienen acceso total a todos los módulos sin necesidad de perfil adicional
    2. **Campo activo:** Un perfil con `activo=False` no puede acceder aunque tenga el rol correcto
    3. **Sesiones independientes:** Cada módulo tiene su propio login, pero comparten la sesión de Django
    4. **Seguridad:** Los decoradores verifican permisos en cada request, no solo en el login
    5. **Escalabilidad:** El sistema permite agregar más roles en el futuro sin cambios mayores

    ---

    ## Preguntas Frecuentes

    **P: ¿Un usuario puede tener acceso a múltiples módulos?**
    R: Sí, con el rol 'ambos' o siendo staff.

    **P: ¿Cómo cambio el rol de un usuario existente?**
    R: Desde el panel admin, editar su perfil y cambiar el campo "Rol".

    **P: ¿Los usuarios staff necesitan perfil?**
    R: No, los staff tienen acceso automático a todos los módulos.

    **P: ¿Puedo desactivar temporalmente un usuario?**
    R: Sí, marcando `activo=False` en su perfil.

    **P: ¿Qué pasa si un usuario sin permisos intenta acceder?**
    R: Es redirigido a la página de acceso a módulos con un mensaje de error.
