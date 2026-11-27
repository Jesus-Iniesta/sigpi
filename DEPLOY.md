# Despliegue de SIGPI

Esta guía describe cómo poner SIGPI en un servidor con Docker Compose, cómo respaldar la base de datos y cómo volver a una versión anterior si algo sale mal. Todo lo que aparece aquí sale de los archivos del repositorio: `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `backend/.env.example`, `backend/app/core/config.py` y las migraciones de `backend/alembic/versions/`.

Para el entorno de desarrollo local consulta el [README](README.md).

## Índice

1. [Arquitectura del despliegue](#1-arquitectura-del-despliegue)
2. [Requisitos del servidor](#2-requisitos-del-servidor)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Primer despliegue con Docker Compose](#4-primer-despliegue-con-docker-compose)
5. [Actualizar a una nueva versión](#5-actualizar-a-una-nueva-versión)
6. [Respaldo de la base de datos](#6-respaldo-de-la-base-de-datos)
7. [Rollback](#7-rollback)
8. [Lista de verificación antes de producción](#8-lista-de-verificación-antes-de-producción)
9. [Solución de problemas](#9-solución-de-problemas)

## 1. Arquitectura del despliegue

`docker-compose.yml` levanta tres servicios:

| Servicio   | Imagen / build                | Puerto | Qué hace |
|------------|-------------------------------|--------|----------|
| `db`       | `postgres:16-alpine`          | 5432   | PostgreSQL. Los datos viven en el volumen `sigpi_db_data`. Tiene `healthcheck` con `pg_isready`. |
| `backend`  | `backend/Dockerfile` (Python 3.14) | 8000 | API FastAPI (`fastapi run app/main.py`). Arranca cuando `db` está sano. |
| `frontend` | `frontend/Dockerfile` (Node 22) | 4173 | Compila la SPA con Vite y la sirve con `serve -s dist`. |

Los tres servicios usan `restart: unless-stopped`, así que vuelven a arrancar solos tras un reinicio del servidor.

Detalles del servicio `backend` que conviene conocer:

- Lee sus variables de `backend/.env` (`env_file`) y fuerza `DATABASE_HOST=db` para hablar con el contenedor de PostgreSQL.
- Monta `./backend` en `/app`. El código que corre es el del directorio del servidor, no el copiado en la imagen: un `git checkout` cambia el código y basta reiniciar el contenedor. Solo hace falta reconstruir la imagen cuando cambia `backend/requirements.txt`.
- Monta `./ml` en `/ml` (solo lectura). El clasificador busca ahí los conjuntos de datos `ml/data/dataset_v*.csv`. Los modelos reentrenados se guardan en la tabla `classifier_models`, no en disco, así que entran en el respaldo de la base.
- Monta `./frontend` en `/frontend` (solo lectura). Lo usan pruebas que comparan contratos entre backend y frontend; la API no lo necesita para funcionar.

```text
Navegador ──► proxy inverso (443) ──┬──► frontend :4173  (SPA estática)
                                    └──► backend  :8000  (API) ──► db :5432
