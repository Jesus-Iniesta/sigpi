# Seeds

Comandos Typer para cargar la unidad organizacional, el área, las categorías y las prioridades de SIGPI.

## Prerrequisitos

Ejecuta los comandos desde `backend/`, con el entorno virtual activado y las variables de conexión a PostgreSQL configuradas. La base de datos debe tener las migraciones aplicadas:

```bash
alembic upgrade head
```

La semilla `all` crea de forma idempotente la unidad `SPT`, el área `Soporte técnico` y sus categorías.

## Comandos

Ejecutar todas las semillas:

```bash
python -m app.seeds all
```

Crear solo la unidad organizacional:

```bash
python -m app.seeds units
```

Crear el área de soporte:

```bash
python -m app.seeds area
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
