# Plan de implementación de SIGPI

## Fase 1: fundamento y persistencia

- Mantener Python 3.14 y dependencias reproducibles.
- Configurar FastAPI, SQLAlchemy async, PostgreSQL y Alembic.
- Generar la migración inicial a partir de los 29 modelos actuales.
- Cargar catálogos base: áreas, categorías, prioridades/SLA y roles.

## Fase 2: dominio y aplicación

- Implementar reglas puras RN-05 (matriz urgencia-impacto), RN-06/RN-07 (confianza y corrección), RN-08/RN-09 (asignación crítica), RN-11 (reloj SLA) y RN-15/RN-16 (cierre/reapertura).
- Crear repositorios async por agregado: solicitudes, identidad, catálogo, SLA, inventario y conocimiento.
- Crear servicios de alta, clasificación, asignación, seguimiento, escalamiento, notificación y mantenimiento.
- Añadir pruebas unitarias de dominio antes de conectar infraestructura.

## Fase 3: API y seguridad

- Crear schemas Pydantic desde los casos de uso.
- Añadir routers por feature y dependencias de sesión/autorización.
- Integrar JWT, roles y permisos RN-19.
- Generar el contrato OpenAPI para el frontend TypeScript.

## Fase 4: integraciones

- Adaptadores para directorio institucional, correo, inventario patrimonial y clasificador.
- Implementar contingencias y reintentos sin contaminar el dominio.
- Registrar auditoría inalterable y eventos de notificación.

## Fase 5: calidad y transición

- Pruebas API con `httpx` y base de datos de prueba.
- Cobertura mínima del 60 % en sprint 4 y del 80 % al cierre.
- Ruff, pytest, migraciones y comprobación de arranque en CI.
- Documentación de despliegue, respaldo, reversión y contrato para frontend.