```

El proxy inverso (Nginx, Caddy, un balanceador) no viene en el repositorio; se recomienda ponerlo delante para tener HTTPS. Ver [TRUSTED_PROXIES](#red-y-seguridad).

## 2. Requisitos del servidor

**Software**

- Linux de 64 bits (Ubuntu 22.04/24.04 o Debian 12 funcionan bien).
- Docker Engine 24 o superior con el plugin Docker Compose v2 (`docker compose`, sin guion).
- Git, para clonar el repositorio y cambiar de versión.
- Acceso a internet durante el build: se descargan `python:3.14-slim`, `node:22-slim`, `postgres:16-alpine`, los paquetes de `pip` y de `pnpm`.

No hace falta instalar Python, Node ni PostgreSQL en el servidor: todo corre en contenedores.

**Recursos sugeridos** (estimación para el uso de una facultad, no una medición):

- 2 vCPU y 4 GB de RAM. El build del frontend es la etapa que más memoria pide.
- 20 GB de disco: imágenes, volumen de PostgreSQL y espacio para los respaldos.

**Red**

- Abrir al exterior solo 80/443 (el proxy inverso).
- Los puertos 8000 y 4173 deben quedar accesibles solo para el proxy.
- `docker-compose.yml` publica `5432:5432`. En producción no expongas PostgreSQL a internet: bloquéalo en el firewall o cambia el mapeo a `"127.0.0.1:5432:5432"`.

> Docker escribe sus propias reglas de iptables y puede saltarse `ufw`. Si dependes de `ufw`, publica los puertos en `127.0.0.1` en lugar de confiar en el firewall.

## 3. Variables de entorno

### Backend (`backend/.env`)

Parte de la plantilla:

```bash
cp backend/.env.example backend/.env
```

`backend/.env` está en `backend/.gitignore`; nunca lo subas al repositorio. Los nombres no distinguen mayúsculas (pydantic-settings).

#### Base de datos

| Variable | Por omisión | Descripción |
|----------|-------------|-------------|
| `DATABASE_HOST` | `localhost` | En Compose se fuerza a `db`; no hace falta cambiarla. |
| `DATABASE_PORT` | `5432` | Puerto de PostgreSQL. |
| `DATABASE_NAME` | `sigpi` | Nombre de la base. |
| `DATABASE_USER` | vacío | **Obligatoria.** Usuario de PostgreSQL. |
| `DATABASE_PASSWORD` | vacío | **Obligatoria.** Contraseña de PostgreSQL. Se codifica en la URL, así que admite caracteres especiales. |

El servicio `db` toma `DATABASE_NAME`, `DATABASE_USER` y `DATABASE_PASSWORD` para crear la base **la primera vez** que se inicializa el volumen (si no las encuentra usa `sigpi`/`sigpi`/`sigpi`). Docker Compose resuelve esas `${...}` desde el entorno del shell o desde un `.env` en la raíz, **no** desde `backend/.env`. Para que ambos servicios usen las mismas credenciales, lanza siempre Compose con `--env-file backend/.env` (ver [sección 4](#4-primer-despliegue-con-docker-compose)). El `.gitignore` de la raíz no ignora `.env`, así que no crees uno ahí.

#### Seguridad y sesión

| Variable | Por omisión | Descripción |
|----------|-------------|-------------|
| `JWT_SECRET_KEY` | `dev-only-change-me` | **Obligatoria en producción.** Firma los tokens de sesión. Genera una con `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Si la cambias, todas las sesiones abiertas se invalidan. |
| `JWT_ALGORITHM` | `HS256` | Algoritmo de firma. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Duración del token de acceso. |
| `MAX_FAILED_LOGIN_ATTEMPTS` | `3` | Intentos fallidos antes de bloquear la cuenta. |

#### Red y seguridad

| Variable | Por omisión | Descripción |
|----------|-------------|-------------|
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | **Hay que cambiarla.** Orígenes que pueden llamar a la API desde el navegador. Va como lista JSON, por ejemplo `CORS_ORIGINS=["https://sigpi.ejemplo.mx"]`. El valor por omisión no incluye el puerto 4173 del contenedor `frontend`. |
| `TRUSTED_PROXIES` | vacío | IPs o redes CIDR del proxy inverso, separadas por comas (`10.0.0.5,172.16.0.0/12`). Solo si la conexión directa viene de uno de ellos se toma la IP de `X-Forwarded-For` para la bitácora de auditoría. Un valor inválido impide arrancar la API. Si el proxy corre en el mismo host y llega a los contenedores por la red de Docker, incluye la red del bridge de Docker (por ejemplo `172.16.0.0/12`). |

#### Reglas de negocio

