# Matriz de permisos por módulo

La autorización se expresa como `modulo.accion` y se centraliza en
`app/core/permissions.py`. La ausencia de un permiso implica denegación. El rol
`administrator` es el único rol global; los demás reciben únicamente los permisos
listados en esta matriz.

| Rol | Solicitudes | Clasificación | SLA | Conocimiento | Inventario | Mantenimiento | Catálogo | Identidad | Reportes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `administrator` | lectura, alta, edición, asignación, cierre | lectura, revisión | lectura, gestión | lectura, gestión | lectura, gestión | lectura, gestión | lectura, gestión | lectura, gestión | lectura |
| `service_manager` | lectura, edición, asignación, cierre | lectura, revisión | lectura, gestión | lectura, gestión | lectura, gestión | lectura, gestión | lectura, gestión | - | lectura |
| `support_agent` | lectura, edición, asignación, cierre | lectura | - | lectura | lectura | lectura | lectura | - | - |
| `classifier` | lectura | lectura, revisión | - | - | - | - | lectura | - | - |
| `knowledge_manager` | lectura | - | - | lectura, gestión | - | - | - | - | - |
| `auditor` | lectura | - | lectura | lectura | lectura | lectura | lectura | lectura | lectura |
| `requester` | lectura, alta | - | - | lectura | - | - | - | - | - |

## Convención

- `read`: consultar información del módulo.
- `create`: crear un recurso.
- `update`: editar un recurso existente.
- `assign`: asignar una solicitud a un responsable.
- `close`: cerrar una solicitud.
- `review`: revisar o corregir una clasificación.
- `manage`: crear, editar, activar o desactivar la configuración del módulo.

La capa HTTP deberá obtener el rol del usuario autenticado y usar
`has_permission(role, permission)` antes de ejecutar el caso de uso. Esta política
no sustituye las restricciones de pertenencia organizacional ni la auditoría de
acciones sensibles.
