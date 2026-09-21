# Arquitectura en capas de SIGPI

## Dependencias

`api` -> `schemas` -> `services` -> `domain` -> `repositories` -> `models`.

`integrations` se consume desde `services`; `core` contiene configuración, seguridad,
excepciones, auditoría y logging. `domain` no depende de FastAPI ni SQLAlchemy.

## Persistencia implementada

Los modelos SQLAlchemy de `app/models` cubren las entidades que el modelado de negocio
identifica como recursos humanos, unidades, solicitudes, SLA, conocimiento, inventario,
mantenimiento y registros transversales:

- identidad, roles, unidades organizacionales, áreas, categorías, especialidades y turnos;
- solicitudes, clasificación, prioridad, bitácora, asignación y escalamiento;
- acuerdos de nivel de servicio y sus versiones;
- auditoría, notificaciones y plantillas;
- artículos de conocimiento y consultas;
- espacios físicos, activos y resguardos;
- órdenes y actas de mantenimiento, además de versiones del modelo.

## Decisiones de diseño

- UUID como clave primaria técnica y folio único como identificador operativo de solicitud.
- Fechas en UTC mediante `DateTime(timezone=True)`.
- Estados y catálogos como enums persistidos; la prioridad no se recibe como entrada de usuario.
- Historiales append-only para bitácora, auditoría, clasificación, asignación y SLA.
- Reglas de negocio RN-01 a RN-20 se aplican en `domain` y `services`; las restricciones
  estructurales se reflejan también en claves, índices y checks de la base de datos.

## Siguientes entregables

1. Alembic y migración inicial.
2. Repositorios async y servicios por caso de uso.
3. Schemas Pydantic desde el contrato OpenAPI.
4. Routers FastAPI y pruebas de dominio/API.
