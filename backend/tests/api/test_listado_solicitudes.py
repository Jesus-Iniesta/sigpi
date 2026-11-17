"""Pruebas del listado de solicitudes: `GET /solicitudes`.

- El personal ve todas las solicitudes; el solicitante, solo las suyas.
- Búsqueda por folio, título, descripción o nombre del solicitante, sin distinguir
  mayúsculas; `%` y `_` se buscan como texto literal.
- Filtros por estatus y prioridad, y paginación con el total de coincidencias.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import Categoria
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _como(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """Base SQLite con un técnico, dos solicitantes y tres solicitudes.

    - SIG-0001 (Sara, Redes, P2, Clasificada): «Sin red en el laboratorio».
    - SIG-0002 (Sara, sin categoría, P3, Registrada): «Impresora atascada».
    - SIG-0003 (Olga, Redes, P1, Resuelta): «Correo caído al 100%».
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {key: uuid.uuid4() for key in ("tecnico", "sara", "olga", "categoria")}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key, nombre in (
                ("tecnico", "Tomás Técnico"),
                ("sara", "Sara Solicitante"),
                ("olga", "Olga Otra"),
            ):
                session.add(
                    User(
                        id=ids[key],
                        institutional_id=f"u-{ids[key].hex[:8]}",
                        full_name=nombre,
                        email=f"{key}@example.test",
                        user_type=UserType.ACADEMIC,
                    )
                )
            session.add(Categoria(id=ids["categoria"], area_id=uuid.uuid4(), name="Redes"))

            def solicitud(folio, requester, titulo, descripcion, estatus, prioridad, dias, cat):
                return Request(
                    id=uuid.uuid4(),
                    requester_id=ids[requester],
                    category_id=ids["categoria"] if cat else None,
                    folio=folio,
                    title=titulo,
                    description=descripcion,
                    physical_location="Edificio B",
                    channel=RequestChannel.PORTAL,
                    status=estatus,
                    priority=prioridad,
                    created_at=INICIO + timedelta(days=dias),
                )

            session.add_all(
                [
                    solicitud(
                        "SIG-0001",
                        "sara",
                        "Sin red en el laboratorio",
                        "No hay conexión desde la mañana.",
                        RequestStatus.CLASSIFIED,
                        Priority.P2,
                        0,
                        True,
                    ),
                    solicitud(
                        "SIG-0002",
                        "sara",
                        "Impresora atascada",
                        "El papel se queda atorado.",
                        RequestStatus.REGISTERED,
                        Priority.P3,
                        1,
                        False,
                    ),
                    solicitud(
                        "SIG-0003",
                        "olga",
                        "Correo caído al 100%",
                        "No abre el buzón.",
                        RequestStatus.RESOLVED,
                        Priority.P1,
                        2,
                        True,
                    ),
                ]
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
    actual = {"usuario": _como(ids["tecnico"], "support_agent")}

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: actual["usuario"]
    try:
        yield TestClient(fastapi_app), actual, ids
    finally:
        fastapi_app.dependency_overrides.clear()


def _folios(respuesta) -> list[str]:
    return [item["folio"] for item in respuesta.json()["items"]]


def test_el_personal_ve_todas_de_la_mas_reciente_a_la_mas_antigua(cliente) -> None:
    client, _actual, _ids = cliente

    respuesta = client.get("/solicitudes")

    assert respuesta.status_code == 200
    assert _folios(respuesta) == ["SIG-0003", "SIG-0002", "SIG-0001"]
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 3
    assert cuerpo["limit"] == 20
    assert cuerpo["offset"] == 0


def test_cada_renglon_trae_id_categoria_y_solicitante(cliente) -> None:
    client, _actual, _ids = cliente

    items = {i["folio"]: i for i in client.get("/solicitudes").json()["items"]}

    assert uuid.UUID(items["SIG-0001"]["id"])
    assert items["SIG-0001"]["category_name"] == "Redes"
    assert items["SIG-0001"]["requester_name"] == "Sara Solicitante"
    assert items["SIG-0002"]["category_name"] is None


def test_el_solicitante_solo_ve_las_suyas(cliente) -> None:
    client, actual, ids = cliente
    actual["usuario"] = _como(ids["sara"], "requester")

    respuesta = client.get("/solicitudes")

    assert respuesta.status_code == 200
    assert _folios(respuesta) == ["SIG-0002", "SIG-0001"]
    assert respuesta.json()["total"] == 2


@pytest.mark.parametrize(
    ("texto", "esperados"),
    [
        ("0002", ["SIG-0002"]),
        ("sig-0003", ["SIG-0003"]),
        ("RED", ["SIG-0001"]),
        ("atorado", ["SIG-0002"]),
        ("olga", ["SIG-0003"]),
        ("sara", ["SIG-0002", "SIG-0001"]),
        ("no existe", []),
    ],
)
def test_la_busqueda_encuentra_por_folio_titulo_descripcion_o_solicitante(
    cliente, texto, esperados
) -> None:
    client, _actual, _ids = cliente

    respuesta = client.get("/solicitudes", params={"q": texto})

    assert respuesta.status_code == 200
    assert _folios(respuesta) == esperados
    assert respuesta.json()["total"] == len(esperados)


def test_los_comodines_de_sql_se_buscan_como_texto_literal(cliente) -> None:
    client, _actual, _ids = cliente

    solo_porcentaje = client.get("/solicitudes", params={"q": "100%"})
    guion_bajo = client.get("/solicitudes", params={"q": "_"})

    assert _folios(solo_porcentaje) == ["SIG-0003"]
    assert _folios(guion_bajo) == []


def test_filtra_por_estatus_y_por_prioridad(cliente) -> None:
    client, _actual, _ids = cliente

    por_estatus = client.get("/solicitudes", params={"status": "resolved"})
    por_prioridad = client.get("/solicitudes", params={"priority": "P2"})
    combinado = client.get("/solicitudes", params={"status": "resolved", "priority": "P2"})

    assert _folios(por_estatus) == ["SIG-0003"]
    assert _folios(por_prioridad) == ["SIG-0001"]
    assert _folios(combinado) == []


def test_pagina_y_reporta_el_total_de_coincidencias(cliente) -> None:
    client, _actual, _ids = cliente

    primera = client.get("/solicitudes", params={"limit": 2, "offset": 0})
    segunda = client.get("/solicitudes", params={"limit": 2, "offset": 2})

    assert _folios(primera) == ["SIG-0003", "SIG-0002"]
    assert _folios(segunda) == ["SIG-0001"]
    assert primera.json()["total"] == segunda.json()["total"] == 3


@pytest.mark.parametrize(
    "parametros",
    [{"status": "inventado"}, {"priority": "P9"}, {"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_rechaza_parametros_invalidos(cliente, parametros) -> None:
    client, _actual, _ids = cliente

    assert client.get("/solicitudes", params=parametros).status_code == 422


def test_sin_sesion_responde_401(cliente) -> None:
    client, _actual, _ids = cliente
    fastapi_app.dependency_overrides.pop(get_current_user)

    assert client.get("/solicitudes").status_code == 401


def test_un_rol_sin_permiso_de_lectura_responde_403(cliente) -> None:
    client, actual, ids = cliente
    actual["usuario"] = _como(ids["tecnico"], "rol_inexistente")

    assert client.get("/solicitudes").status_code == 403