| Variable | Por omisión | Descripción |
|----------|-------------|-------------|
| `CLASSIFICATION_CONFIDENCE_THRESHOLD` | `0.75` | Confianza mínima (0 a 1) para aceptar una clasificación sin revisión humana (RN-06). Desde S5-06 el administrador también puede ajustarla en caliente; ese ajuste se guarda en `app_settings`. |
| `CLASSIFIER_DATASET_PATH` | `ml/data/dataset_v1.csv` | CSV del clasificador, relativo a la raíz del repositorio. En el contenedor la raíz es `/`, así que `ml/data/...` apunta al volumen `/ml`. |
| `SLA_WARNING_THRESHOLD` | `0.80` | Fracción del SLA consumido a partir de la cual se marca riesgo. |
| `SLA_MONITOR_ENABLED` | `false` | **Ponla en `true` en producción.** Activa la tarea en segundo plano que revisa el riesgo de SLA y genera alertas. Si se queda en `false`, las alertas de SLA no se disparan. |
| `SLA_MONITOR_INTERVAL_SECONDS` | `30` | Cada cuántos segundos corre el monitor. |

#### Otras

| Variable | Por omisión | Descripción |
|----------|-------------|-------------|
| `APP_NAME` | `SIGPI` | Nombre que devuelven `/health` y la documentación OpenAPI. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` o `ERROR`. |

Ejemplo de `backend/.env` para producción:

```dotenv
APP_NAME=SIGPI

DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=sigpi
DATABASE_USER=sigpi
DATABASE_PASSWORD=<contraseña-larga-y-aleatoria>

CLASSIFICATION_CONFIDENCE_THRESHOLD=0.75
SLA_WARNING_THRESHOLD=0.80
SLA_MONITOR_ENABLED=true

JWT_SECRET_KEY=<salida-de-secrets.token_urlsafe(48)>

CORS_ORIGINS=["https://sigpi.ejemplo.mx"]
TRUSTED_PROXIES=172.16.0.0/12

LOG_LEVEL=INFO
```

### Frontend (`VITE_API_URL`)

El frontend solo tiene una variable: `VITE_API_URL`, la URL pública de la API (por omisión `http://localhost:8000`, ver `frontend/src/api/client.ts`). Vite la incrusta en el bundle **al compilar**, no al arrancar, así que cambiarla exige reconstruir la imagen del frontend.

El `Dockerfile` del frontend copia todo el directorio antes de `pnpm run build`, así que la forma más simple es crear `frontend/.env.production.local` (ignorado por git gracias a `*.local`):

```dotenv
VITE_API_URL=https://sigpi.ejemplo.mx/api
```

No pongas secretos en variables `VITE_*`: terminan en el JavaScript que descarga el navegador.

> Si el proxy publica la API bajo un prefijo como `/api`, debe quitarlo antes de reenviar a `backend:8000`, porque las rutas de FastAPI no llevan prefijo (`/health`, `/auth/...`).

> No hay `.dockerignore`. Si construyes desde una copia con `frontend/node_modules` o `frontend/dist`, se copian al contexto del build. Construye desde un clon limpio.

## 4. Primer despliegue con Docker Compose

Todos los comandos se ejecutan desde la raíz del repositorio. Para no repetir `--env-file`, puedes definir un alias en la sesión:

```bash
alias dc='docker compose --env-file backend/.env'
```

1. **Clonar el repositorio** en la versión a desplegar:

   ```bash
   git clone https://github.com/Jesus-Iniesta/sigpi.git
   cd sigpi
   git checkout main        # o la etiqueta/commit de la versión
   ```

2. **Configurar las variables**: crea `backend/.env` y, si la API no está en `http://localhost:8000`, `frontend/.env.production.local` (sección 3).

3. **Construir y levantar**:

   ```bash
   docker compose --env-file backend/.env up -d --build
   docker compose --env-file backend/.env ps
   ```

   `db` debe aparecer como `healthy` y los otros dos como `running`.

