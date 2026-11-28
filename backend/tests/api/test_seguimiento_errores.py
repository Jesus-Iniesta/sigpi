"""Caminos de error de los endpoints de seguimiento (S5-24, HU-04.1).

Por cada acción sobre `/solicitudes/{id}/...` se prueba:

- 404 cuando la solicitud no existe.
- 409 cuando el estatus actual no admite la acción, sin modificar la solicitud
  ni escribir en la bitácora.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.enums import RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request, RequestLog

# Acción → (método HTTP, sufijo de la ruta, cuerpo de la petición).
ACCIONES: dict[str, tuple[str, str, dict | None]] = {
    "diagnostico": ("post", "diagnostico", {"diagnosis": "Cable dañado"}),
    "iniciar": ("post", "iniciar", None),
    "resolver": ("post", "resolver", {"solution": "Se cambió el cable"}),
    "confirmar": ("post", "confirmar", {}),
    "bitacora": ("get", "bitacora", None),
}

# Acciones que cambian el estatus, con un estatus que no las admite.
ESTATUS_QUE_NO_ADMITEN = [
    pytest.param("diagnostico", RequestStatus.RESOLVED, id="diagnosticar-una-resuelta"),
    pytest.param("diagnostico", RequestStatus.CLOSED, id="diagnosticar-una-cerrada"),
    pytest.param("iniciar", RequestStatus.CLOSED, id="iniciar-una-cerrada"),
    pytest.param("iniciar", RequestStatus.IN_PROGRESS, id="iniciar-una-en-atencion"),
    pytest.param("iniciar", RequestStatus.WAITING, id="iniciar-una-en-espera"),
    pytest.param("resolver", RequestStatus.WAITING, id="resolver-una-en-espera"),
    pytest.param("resolver", RequestStatus.CLOSED, id="resolver-una-cerrada"),
    pytest.param("resolver", RequestStatus.REGISTERED, id="resolver-una-registrada"),
    pytest.param("confirmar", RequestStatus.ASSIGNED, id="confirmar-una-asignada"),
    pytest.param("confirmar", RequestStatus.IN_PROGRESS, id="confirmar-una-en-atencion"),
    pytest.param("confirmar", RequestStatus.CLOSED, id="confirmar-una-cerrada"),
]


def _user(user_id: uuid.UUID, institutional_id: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )


def _como_tecnico(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name="support_agent"))],
    )


@pytest.fixture
def cliente():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"tecnico": uuid.uuid4(), "solicitante": uuid.uuid4()}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [_user(ids["tecnico"], "tec-001"), _user(ids["solicitante"], "sol-001")]
            )
            await session.commit()

    async def sesion():
        async with maker() as session:
            yield session

    asyncio.run(preparar())
    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como_tecnico(ids["tecnico"])
    try:
        yield TestClient(fastapi_app), maker, ids
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _crear_solicitud(maker, ids, status: RequestStatus) -> uuid.UUID:
    async def crear() -> uuid.UUID:
        async with maker() as session:
            request = Request(
                requester_id=ids["solicitante"],
                folio="SIG-0001",
                title="No hay conexión a la red",
                description="El laboratorio perdió conectividad.",
                physical_location="Edificio A, laboratorio 2",
                channel=RequestChannel.PORTAL,
                status=status,
                urgency=2,
                impact=2,
            )
            session.add(request)
            await session.commit()
            return request.id

    return asyncio.run(crear())


def _estado_y_bitacora(maker, request_id: uuid.UUID) -> tuple[RequestStatus, int]:
    async def leer() -> tuple[RequestStatus, int]:
        async with maker() as session:
            request = await session.get(Request, request_id)
            entradas = await session.scalar(
                select(func.count())
                .select_from(RequestLog)
                .where(RequestLog.request_id == request_id)
            )
            return request.status, entradas

    return asyncio.run(leer())


def _llamar(client: TestClient, accion: str, request_id: uuid.UUID):
    metodo, sufijo, cuerpo = ACCIONES[accion]
    ruta = f"/solicitudes/{request_id}/{sufijo}"
    if metodo == "get":
        return client.get(ruta)
    return client.post(ruta, json=cuerpo) if cuerpo is not None else client.post(ruta)


@pytest.mark.parametrize("accion", list(ACCIONES))
def test_una_solicitud_inexistente_responde_404(cliente, accion) -> None:
    client, _maker, _ids = cliente

    respuesta = _llamar(client, accion, uuid.uuid4())

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["detail"]


@pytest.mark.parametrize(("accion", "estatus"), ESTATUS_QUE_NO_ADMITEN)
def test_un_estatus_que_no_admite_la_accion_responde_409(cliente, accion, estatus) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, estatus)

    respuesta = _llamar(client, accion, request_id)

    assert respuesta.status_code == 409, respuesta.text
    assert estatus.value in respuesta.json()["detail"]
    assert _estado_y_bitacora(maker, request_id) == (estatus, 0)


def test_la_bitacora_no_depende_del_estatus(cliente) -> None:
    """Consultar la bitácora nunca es un conflicto: una solicitud cerrada también la tiene."""
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, RequestStatus.CLOSED)

    respuesta = _llamar(client, "bitacora", request_id)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []
