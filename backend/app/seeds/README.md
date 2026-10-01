# Seeds

Comandos Typer para cargar las categorías y consultar el catálogo de prioridades de SIGPI.

## Prerrequisitos

Ejecuta los comandos desde `backend/`, con el entorno virtual activado y las variables de conexión a PostgreSQL configuradas. La base de datos debe tener las migraciones aplicadas:

```bash
alembic upgrade head
```

El área de servicio `Soporte técnico` debe existir antes de cargar las categorías.

## Comandos

Ejecutar todas las semillas:

```bash
python -m app.seeds all
```

Cargar únicamente las categorías:

```bash
python -m app.seeds categories
```

Usar otra área de servicio existente:

```bash
python -m app.seeds categories --area-name "Nombre del área"
```

Ejecutar la semilla de prioridades:

```bash
python -m app.seeds priorities
```

Consultar las opciones disponibles:

```bash
python -m app.seeds --help
python -m app.seeds categories --help
```

Las semillas son idempotentes: ejecutar `categories` varias veces no duplica registros. Las prioridades válidas son `P1`, `P2`, `P3` y `P4`; se representan mediante el enum del dominio y se almacenan en las versiones SLA que las utilizan.