4. **Aplicar las migraciones.** El contenedor de la API **no** las ejecuta al arrancar; hay que lanzarlas a mano:

   ```bash
   docker compose --env-file backend/.env exec backend alembic upgrade head
   docker compose --env-file backend/.env exec backend alembic current
   ```

   `alembic current` debe mostrar la última revisión marcada `(head)`. Las migraciones también crean los roles de identidad (`4d9e0a2b7c6f_seed_identity_roles`) y los triggers que vuelven `audit_logs` de solo inserción.

5. **Cargar el catálogo inicial** (unidad `SPT`, área `Soporte técnico`, categorías y prioridades). Las semillas son idempotentes:

   ```bash
   docker compose --env-file backend/.env exec backend python -m app.seeds all
   docker compose --env-file backend/.env exec backend python -m app.seeds priorities
   ```

   No ejecutes `python -m app.seeds users` en producción: crea cuatro cuentas de prueba con una contraseña conocida (`ClaveSegura#2026`). Si la usas para una demostración, cambia esas contraseñas o desactiva las cuentas antes de abrir el sistema.

6. **Comprobar** que todo responde:

   ```bash
   curl -fsS http://localhost:8000/health      # {"status":"ok","service":"SIGPI"}
   curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:4173/   # 200
   docker compose --env-file backend/.env logs --tail=50 backend
   ```

   La documentación interactiva queda en `http://<host>:8000/docs`.

## 5. Actualizar a una nueva versión

1. **Respalda la base** (sección 6). No te saltes este paso: es lo que hace posible el rollback.
2. **Anota la versión actual** para poder volver:

   ```bash
   git rev-parse HEAD > ../sigpi-version-anterior.txt
   docker compose --env-file backend/.env exec backend alembic current
   ```

3. **Trae la nueva versión**:

   ```bash
   git fetch origin
   git checkout <etiqueta-o-commit>     # o: git pull --ff-only en main
   ```

4. **Reconstruye y reinicia.** `--build` es necesario para el frontend siempre, y para el backend cuando cambió `requirements.txt`:

   ```bash
   docker compose --env-file backend/.env up -d --build
   ```

5. **Migra y verifica**:

   ```bash
   docker compose --env-file backend/.env exec backend alembic upgrade head
   docker compose --env-file backend/.env restart backend
   curl -fsS http://localhost:8000/health
   ```

   Antes de migrar puedes revisar el SQL que se va a ejecutar sin tocar la base:

   ```bash
   docker compose --env-file backend/.env exec backend alembic upgrade <revision_actual>:head --sql
   ```

Como `./backend` está montado en el contenedor, la API puede ver el código nuevo antes de que se apliquen las migraciones. Si quieres evitar errores durante esa ventana, detén la API (`docker compose --env-file backend/.env stop backend`) antes del `git checkout`, migra con `run --rm` y vuelve a levantarla:

```bash
docker compose --env-file backend/.env run --rm backend alembic upgrade head
docker compose --env-file backend/.env up -d --build
```

## 6. Respaldo de la base de datos

Los datos de SIGPI viven en el volumen `sigpi_db_data`. Incluyen las solicitudes, los historiales append-only (auditoría, clasificación, asignación, SLA), los ajustes del clasificador (`app_settings`) y sus modelos reentrenados (`classifier_models`). Lo que no está en la base y debes guardar por separado es `backend/.env` (credenciales y `JWT_SECRET_KEY`) y, si lo modificaste, `ml/data/`.

### Respaldo manual

Usa `pg_dump` en formato personalizado (`-Fc`), que es comprimido y permite restaurar con `pg_restore`:

```bash
mkdir -p backups
docker compose --env-file backend/.env exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "backups/sigpi_$(date +%Y%m%d_%H%M%S).dump"
```

Comprueba que el archivo no está vacío y que se puede leer:

