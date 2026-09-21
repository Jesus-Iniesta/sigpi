# SIGPI Backend

Backend FastAPI para el Sistema Inteligente para la Gestión y Priorización de Incidencias de Soporte Técnico.

## Entorno

El entorno oficial del proyecto es Python 3.14. Crear o activar el entorno local:

```bash
/home/jesus/Repos/portafolio/Flowra/venv/bin/python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copiar `.env.example` como `.env` y completar los datos de PostgreSQL. El archivo
`.env` es local y no debe versionarse.

## Primera migración

Desde `backend/`, después de configurar `.env` y crear la base de datos:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

La primera orden genera la revisión a partir de `Base.metadata`; la segunda la aplica.

## Ejecución

```bash
fastapi dev app/main.py
```

La comprobación de salud queda disponible en `/health`.

## Capas

- `api`: routers y dependencias HTTP.
- `schemas`: contratos Pydantic.
- `services`: casos de uso.
- `domain`: reglas puras, incluida RN-05.
- `repositories`: acceso async a SQLAlchemy.
- `models`: persistencia SQLAlchemy.
- `integrations`: directorio institucional, correo, inventario y clasificador.
- `core`: configuración, seguridad, excepciones, auditoría y logging.
