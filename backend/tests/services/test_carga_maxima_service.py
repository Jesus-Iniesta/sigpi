"""La asignación automática respeta la carga máxima, salvo en P1 (S5-14, HU-03.3)."""

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.db.base import Base
from app.models.catalog import AreaServicio, Categoria, Especialidad
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestAssignment
from app.services.asignacion_service import AsignacionService


@pytest.fixture
def maker():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    sesiones = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(preparar())
    try:
        yield sesiones
    finally:
        asyncio.run(engine.dispose())


async def _escenario(session, *, topes: dict[str, int | None], cargas: dict[str, int]):
    """Técnicos con tope (`topes`) y solicitudes activas ya asignadas (`cargas`)."""
    unidad = OrganizationalUnit(name="Facultad de prueba", unit_type="facultad")
    session.add(unidad)
    await session.flush()
    area = AreaServicio(unit_id=unidad.id, name="Soporte")
    session.add(area)
    await session.flush()
    categoria = Categoria(area_id=area.id, name="Redes")
    session.add(categoria)
    await session.flush()
    especialidad = Especialidad(category_id=categoria.id, name="Conectividad")
    session.add(especialidad)
    solicitante = User(
        id=uuid.uuid4(),
        institutional_id="u-sol",
        full_name="Solicitante",
        email="sol@example.test",
        user_type=UserType.ADMINISTRATIVE,
    )
    session.add(solicitante)
    tecnicos: dict[str, User] = {}
    for nombre, tope in topes.items():
        tecnico = User(
            id=uuid.uuid4(),
            institutional_id=f"u-{nombre}",
            full_name=nombre.title(),
            email=f"{nombre}@example.test",
            user_type=UserType.TECHNICAL,
            is_active=True,
            max_load=tope,
            specialties=[especialidad],
        )
        session.add(tecnico)
        tecnicos[nombre] = tecnico
    await session.flush()
    for nombre, cantidad in cargas.items():
        for n in range(cantidad):
            previa = _solicitud(solicitante.id, categoria.id, f"{nombre}-{n}", Priority.P3)
            previa.status = RequestStatus.IN_PROGRESS
            session.add(previa)
            await session.flush()
            session.add(
                RequestAssignment(
                    request_id=previa.id, technician_id=tecnicos[nombre].id, is_automatic=False
                )
            )
    await session.commit()
    return solicitante, categoria, tecnicos


def _solicitud(solicitante_id, categoria_id, folio: str, prioridad: Priority) -> Request:
    return Request(
        requester_id=solicitante_id,
        category_id=categoria_id,
        folio=f"SIG-{folio}",
        title="t",
        description="d",
        physical_location="p",
        channel=RequestChannel.PORTAL,
        status=RequestStatus.CLASSIFIED,
        priority=prioridad,
    )


async def _asignar(session, solicitante, categoria, prioridad: Priority):
    nueva = _solicitud(solicitante.id, categoria.id, "NUEVA", prioridad)
    session.add(nueva)
    await session.commit()
    resultado = await AsignacionService(session).asignar_automaticamente(nueva.id)
    return nueva, resultado


def _correr(sesiones, topes, cargas, prioridad):
    async def correr():
        async with sesiones() as session:
            solicitante, categoria, tecnicos = await _escenario(session, topes=topes, cargas=cargas)
            nueva, resultado = await _asignar(session, solicitante, categoria, prioridad)
            vigente = await session.scalar(
                select(RequestAssignment).where(
                    RequestAssignment.request_id == nueva.id,
                    RequestAssignment.unassigned_at.is_(None),
                )
            )
            await session.refresh(nueva)
            return tecnicos, nueva, resultado, vigente

    return asyncio.run(correr())


def test_no_p1_salta_al_tecnico_en_su_carga_maxima(maker):
    # Sin la regla ganaría Ana (109 contra 106), pero ya tiene su tope de 1 solicitud.
    tecnicos, nueva, resultado, vigente = _correr(
        maker, {"ana": 1, "beto": 5}, {"ana": 1, "beto": 4}, Priority.P3
    )
    assert resultado is not None
    assert vigente.technician_id == tecnicos["beto"].id
    assert nueva.status == RequestStatus.ASSIGNED


def test_p1_ignora_la_carga_maxima_y_asigna_al_mejor_puntaje(maker):
    tecnicos, nueva, resultado, vigente = _correr(
        maker, {"ana": 1, "beto": 5}, {"ana": 1, "beto": 4}, Priority.P1
    )
    assert resultado is not None
    assert vigente.technician_id == tecnicos["ana"].id
    assert nueva.status == RequestStatus.ASSIGNED


def test_no_p1_con_todos_al_tope_queda_en_la_cola_general(maker):
    _, nueva, resultado, vigente = _correr(
        maker, {"ana": 1, "beto": 1}, {"ana": 1, "beto": 1}, Priority.P2
    )
    assert resultado is None
    assert vigente is None
    assert nueva.status == RequestStatus.CLASSIFIED


def test_p1_con_todos_al_tope_se_asigna_igual(maker):
    _, nueva, resultado, vigente = _correr(
        maker, {"ana": 1, "beto": 1}, {"ana": 1, "beto": 1}, Priority.P1
    )
    assert resultado is not None
    assert vigente is not None
    assert nueva.status == RequestStatus.ASSIGNED


def test_sin_tope_configurado_se_sigue_asignando(maker):
    _, _, resultado, vigente = _correr(maker, {"ana": None}, {"ana": 6}, Priority.P4)
    assert resultado is not None
    assert vigente is not None
