"""Pruebas de los indicadores del servicio y su exportación (S5-05, HU-09.1 y HU-09.2).

Usan los routers, el servicio y el repositorio reales contra SQLite en memoria, con un
conjunto conocido de solicitudes. El usuario en sesión se reemplaza con
`dependency_overrides`; `require_permission` solo consulta sus roles.
"""

import asyncio
import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.domain.indicadores import SolicitudMedida, cumplio_sla, esta_vencida, resumir
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria
from app.models.enums import Priority, RequestChannel, RequestStatus
from app.models.organization import OrganizationalUnit
from app.models.request import Request
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services.indicador_service import RangoFechasInvalidoError, resolver_rango

DIA = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _en_sesion(role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), is_active=True, roles=[SimpleNamespace(role=SimpleNamespace(name=role))]
    )


def _solicitud(folio: str, **campos) -> Request:
    base = {
        "folio": folio,
        "title": f"Solicitud {folio}",
        "description": "Descripción",
        "physical_location": "Edificio A",
        "channel": RequestChannel.PORTAL,
        "status": RequestStatus.REGISTERED,
        "created_at": DIA,
    }
    base.update(campos)
    return Request(**base)


@pytest.fixture
def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        unit_id, area_id, cat_id, sla_id = (uuid.uuid4() for _ in range(4))
        p2_id, p3_id = uuid.uuid4(), uuid.uuid4()
        async with maker() as session:
            session.add(OrganizationalUnit(id=unit_id, name="DTIC", unit_type="dept", code="DTIC"))
            session.add(AreaServicio(id=area_id, unit_id=unit_id, name="Soporte"))
            session.add(Categoria(id=cat_id, area_id=area_id, name="Conexión inalámbrica"))
            session.add(ServiceLevelAgreement(id=sla_id, name="General", is_default=True))
            await session.flush()
            for vid, prio, minutos in ((p2_id, Priority.P2, 240), (p3_id, Priority.P3, 480)):
                session.add(
                    ServiceLevelVersion(
                        id=vid,
                        agreement_id=sla_id,
                        version=1,
                        priority=prio,
                        first_response_minutes=30,
                        resolution_minutes=minutos,
                        valid_from=DIA - timedelta(days=60),
                    )
                )
            await session.flush()
            session.add_all(
                [
                    # Resuelta en tiempo: 200 ≤ 240; primera respuesta a los 10 min.
                    _solicitud(
                        "SIGPI-1",
                        category_id=cat_id,
                        priority=Priority.P2,
                        service_level_version_id=p2_id,
                        status=RequestStatus.RESOLVED,
                        first_response_at=DIA + timedelta(minutes=10),
                        resolved_at=DIA + timedelta(minutes=200),
                        resolution_minutes=200,
                    ),
                    # Resuelta fuera de tiempo: 600 > 480; primera respuesta a los 30 min.
                    _solicitud(
                        "SIGPI-2",
                        category_id=cat_id,
                        priority=Priority.P3,
                        service_level_version_id=p3_id,
                        status=RequestStatus.CLOSED,
                        first_response_at=DIA + timedelta(minutes=30),
                        resolved_at=DIA + timedelta(minutes=600),
                        closed_at=DIA + timedelta(minutes=700),
                        resolution_minutes=600,
                    ),
                    # Abierta y vencida (creada hace días con P2 de 240 min).
                    _solicitud(
                        "SIGPI-3",
                        category_id=cat_id,
                        priority=Priority.P2,
                        service_level_version_id=p2_id,
                        status=RequestStatus.IN_PROGRESS,
                        created_at=DIA + timedelta(days=1),
                    ),
                    # Abierta sin prioridad ni categoría ni acuerdo: no cuenta como vencida.
                    _solicitud("SIGPI-4", created_at=DIA + timedelta(days=1)),
                    # Fuera del rango consultado.
                    _solicitud("SIGPI-5", created_at=DIA - timedelta(days=40)),
                ]
            )
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(
        RoleName.SERVICE_MANAGER.value
    )
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


RANGO = {"desde": "2026-11-09", "hasta": "2026-11-12"}


def test_resumen_con_conjunto_conocido(client):
    response = client.get("/indicadores/resumen", params=RANGO)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["por_estatus"] == {"resolved": 1, "closed": 1, "in_progress": 1, "registered": 1}
    assert body["por_prioridad"] == {"P2": 2, "P3": 1, "sin_prioridad": 1}
    assert body["por_categoria"] == {"Conexión inalámbrica": 3, "Sin categoría": 1}
    assert body["resueltas_con_sla"] == 2
    assert body["resueltas_en_tiempo"] == 1
    assert body["cumplimiento_sla"] == 50.0
    assert body["tiempo_medio_primera_respuesta_min"] == 20.0
    assert body["tiempo_medio_resolucion_min"] == 400.0
    assert body["abiertas_vencidas"] == 1
    assert body["por_dia"] == [
        {"fecha": "2026-11-09", "total": 0},
        {"fecha": "2026-11-10", "total": 2},
        {"fecha": "2026-11-11", "total": 2},
        {"fecha": "2026-11-12", "total": 0},
    ]


