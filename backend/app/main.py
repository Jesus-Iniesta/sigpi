from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.auth import router as auth_router
from app.api.routers.catalog import router as catalog_router
from app.api.routers.sla import router as sla_router
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.usuarios import router as usuarios_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers 
from app.core.logging import configure_logging, REQUEST_ID_HEADER, RequestContextMiddleware

configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name, version="0.1.0")

register_exception_handlers(app)
app.add_middleware(RequestContextMiddleware) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER]
)


app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(catalog_router)
app.include_router(solicitudes_router)
app.include_router(sla_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