```bash
ls -lh backups/
docker compose --env-file backend/.env exec -T db pg_restore --list < backups/<archivo>.dump | head
```

`pg_dump` toma una foto consistente sin detener la aplicación.

### Respaldo automático

Ejemplo de `cron` diario a las 02:30 que guarda 14 días de respaldos. Ajusta la ruta del repositorio (`/opt/sigpi`):

```cron
30 2 * * * cd /opt/sigpi && docker compose --env-file backend/.env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/sigpi_$(date +\%Y\%m\%d).dump && find backups -name 'sigpi_*.dump' -mtime +14 -delete
```

En `crontab` el signo `%` debe ir escapado como `\%`. Copia los respaldos fuera del servidor (otro equipo, almacenamiento institucional): un respaldo en el mismo disco no sirve si el disco falla.

### Restaurar un respaldo

Restaurar reemplaza los datos actuales. Haz primero un respaldo del estado actual, aunque esté roto.

```bash
# 1. Detener la API para que nadie escriba durante la restauración
docker compose --env-file backend/.env stop backend

# 2. Borrar y recrear la base vacía
docker compose --env-file backend/.env exec -T db sh -c \
  'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'

# 3. Cargar el respaldo
docker compose --env-file backend/.env exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' \
  < backups/<archivo>.dump

# 4. Volver a levantar la API y comprobar
docker compose --env-file backend/.env start backend
docker compose --env-file backend/.env exec backend alembic current
curl -fsS http://localhost:8000/health
```

Notas:

- Se recrea la base en lugar de usar `pg_restore --clean` porque `audit_logs` tiene triggers que bloquean `UPDATE`, `DELETE` y `TRUNCATE` (migraciones `5e1f7a9c3b2d` y `bfbc891766fd`). Con una base vacía no hay nada que borrar y la restauración solo inserta, que sí está permitido.
- `dropdb` falla si hay conexiones abiertas. Por eso se detiene `backend` antes.
- El respaldo incluye la tabla `alembic_version`, así que tras restaurar la base queda en la revisión que tenía cuando se respaldó. El código desplegado debe corresponder a esa revisión (ver sección 7).

## 7. Rollback

Hay dos maneras de volver atrás. Elige según lo que haya cambiado la versión nueva.

### A. La versión nueva no trajo migraciones

Solo hay que volver al código anterior:

```bash
git checkout "$(cat ../sigpi-version-anterior.txt)"
docker compose --env-file backend/.env up -d --build
docker compose --env-file backend/.env restart backend
curl -fsS http://localhost:8000/health
```

Para saber si una versión trae migraciones, compara las carpetas:

```bash
git diff --stat <version_anterior> <version_nueva> -- backend/alembic/versions/
```

### B. La versión nueva aplicó migraciones

**Opción recomendada: restaurar el respaldo** tomado justo antes de actualizar (sección 6) y volver al código anterior. Es la vía más segura, porque devuelve la base exactamente al estado previo. Perderás lo que se haya escrito entre la actualización y el rollback.

```bash
docker compose --env-file backend/.env stop backend
git checkout "$(cat ../sigpi-version-anterior.txt)"
# ... pasos de "Restaurar un respaldo" de la sección 6 ...
docker compose --env-file backend/.env up -d --build
```

**Opción alternativa: `alembic downgrade`**, útil si no quieres perder los datos escritos después de la actualización. Hazlo **con el código nuevo todavía desplegado**, porque los archivos de migración nuevos (los que saben deshacerse) solo existen en esa versión:

```bash
# 1. Ver en qué revisión está la base y cuál quieres
docker compose --env-file backend/.env exec backend alembic current
docker compose --env-file backend/.env exec backend alembic history --verbose | head -40

# 2. Respaldar (siempre)
# 3. Bajar a la revisión anterior (o una cantidad de pasos con -1, -2...)
docker compose --env-file backend/.env exec backend alembic downgrade <revision_anterior>

# 4. Ahora sí, volver al código anterior
docker compose --env-file backend/.env stop backend
git checkout "$(cat ../sigpi-version-anterior.txt)"
docker compose --env-file backend/.env up -d --build
```

