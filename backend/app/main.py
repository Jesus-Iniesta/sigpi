import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.auditoria import router as auditoria_router
from app.api.routers.auth import router as auth_router
from app.api.routers.catalog import router as catalog_router
from app.api.routers.mis_solicitudes import router as mis_solicitudes_router
from app.api.routers.notificaciones import router as notificaciones_router
from app.api.routers.revision import router as revision_router
from app.api.routers.seguimiento import router as seguimiento_router
from app.api.routers.sla import router as sla_router
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.usuarios import router as usuarios_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import REQUEST_ID_HEADER, RequestContextMiddleware, configure_logging
from app.db.session import SessionLocal
from app.services.sla_monitor_service import ejecutar_monitor

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Arranca el monitor del SLA (S4-08) si está habilitado y lo detiene al apagar."""
    tarea = None
    if settings.sla_monitor_enabled:
        tarea = asyncio.create_task(
            ejecutar_monitor(SessionLocal, settings.sla_monitor_interval_seconds)
        )
    try:
        yield
    finally:
        if tarea is not None:
            tarea.cancel()
            with suppress(asyncio.CancelledError):
                await tarea


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

register_exception_handlers(app)
app.add_middleware(RequestContextMiddleware) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER, "Content-Disposition"],
)


app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(catalog_router)
app.include_router(solicitudes_router)
app.include_router(seguimiento_router)
app.include_router(notificaciones_router)
app.include_router(sla_router)
app.include_router(auditoria_router)
app.include_router(mis_solicitudes_router)
app.include_router(revision_router)

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
