"""Entorno de las pruebas de aceptación (S5-25).

Base SQLite en memoria con el catálogo, el acuerdo de servicio y una persona por rol. Solo
se sustituyen el clasificador (confianza fija), el reloj (`_ahora` de los servicios) y la
autenticación (`get_current_user`); todo lo demás corre por la API HTTP real.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.api.routers.solicitudes import get_clasificacion_service
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria, Especialidad
from app.models.enums import ClassificationSource, Priority, UserType
from app.models.identity import Role, User, UserRole
from app.models.organization import OrganizationalUnit
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services import asignacion_service, seguimiento_service, sla_clock_service
from app.services.clasificacion_service import ClasificacionService

RESOLUCION_MINUTOS = {Priority.P1: 120, Priority.P2: 240, Priority.P3: 480, Priority.P4: 960}

# clave -> (nombre, tipo de usuario, rol con el que entra a la API)
PERSONAS = {
    "solicitante": ("Sara Solicitante", UserType.ACADEMIC, RoleName.REQUESTER),
    "tecnico": ("Tomás Técnico", UserType.TECHNICAL, RoleName.SUPPORT_AGENT),
    "otro_tecnico": ("Óscar Otro", UserType.TECHNICAL, RoleName.SUPPORT_AGENT),
    "jefe": ("Julia Jefa", UserType.ADMINISTRATIVE, RoleName.SERVICE_MANAGER),
}


class ClasificadorFijo:
    """Predice siempre «Redes» con urgencia e impacto altos (P1) y la confianza dada."""

    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)
    version = "aceptacion-v1"

    def __init__(self, confianza: float) -> None:
        self.confianza = confianza

    def predecir(self, texto: str):
        from app.integrations.clasificador_client import Prediccion

        return Prediccion(
            categoria="Redes",
            urgencia=3,
            impacto=3,
            confianza=self.confianza,
            fuente=self.fuente,
            version=self.version,
        )


class Reloj:
    """Reloj de los servicios: la hora real más un desfase que la prueba hace avanzar."""

    def __init__(self) -> None:
        self.desfase = timedelta()

    def ahora(self) -> datetime:
        return datetime.now(UTC) + self.desfase

    def avanzar(self, minutos: float) -> None:
        self.desfase += timedelta(minutes=minutos)


@pytest.fixture
def entorno():
    """Catálogo (Redes y Software), especialidad de Redes, acuerdo por prioridad y personas.

    Solo «tecnico» tiene la especialidad de Redes; «otro_tecnico» no tiene ninguna.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids: dict[str, uuid.UUID] = {clave: uuid.uuid4() for clave in PERSONAS}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            unidad = OrganizationalUnit(name="Facultad de Ingeniería", unit_type="facultad")
            session.add(unidad)
            await session.flush()
            area = AreaServicio(unit_id=unidad.id, name="Soporte")
            session.add(area)
            await session.flush()
            for nombre in ("Redes", "Software"):
                categoria = Categoria(area_id=area.id, name=nombre)
                session.add(categoria)
                await session.flush()
                ids[nombre] = categoria.id
            conectividad = Especialidad(category_id=ids["Redes"], name="Conectividad")
            session.add(conectividad)
            await session.flush()

            roles: dict[RoleName, Role] = {}
            for clave, (nombre, tipo, rol) in PERSONAS.items():
                session.add(
                    User(
                        id=ids[clave],
                        institutional_id=f"acp-{clave}",
                        full_name=nombre,
                        email=f"{clave}@example.test",
                        user_type=tipo,
                        is_active=True,
                        specialties=[conectividad] if clave == "tecnico" else [],
                    )
                )
                if rol not in roles:
                    roles[rol] = Role(name=rol)
                    session.add(roles[rol])
            await session.flush()
            for clave, (_, _, rol) in PERSONAS.items():
                session.add(UserRole(user_id=ids[clave], role_id=roles[rol].id))

            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            for prioridad, minutos in RESOLUCION_MINUTOS.items():
                session.add(
                    ServiceLevelVersion(
                        agreement_id=acuerdo.id,
                        version=1,
                        priority=prioridad,
                        first_response_minutes=30,
                        resolution_minutes=minutos,
                        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
                    )
                )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def reloj(monkeypatch) -> Reloj:
    """Sustituye `_ahora` de los servicios del ciclo de vida por un reloj controlable."""
    reloj = Reloj()
    for modulo in (sla_clock_service, seguimiento_service, asignacion_service):
        monkeypatch.setattr(modulo, "_ahora", reloj.ahora)
    return reloj


@pytest.fixture
def cliente(entorno, reloj):
    """Cliente HTTP. `como(persona)` entra con el rol de esa persona y `usar(confianza)`
    fija la confianza del clasificador del alta."""
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    def como(persona: str) -> TestClient:
        rol = PERSONAS[persona][2]
        fastapi_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=ids[persona],
            is_active=True,
            roles=[SimpleNamespace(role=SimpleNamespace(name=rol))],
        )
        return client

    def usar(confianza: float) -> None:
        clasificador = ClasificadorFijo(confianza)

        def servicio(session: AsyncSession = Depends(get_session)) -> ClasificacionService:
            return ClasificacionService(session, clasificador=clasificador)

        fastapi_app.dependency_overrides[get_clasificacion_service] = servicio

    fastapi_app.dependency_overrides[get_session] = sesion
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    usar(0.90)
    try:
        yield SimpleNamespace(como=como, usar=usar, ids=ids, reloj=reloj)
    finally:
        fastapi_app.dependency_overrides.clear()
