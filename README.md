# SIGPI

Sistema Inteligente para la Gestión y Priorización de Incidencias de Soporte Técnico.

SIGPI está organizado como un monorepo con un backend FastAPI y un frontend React. El backend concentra las reglas de negocio, persistencia y API; el frontend consume esos contratos para presentar la operación institucional.

## Stack

- **Backend:** Python 3.14, FastAPI, SQLAlchemy, Alembic y PostgreSQL.
- **Frontend:** React, TypeScript estricto, Vite, React Router y TanStack Query.
- **UI y calidad:** Tailwind CSS compatible con shadcn/ui, ESLint y Prettier.
- **Gestor frontend:** pnpm `12.5.1`.

## Requisitos

Instala las siguientes herramientas antes de comenzar:

- Python 3.14
- PostgreSQL 14 o superior
- Node.js compatible con pnpm 12
- Corepack habilitado para usar la versión fijada de pnpm

Comprueba las versiones:

```bash
python3 --version
node --version
corepack --version
```

## Inicio rápido

Clona el repositorio y trabaja desde la raíz del proyecto:

```bash
git clone <URL_DEL_REPOSITORIO>
cd SIGPI
```

El backend y el frontend se ejecutan en terminales separadas.

## Backend

### 1. Crear el entorno Python

```bash
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

En Windows, activa el entorno con:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Configurar PostgreSQL

Crea una base de datos llamada `sigpi` y copia las variables de ejemplo:

```bash
cp .env.example .env
```

Completa en `.env` al menos `DATABASE_USER` y `DATABASE_PASSWORD`. La configuración completa está en [.env.example](backend/.env.example). No subas `.env` al repositorio.

### 3. Aplicar migraciones

Desde `backend/`:

```bash
alembic upgrade head
```

Para crear una migración después de cambiar modelos:

```bash
alembic revision --autogenerate -m "describe the schema change"
alembic upgrade head
```

Revisa siempre la migración generada antes de aplicarla. Las migraciones existentes incluyen el esquema inicial y el modelo de SLA versionado.

### 4. Ejecutar la API

```bash
fastapi dev app/main.py
```

La API queda disponible en:

- Health check: http://localhost:8000/health
- Documentación Swagger: http://localhost:8000/docs
- OpenAPI: http://localhost:8000/openapi.json

## Frontend

Desde la raíz del repositorio:

```bash
cd frontend
corepack enable
pnpm install
pnpm dev
```

La aplicación queda disponible en http://localhost:5173.

El cliente usa `http://localhost:8000` como API por defecto. Para cambiarlo, crea `frontend/.env.local`:

```dotenv
VITE_API_URL=http://localhost:8000
```

No agregues secretos a variables `VITE_*`, porque se incluyen en el bundle del navegador.

## Comandos de calidad

### Backend

Activa el entorno virtual antes de ejecutar los comandos:

```bash
cd backend
source .venv/bin/activate
pytest
ruff check app tests alembic
ruff format --check app tests alembic
```

La migración puede revisarse sin conexión a PostgreSQL con:

```bash
alembic upgrade head --sql
```

### Frontend

```bash
cd frontend
pnpm lint
pnpm format:check
pnpm build
```

Para corregir automáticamente el formato:

```bash
pnpm format
```

## Estructura del repositorio

```text
SIGPI/
├── backend/
│   ├── app/
│   │   ├── api/            # Routers y dependencias HTTP
│   │   ├── core/           # Configuración, permisos y seguridad transversal
│   │   ├── db/             # Base declarativa y sesiones
│   │   ├── domain/         # Reglas de negocio puras
│   │   ├── integrations/   # Sistemas externos
│   │   ├── models/         # Entidades SQLAlchemy
│   │   ├── repositories/   # Acceso a datos
│   │   ├── schemas/        # Contratos Pydantic
│   │   └── services/       # Casos de uso
│   ├── alembic/            # Migraciones de base de datos
│   ├── docs/               # Documentación funcional y técnica
│   └── tests/              # Pruebas del backend
└── frontend/
    ├── src/
    │   ├── api/            # Cliente HTTP y contratos de API
    │   ├── features/       # Funcionalidades por dominio
    │   ├── routes/         # Layout y rutas de React Router
    │   └── shared/         # UI y utilidades reutilizables
    └── public/             # Recursos estáticos
```

## Flujo de trabajo recomendado

1. Actualiza tu rama antes de comenzar:

   ```bash
   git pull --rebase
   ```

2. Implementa la regla de negocio en `backend/app/domain` cuando sea independiente de infraestructura.
3. Coloca los modelos SQLAlchemy en `backend/app/models` y crea una migración revisada.
4. Expón contratos mediante schemas, servicios y routers antes de conectarlos al frontend.
5. En frontend, organiza el cambio dentro de `features`; usa `api` para llamadas HTTP y `shared` para piezas reutilizables.
6. Ejecuta las validaciones de backend y frontend antes de abrir un pull request.
7. Documenta cambios de contrato, configuración o migración en el README o en `docs/`.

## Documentación del proyecto

- [Arquitectura por capas](backend/docs/architecture-layers.md)
- [Plan de implementación](backend/docs/implementation-plan.md)
- [Matriz de permisos](backend/docs/matriz_permisos.md)
- [Guía del backend](backend/README.md)

## Convenciones importantes

- Las fechas se almacenan en UTC.
- Las entidades usan UUID como clave técnica.
- Las prioridades se calculan mediante urgencia e impacto; no se reciben libremente desde el cliente.
- Los historiales de auditoría, clasificación, asignación y SLA son append-only.
- Los cambios de esquema deben incluir una migración Alembic.
- No versionar `.env`, credenciales, dumps de base de datos ni carpetas `.venv`, `node_modules` o `dist`.

## Solución de problemas

### El frontend no puede consultar `/health`

Asegúrate de que ambos procesos estén activos. El backend debe escuchar en el puerto `8000` y el frontend en `5173`. FastAPI ya permite los orígenes locales de Vite mediante CORS.

### `ModuleNotFoundError: No module named 'app'`

Ejecuta los comandos del backend desde la carpeta `backend/` con el entorno virtual activado.

### Alembic no encuentra la base de datos

Comprueba que PostgreSQL esté activo, que la base `sigpi` exista y que las variables `DATABASE_*` de `.env` sean correctas.
