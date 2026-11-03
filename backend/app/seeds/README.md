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

Ejecutar la semilla de usuarios (4 cuentas con contraseña `ClaveSegura#2026`):

```bash
python -m app.seeds users
```

Consultar las opciones disponibles:

```bash
python -m app.seeds --help
python -m app.seeds categories --help
```

Las semillas son idempotentes: ejecutar `categories` varias veces no duplica registros. Las prioridades válidas son `P1`, `P2`, `P3` y `P4`; se representan mediante el enum del dominio y se almacenan en las versiones SLA que las utilizan.

## Usuarios creados por la semilla

El comando `users` crea 4 cuentas con contraseña `ClaveSegura#2026`:

| institutional_id | email | Rol | user_type | soporte |
|------------------|-------|-----|-----------|---------|
| uaem2026001 | amartinez@uaemex.mx | administrator | administrative | - |
| uaem2026002 | crodriguez@uaemex.mx | support_agent | technical | level_1 |
| uaem2026003 | egarcia@uaemex.mx | requester | academic | - |
| uaem2026004 | lhernandez@uaemex.mx | support_agent | technical | level_2 |