def test_rango_sin_solicitudes_devuelve_ceros(client):
    response = client.get(
        "/indicadores/resumen", params={"desde": "2025-01-01", "hasta": "2025-01-02"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["por_estatus"] == {} and body["por_prioridad"] == {} and body["por_categoria"] == {}
    assert body["cumplimiento_sla"] == 0.0
    assert body["tiempo_medio_primera_respuesta_min"] == 0.0
    assert body["tiempo_medio_resolucion_min"] == 0.0
    assert body["abiertas_vencidas"] == 0
    assert [d["total"] for d in body["por_dia"]] == [0, 0]


def test_resumen_por_omision_son_los_ultimos_30_dias(client):
    body = client.get("/indicadores/resumen").json()

    assert date.fromisoformat(body["hasta"]) - date.fromisoformat(body["desde"]) == timedelta(
        days=29
    )
    assert len(body["por_dia"]) == 30


def test_csv_tiene_encabezado_una_fila_por_solicitud_y_acentos(client):
    response = client.get("/indicadores/exportar.csv", params=RANGO)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "indicadores_2026-11-09_2026-11-12.csv" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")  # BOM para Excel
    filas = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert filas[0] == [
        "Folio",
        "Título",
        "Categoría",
        "Prioridad",
        "Estatus",
        "Fecha de alta",
        "Primera respuesta",
        "Resuelta",
        "Cerrada",
        "Minutos de resolución",
        "Cumplió SLA",
    ]
    por_folio = {fila[0]: fila for fila in filas[1:]}
    assert sorted(por_folio) == ["SIGPI-1", "SIGPI-2", "SIGPI-3", "SIGPI-4"]
    assert por_folio["SIGPI-1"][2] == "Conexión inalámbrica"
    assert por_folio["SIGPI-1"][5] == "2026-11-10 09:00"
    assert por_folio["SIGPI-1"][9:] == ["200", "sí"]
    assert por_folio["SIGPI-2"][9:] == ["600", "no"]
    assert por_folio["SIGPI-4"][9:] == ["", ""]


def test_csv_de_rango_vacio_solo_tiene_encabezado(client):
    response = client.get(
        "/indicadores/exportar.csv", params={"desde": "2025-01-01", "hasta": "2025-01-01"}
    )

    filas = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(filas) == 1


@pytest.mark.parametrize("ruta", ["/indicadores/resumen", "/indicadores/exportar.csv"])
def test_desde_posterior_a_hasta_responde_422(client, ruta):
    response = client.get(ruta, params={"desde": "2026-11-12", "hasta": "2026-11-01"})

    assert response.status_code == 422
    assert response.json()["code"] == "business_rule_violation"


@pytest.mark.parametrize("ruta", ["/indicadores/resumen", "/indicadores/exportar.csv"])
def test_sin_sesion_responde_401(client, ruta):
    fastapi_app.dependency_overrides.pop(get_current_user)

    assert client.get(ruta).status_code == 401


@pytest.mark.parametrize("ruta", ["/indicadores/resumen", "/indicadores/exportar.csv"])
def test_sin_permiso_de_reportes_responde_403(client, ruta):
    fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(
        RoleName.REQUESTER.value
    )

    assert client.get(ruta).status_code == 403


@pytest.mark.parametrize("rol", [RoleName.ADMINISTRATOR, RoleName.SERVICE_MANAGER])
def test_roles_con_reportes_pueden_consultar(client, rol):
    fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(rol.value)

    assert client.get("/indicadores/resumen", params=RANGO).status_code == 200


# --- Dominio puro -------------------------------------------------------------


def _medida(**campos) -> SolicitudMedida:
    base = {
        "folio": "F",
        "titulo": "T",
        "categoria": None,
        "prioridad": None,
        "estatus": "resolved",
        "creada": DIA,
        "primera_respuesta": None,
        "resuelta": None,
        "cerrada": None,
        "minutos_resolucion": None,
        "minutos_comprometidos": None,
        "abierta": False,
    }
    base.update(campos)
    return SolicitudMedida(**base)


def test_cumplio_sla_en_el_limite_cuenta_como_en_tiempo():
    assert cumplio_sla(_medida(minutos_resolucion=240, minutos_comprometidos=240)) is True
    assert cumplio_sla(_medida(minutos_resolucion=241, minutos_comprometidos=240)) is False
    assert cumplio_sla(_medida(minutos_resolucion=100)) is None


def test_vencida_solo_si_abierta_con_acuerdo_y_rebasada():
    assert esta_vencida(_medida(abierta=True, minutos_comprometidos=60, minutos_efectivos=61))
    assert not esta_vencida(_medida(abierta=True, minutos_comprometidos=60, minutos_efectivos=60))
    assert not esta_vencida(_medida(abierta=False, minutos_comprometidos=60, minutos_efectivos=99))
    assert not esta_vencida(_medida(abierta=True, minutos_efectivos=99))


def test_resumir_lista_vacia_da_ceros():
    resumen = resumir([], date(2026, 1, 1), date(2026, 1, 1))

    assert resumen.total == 0 and resumen.cumplimiento_sla == 0.0
    assert [d.total for d in resumen.por_dia] == [0]


def test_resolver_rango_valida_y_completa():
    hoy = date(2026, 11, 25)
    assert resolver_rango(None, None, hoy) == (date(2026, 10, 27), hoy)
    assert resolver_rango(date(2026, 11, 1), None, hoy) == (date(2026, 11, 1), hoy)
    with pytest.raises(RangoFechasInvalidoError):
        resolver_rango(date(2026, 11, 2), date(2026, 11, 1))
