"""Pruebas de la bandeja de solicitudes asignadas: `GET /bandeja` (S5-04, HU-04.6).

- El técnico solo ve las solicitudes con su asignación vigente; las reasignadas a otra
  persona ya no aparecen, y las cerradas tampoco.
- Orden: P1 primero y, dentro de la misma prioridad, la fecha compromiso más cercana.
- `en_riesgo` se enciende cuando el tiempo consumido llega al 80 %.
- `todas=true` muestra las de todo el equipo solo a quien puede asignar.
- Sin sesión 401; sin permiso 403.
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
from app.api.routers.bandeja import get_bandeja_service
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import Categoria
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType, WaitReason
from app.models.identity import User
from app.models.request import Request, RequestAssignment, RequestSlaPause
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.solicitud_repository import SolicitudRepository
from app.services.bandeja_service import BandejaService

AHORA = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

# Tiempo de resolución (minutos) por prioridad.
RESOLUCION = {Priority.P1: 240, Priority.P2: 480, Priority.P3: 1000}

# folio: (prioridad, estatus, minutos desde el alta, minutos en espera, asignaciones)
# Cada asignación es (técnico, vigente).
SOLICITUDES = {
    # P2 dada de alta antes que SIG-0003, pero con 250 min en espera: vence después.
    "SIG-0001": (Priority.P2, RequestStatus.IN_PROGRESS, 300, 250, [("tomas", True)]),
    # P1 con 200 de 240 min consumidos (83.3 %): en riesgo.
    "SIG-0002": (Priority.P1, RequestStatus.ASSIGNED, 200, 0, [("tomas", True)]),
    "SIG-0003": (Priority.P2, RequestStatus.ASSIGNED, 60, 0, [("tomas", True)]),
    # P3 con 800 de 1000 min: justo el 80 %.
    "SIG-0005": (Priority.P3, RequestStatus.IN_PROGRESS, 800, 0, [("tomas", True)]),
    # P3 con 799 de 1000 min: 79.9 %, todavía no está en riesgo.
    "SIG-0006": (Priority.P3, RequestStatus.WAITING, 799, 0, [("tomas", True)]),
    # Reasignada de Tomás a Luis.
    "SIG-0007": (
        Priority.P1,
        RequestStatus.ASSIGNED,
        30,
        0,
        [("tomas", False), ("luis", True)],
    ),
    "SIG-0008": (Priority.P1, RequestStatus.CLOSED, 100, 0, [("tomas", True)]),
    "SIG-0009": (Priority.P1, RequestStatus.CLOSED_UNVERIFIED, 100, 0, [("tomas", True)]),
    # Sin asignar.
    "SIG-0010": (Priority.P1, RequestStatus.CLASSIFIED, 100, 0, []),
    # Sin prioridad ni SLA todavía.
    "SIG-0011": (None, RequestStatus.ASSIGNED, 10, 0, [("tomas", True)]),
}


def _como(user_id: uuid.UUID, *roles: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role)) for role in roles],
    )


@pytest.fixture
def entorno():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {key: uuid.uuid4() for key in ("tomas", "luis", "jefa", "categoria")}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key in ("tomas", "luis", "jefa"):
                session.add(
                    User(
                        id=ids[key],
                        institutional_id=f"u-{ids[key].hex[:8]}",
                        full_name=key.capitalize(),
                        email=f"{key}@example.test",
                        user_type=UserType.TECHNICAL,
                    )
                )
            session.add(Categoria(id=ids["categoria"], area_id=uuid.uuid4(), name="Redes"))
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            versiones = {}
            for prioridad, minutos in RESOLUCION.items():
                versiones[prioridad] = ServiceLevelVersion(
                    agreement_id=acuerdo.id,
                    version=1,
                    priority=prioridad,
                    first_response_minutes=30,
                    resolution_minutes=minutos,
                    valid_from=AHORA - timedelta(days=30),
                )
                session.add(versiones[prioridad])
            await session.flush()

            for folio, (prioridad, estatus, edad, espera, asignaciones) in SOLICITUDES.items():
                alta = AHORA - timedelta(minutes=edad)
                version = versiones.get(prioridad)
                ids[folio] = uuid.uuid4()
                request = Request(
                    id=ids[folio],
                    category_id=ids["categoria"],
                    service_level_version_id=version.id if version else None,
                    folio=folio,
                    title=f"Solicitud {folio}",
                    description="Falla.",
                    physical_location="Edificio B",
                    channel=RequestChannel.PORTAL,
                    status=estatus,
                    priority=prioridad,
                    created_at=alta,
                )
                session.add(request)
                if espera:
                    session.add(
                        RequestSlaPause(
                            request_id=request.id,
                            reason=WaitReason.EXTERNAL_INPUT,
                            started_by_id=ids["tomas"],
                            started_at=alta + timedelta(minutes=1),
                            ended_at=alta + timedelta(minutes=1 + espera),
                        )
                    )
                for tecnico, vigente in asignaciones:
                    session.add(
                        RequestAssignment(
                            request_id=request.id,
                            technician_id=ids[tecnico],
                            assigned_at=alta,
                            unassigned_at=None if vigente else alta + timedelta(minutes=5),
                        )
                    )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def cliente(entorno):
    maker, ids = entorno
    actual = {"usuario": _como(ids["tomas"], "support_agent")}

    async def sesion():
        async with maker() as session:
            yield session

    def servicio(session: AsyncSession = Depends(get_session)) -> BandejaService:
        return BandejaService(SolicitudRepository(session), reloj=lambda: AHORA)

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: actual["usuario"]
    fastapi_app.dependency_overrides[get_bandeja_service] = servicio
    try:
        yield TestClient(fastapi_app), actual, ids
    finally:
        fastapi_app.dependency_overrides.clear()


def _folios(respuesta) -> list[str]:
    return [item["folio"] for item in respuesta.json()]


def _por_folio(respuesta) -> dict[str, dict]:
    return {item["folio"]: item for item in respuesta.json()}


def test_el_tecnico_ve_solo_sus_asignadas_abiertas_por_prioridad_y_compromiso(cliente) -> None:
    client, _actual, _ids = cliente

    respuesta = client.get("/bandeja")

    assert respuesta.status_code == 200
    assert _folios(respuesta) == [
        "SIG-0002",
        "SIG-0003",
        "SIG-0001",
        "SIG-0005",
        "SIG-0006",
        "SIG-0011",
    ]


def test_las_reasignadas_a_otro_no_aparecen_y_si_en_la_bandeja_del_nuevo(cliente) -> None:
    client, actual, ids = cliente

    assert "SIG-0007" not in _folios(client.get("/bandeja"))

    actual["usuario"] = _como(ids["luis"], "support_agent")
    assert _folios(client.get("/bandeja")) == ["SIG-0007"]


def test_las_cerradas_no_aparecen(cliente) -> None:
    client, _actual, _ids = cliente

    folios = _folios(client.get("/bandeja"))

    assert "SIG-0008" not in folios
    assert "SIG-0009" not in folios


def test_misma_prioridad_ordena_por_fecha_compromiso_mas_cercana(cliente) -> None:
    client, _actual, _ids = cliente

    items = _por_folio(client.get("/bandeja", params={"prioridad": "P2"}))

    assert list(items) == ["SIG-0003", "SIG-0001"]
    compromiso_3 = datetime.fromisoformat(items["SIG-0003"]["fecha_compromiso"])
    compromiso_1 = datetime.fromisoformat(items["SIG-0001"]["fecha_compromiso"])
    assert compromiso_3 == AHORA + timedelta(minutes=420)
    assert compromiso_1 == AHORA + timedelta(minutes=430)


def test_cada_elemento_trae_los_datos_de_la_bandeja(cliente) -> None:
    client, _actual, _ids = cliente

    item = _por_folio(client.get("/bandeja"))["SIG-0002"]

    assert item["titulo"] == "Solicitud SIG-0002"
    assert item["estatus"] == "assigned"
    assert item["prioridad"] == "P1"
    assert item["categoria"] == "Redes"
    assert datetime.fromisoformat(item["fecha_registro"]).replace(tzinfo=UTC) == (
        AHORA - timedelta(minutes=200)
    )
    assert item["porcentaje_consumido"] == pytest.approx(83.3)
    assert item["en_riesgo"] is True


def test_cada_elemento_trae_el_request_id_para_enlazar_al_detalle(cliente) -> None:
    client, _actual, ids = cliente

    items = _por_folio(client.get("/bandeja"))

    for folio, item in items.items():
        assert uuid.UUID(item["request_id"]) == ids[folio]


@pytest.mark.parametrize(
    ("folio", "porcentaje", "en_riesgo"),
    [
        ("SIG-0005", 80.0, True),
        ("SIG-0006", 79.9, False),
        ("SIG-0003", 12.5, False),
        ("SIG-0001", 10.4, False),
    ],
)
def test_en_riesgo_cuando_el_tiempo_consumido_llega_al_80(
    cliente, folio, porcentaje, en_riesgo
) -> None:
    client, _actual, _ids = cliente

    item = _por_folio(client.get("/bandeja"))[folio]

    assert item["porcentaje_consumido"] == pytest.approx(porcentaje)
    assert item["en_riesgo"] is en_riesgo


def test_sin_sla_no_tiene_compromiso_ni_riesgo(cliente) -> None:
    client, _actual, _ids = cliente

    item = _por_folio(client.get("/bandeja"))["SIG-0011"]

    assert item["fecha_compromiso"] is None
    assert item["porcentaje_consumido"] is None
    assert item["en_riesgo"] is False


def test_filtra_por_estatus(cliente) -> None:
    client, _actual, _ids = cliente

    respuesta = client.get("/bandeja", params={"estatus": "in_progress"})

    assert _folios(respuesta) == ["SIG-0001", "SIG-0005"]


def test_el_jefe_con_todas_ve_las_de_todo_el_equipo(cliente) -> None:
    client, actual, ids = cliente
    actual["usuario"] = _como(ids["jefa"], "service_manager")

    assert _folios(client.get("/bandeja")) == []
    assert _folios(client.get("/bandeja", params={"todas": "true"})) == [
        "SIG-0002",
        "SIG-0007",
        "SIG-0003",
        "SIG-0001",
        "SIG-0005",
        "SIG-0006",
        "SIG-0011",
    ]


@pytest.mark.parametrize("rol", ["classifier", "requester"])
def test_todas_sin_permiso_de_asignar_responde_403(cliente, rol) -> None:
    client, actual, ids = cliente
    actual["usuario"] = _como(ids["tomas"], rol)

    assert client.get("/bandeja").status_code == 200
    respuesta = client.get("/bandeja", params={"todas": "true"})

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "forbidden"


def test_sin_permiso_de_lectura_responde_403(cliente) -> None:
    client, actual, ids = cliente
    actual["usuario"] = _como(ids["tomas"])

    assert client.get("/bandeja").status_code == 403


def test_sin_sesion_responde_401(entorno) -> None:
    maker, _ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    try:
        respuesta = TestClient(fastapi_app).get("/bandeja")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_con_el_reloj_real_responde_con_las_mismas_solicitudes(entorno) -> None:
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(
        ids["tomas"], "support_agent"
    )
    try:
        respuesta = TestClient(fastapi_app).get("/bandeja")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert set(_folios(respuesta)) == {
        "SIG-0001",
        "SIG-0002",
        "SIG-0003",
        "SIG-0005",
        "SIG-0006",
        "SIG-0011",
    }