Antes de un `downgrade`, revisa la función `downgrade()` de cada migración que vas a deshacer. Algunas borran tablas o columnas con datos (por ejemplo `d3f6a9b2c4e8` elimina `app_settings` y `classifier_models`), y lo que borren no vuelve. Si una migración toca `audit_logs` con `DELETE` o `UPDATE`, los triggers la harán fallar; en ese caso usa la opción de restaurar el respaldo.

### Después de cualquier rollback

- `alembic current` debe coincidir con la última migración que existe en `backend/alembic/versions/` del código desplegado.
- `/health` responde `200`.
- Entra al sistema con una cuenta real y revisa la bandeja y una solicitud.
- Si el problema fue de configuración, también regresa `backend/.env` o `frontend/.env.production.local` a sus valores anteriores; no están en git.

## 8. Lista de verificación antes de producción

- [ ] `JWT_SECRET_KEY` propia y larga (no `dev-only-change-me` ni la de `.env.example`).
- [ ] `DATABASE_PASSWORD` fuerte y distinta de `sigpi`.
- [ ] Compose siempre con `--env-file backend/.env`, para que `db` y `backend` compartan credenciales.
- [ ] `CORS_ORIGINS` con el dominio público del frontend.
- [ ] `VITE_API_URL` con la URL pública de la API, y frontend reconstruido.
- [ ] `SLA_MONITOR_ENABLED=true`.
- [ ] `TRUSTED_PROXIES` con la IP o red del proxy inverso.
- [ ] Puerto 5432 no expuesto a internet; 8000 y 4173 solo accesibles por el proxy.
- [ ] HTTPS en el proxy inverso.
- [ ] `alembic upgrade head` aplicado y semillas `all` y `priorities` cargadas.
- [ ] Sin las cuentas de prueba de `python -m app.seeds users`, o con su contraseña cambiada.
- [ ] Respaldo automático programado, probado con una restauración y copiado fuera del servidor.
- [ ] `backend/.env` guardado en un lugar seguro fuera del servidor.

## 9. Solución de problemas

**`password authentication failed for user ...` en los logs del backend.** `db` y `backend` usan credenciales distintas. Casi siempre es porque se levantó Compose sin `--env-file backend/.env` y el volumen se inicializó con `sigpi`/`sigpi`. PostgreSQL solo lee `POSTGRES_USER`/`POSTGRES_PASSWORD` al crear el volumen; cambiarlos después no tiene efecto. Cambia la contraseña dentro de la base (`ALTER USER ... PASSWORD ...`) o, en un servidor sin datos, borra el volumen con `docker compose down -v` y vuelve a empezar.

**El navegador muestra errores de CORS.** El origen del frontend no está en `CORS_ORIGINS`. Recuerda que va como lista JSON y que hay que reiniciar `backend` después de cambiarla.

**El frontend llama a `localhost:8000`.** `VITE_API_URL` no estaba definida al compilar. Crea `frontend/.env.production.local` y reconstruye con `docker compose --env-file backend/.env up -d --build frontend`.

**La API no arranca y menciona `trusted_proxies`.** `TRUSTED_PROXIES` tiene un valor que no es IP ni red CIDR. Corrígelo o déjalo vacío.

**Errores de tablas o columnas que no existen.** Faltan migraciones: `docker compose --env-file backend/.env exec backend alembic upgrade head`.

**`audit_logs is append-only; DELETE is not allowed`.** Es el comportamiento esperado: la bitácora de auditoría no se puede modificar ni vaciar. Para devolver la base a un estado anterior, restaura un respaldo en una base nueva (sección 6).

**Las alertas de SLA no aparecen.** Revisa que `SLA_MONITOR_ENABLED=true` y reinicia `backend`.
