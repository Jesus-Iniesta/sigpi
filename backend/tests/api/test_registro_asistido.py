"""Pruebas del registro asistido y la contingencia (S3-11, HU-01.3).

Cubren, por HTTP, `POST /solicitudes/asistido`:

- Alta válida por teléfono o en persona, con su canal de origen y su bitácora.
- Permisos: solo roles con `requests.create_assisted` pueden usar el endpoint.
- Datos inválidos: canal no permitido, campos incompletos, referencias inexistentes.
- Contingencia: si el solicitante no aparece en SIGPI, la solicitud se registra igual,
  con estado «por verificar» y una nota en la bitácora que explica el motivo.

Las pruebas usan SQLite en memoria (no necesitan PostgreSQL) y reemplazan al usuario
autenticado, igual que las pruebas de S3-17.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.domain.estados import estado_inicial
from app.main import app as fastapi_app
from app.models.enums import RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.schemas.request import RequestAssistedCreate

ACTIVE_ID = "uaem-local-001"  # solicitante con cuenta activa en SIGPI
INACTIVE_ID = "uaem-baja-002"  # solicitante con cuenta dada de baja
UNKNOWN_ID = "desconocido-999"  # no existe en SIGPI ni en el directorio simulado
DIRECTORY_ONLY_ID = "uaem2026001"  # existe en el directorio simulado, pero sin cuenta en SIGPI

# Roles que tienen el permiso `requests.create_assisted` (ver core/permissions.py).
ROLES_PERMITIDOS = ["support_agent", "service_manager", "administrator"]
ROLES_SIN_PERMISO = ["requester", "classifier", "knowledge_manager", "auditor"]


def _user(user_id: uuid.UUID, institutional_id: str, *, active: bool = True) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=active,
    )


def _como(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    """Usuario autenticado con un solo rol (lo único que consulta `require_permission`)."""
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """Base SQLite en memoria con un técnico, un solicitante activo y uno dado de baja."""
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
                [
                    _user(ids["tecnico"], "tec-001"),
                    _user(ids["solicitante"], ACTIVE_ID),
                    _user(uuid.uuid4(), INACTIVE_ID, active=False),
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
    """Cliente HTTP autenticado como técnico de soporte (`support_agent`)."""
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(
        ids["tecnico"], "support_agent"
    )
    try:
        yield TestClient(fastapi_app), ids
    finally:
        fastapi_app.dependency_overrides.clear()


def _autenticar_como(ids, role: str) -> None:
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids["tecnico"], role)


def _cuerpo(**cambios) -> dict:
    cuerpo = {
        "requester_institutional_id": ACTIVE_ID,
        "title": "Sin acceso al correo",
        "description": "No puede entrar a su buzón.",
        "physical_location": "Edificio B, cubículo 4",
        "channel": "phone",
    }
    cuerpo.update(cambios)
    return cuerpo


def _bitacora(client: TestClient, request_id: str) -> list[dict]:
    respuesta = client.get(f"/solicitudes/{request_id}/bitacora")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# --- Alta válida y canal de origen ------------------------------------------------


@pytest.mark.parametrize("canal", ["phone", "in_person"])
def test_registro_asistido_guarda_el_canal_de_origen(cliente, canal) -> None:
    client, ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(channel=canal))

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["channel"] == canal
    assert datos["status"] == "registered"
    assert datos["requester_id"] == str(ids["solicitante"])
    assert datos["requester_institutional_id"] == ACTIVE_ID
    assert datos["folio"] == "SIG-0001"


def test_registro_asistido_con_identificador_interno_del_solicitante(cliente) -> None:
    client, ids = cliente
    cuerpo = _cuerpo(requester_id=str(ids["solicitante"]))
    del cuerpo["requester_institutional_id"]

    respuesta = client.post("/solicitudes/asistido", json=cuerpo)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["requester_id"] == str(ids["solicitante"])


def test_los_folios_del_registro_asistido_son_consecutivos(cliente) -> None:
    client, _ids = cliente

    primero = client.post("/solicitudes/asistido", json=_cuerpo(title="Primera"))
    segundo = client.post("/solicitudes/asistido", json=_cuerpo(title="Segunda"))

    assert primero.json()["folio"] == "SIG-0001"
    assert segundo.json()["folio"] == "SIG-0002"


def test_registro_asistido_calcula_la_prioridad_con_la_matriz(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(urgency=3, impact=3))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["priority"] == "P1"


def test_registro_asistido_rechaza_la_edicion_directa_de_la_prioridad(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(priority="P1"))

    assert respuesta.status_code == 422


# --- Bitácora: queda registrado quién capturó y por qué canal ----------------------


@pytest.mark.parametrize(
    ("canal", "accion"),
    [
        ("phone", "Solicitud registrada por teléfono"),
        ("in_person", "Solicitud registrada de forma presencial"),
    ],
)
def test_la_bitacora_registra_al_tecnico_y_el_canal(cliente, canal, accion) -> None:
    client, ids = cliente

    creada = client.post("/solicitudes/asistido", json=_cuerpo(channel=canal)).json()
    entradas = _bitacora(client, creada["id"])

    assert len(entradas) == 1
    assert entradas[0]["author_id"] == str(ids["tecnico"])
    assert entradas[0]["action"] == accion
    assert entradas[0]["previous_status"] is None
    assert entradas[0]["new_status"] == "registered"
    assert "Registro asistido" in entradas[0]["notes"]


# --- Permisos ----------------------------------------------------------------------


@pytest.mark.parametrize("rol", ROLES_PERMITIDOS)
def test_los_roles_con_permiso_pueden_registrar(cliente, rol) -> None:
    client, ids = cliente
    _autenticar_como(ids, rol)

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo())

    assert respuesta.status_code == 201, respuesta.text


@pytest.mark.parametrize("rol", ROLES_SIN_PERMISO)
def test_los_roles_sin_permiso_reciben_403(cliente, rol) -> None:
    client, ids = cliente
    _autenticar_como(ids, rol)

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo())

    assert respuesta.status_code == 403


def test_sin_iniciar_sesion_responde_401(entorno) -> None:
    maker, _ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    # Solo se reemplaza la sesión de base de datos: sin token, `get_current_user` responde 401.
    fastapi_app.dependency_overrides[get_session] = sesion
    try:
        respuesta = TestClient(fastapi_app).post("/solicitudes/asistido", json=_cuerpo())
    finally:
        fastapi_app.dependency_overrides.clear()

    assert respuesta.status_code == 401


# --- Datos inválidos ---------------------------------------------------------------


def test_el_canal_portal_no_se_admite_en_el_registro_asistido(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(channel="portal"))

    assert respuesta.status_code == 422


def test_el_canal_es_obligatorio(cliente) -> None:
    client, _ids = cliente
    cuerpo = _cuerpo()
    del cuerpo["channel"]

    respuesta = client.post("/solicitudes/asistido", json=cuerpo)

    assert respuesta.status_code == 422


def test_un_canal_desconocido_se_rechaza(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(channel="correo"))

    assert respuesta.status_code == 422


@pytest.mark.parametrize("campo", ["title", "description", "physical_location"])
def test_los_campos_obligatorios_no_pueden_ir_vacios(cliente, campo) -> None:
    client, _ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(**{campo: ""}))

    assert respuesta.status_code == 422


def test_se_exige_una_sola_referencia_al_solicitante(cliente) -> None:
    client, ids = cliente
    sin_referencia = _cuerpo()
    del sin_referencia["requester_institutional_id"]

    ninguna = client.post("/solicitudes/asistido", json=sin_referencia)
    ambas = client.post("/solicitudes/asistido", json=_cuerpo(requester_id=str(ids["solicitante"])))

    assert ninguna.status_code == 422
    assert ambas.status_code == 422


def test_un_solicitante_dado_de_baja_se_rechaza(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post(
        "/solicitudes/asistido", json=_cuerpo(requester_institutional_id=INACTIVE_ID)
    )

    assert respuesta.status_code == 422
    assert "inactive" in respuesta.json()["detail"]


def test_una_categoria_inexistente_se_rechaza(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post("/solicitudes/asistido", json=_cuerpo(category_id=str(uuid.uuid4())))

    assert respuesta.status_code == 422
    assert "category" in respuesta.json()["detail"]


def test_una_solicitud_rechazada_no_consume_folio(cliente) -> None:
    client, _ids = cliente

    client.post("/solicitudes/asistido", json=_cuerpo(channel="portal"))
    valida = client.post("/solicitudes/asistido", json=_cuerpo())

    assert valida.json()["folio"] == "SIG-0001"


# --- Contingencia: solicitante no localizado -----------------------------------------


def test_solicitante_no_localizado_se_registra_como_por_verificar(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post(
        "/solicitudes/asistido", json=_cuerpo(requester_institutional_id=UNKNOWN_ID)
    )

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "pending_verification"
    assert datos["requester_id"] is None
    assert datos["requester_institutional_id"] == UNKNOWN_ID
    assert datos["channel"] == "phone"


def test_la_bitacora_explica_que_no_aparece_en_el_directorio(cliente) -> None:
    client, ids = cliente

    creada = client.post(
        "/solicitudes/asistido", json=_cuerpo(requester_institutional_id=UNKNOWN_ID)
    ).json()
    entradas = _bitacora(client, creada["id"])

    assert len(entradas) == 1
    assert entradas[0]["author_id"] == str(ids["tecnico"])
    assert entradas[0]["new_status"] == "pending_verification"
    assert UNKNOWN_ID in entradas[0]["notes"]
    assert "por verificar" in entradas[0]["notes"]
    assert "no aparece en el directorio" in entradas[0]["notes"]


def test_solicitante_reconocido_en_el_directorio_sin_cuenta_queda_por_verificar(cliente) -> None:
    client, _ids = cliente

    creada = client.post(
        "/solicitudes/asistido", json=_cuerpo(requester_institutional_id=DIRECTORY_ONLY_ID)
    ).json()
    entradas = _bitacora(client, creada["id"])

    assert creada["status"] == "pending_verification"
    assert creada["requester_id"] is None
    assert "el directorio lo reconoce" in entradas[0]["notes"]


def test_la_contingencia_no_afecta_a_los_solicitantes_localizados(cliente) -> None:
    client, ids = cliente

    desconocido = client.post(
        "/solicitudes/asistido", json=_cuerpo(requester_institutional_id=UNKNOWN_ID)
    ).json()
    localizado = client.post("/solicitudes/asistido", json=_cuerpo()).json()
    entradas = _bitacora(client, localizado["id"])

    assert desconocido["folio"] == "SIG-0001"
    assert localizado["folio"] == "SIG-0002"
    assert localizado["status"] == "registered"
    assert localizado["requester_id"] == str(ids["solicitante"])
    assert "por verificar" not in entradas[0]["notes"]


def test_el_identificador_del_solicitante_se_guarda_sin_espacios_sobrantes(cliente) -> None:
    client, _ids = cliente

    respuesta = client.post(
        "/solicitudes/asistido",
        json=_cuerpo(requester_institutional_id=f"  {ACTIVE_ID}  "),
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["requester_institutional_id"] == ACTIVE_ID
    assert respuesta.json()["status"] == "registered"


# --- Esquema y regla de dominio (sin base de datos) ------------------------------------


def test_el_esquema_asistido_acepta_telefono_y_presencial() -> None:
    for canal in (RequestChannel.PHONE, RequestChannel.IN_PERSON):
        datos = RequestAssistedCreate(
            requester_institutional_id=ACTIVE_ID,
            title="Solicitud",
            description="Descripción",
            physical_location="Edificio A",
            channel=canal,
        )
        assert datos.channel == canal


def test_el_esquema_asistido_rechaza_el_canal_portal() -> None:
    with pytest.raises(ValueError):
        RequestAssistedCreate(
            requester_institutional_id=ACTIVE_ID,
            title="Solicitud",
            description="Descripción",
            physical_location="Edificio A",
            channel=RequestChannel.PORTAL,
        )


@pytest.mark.parametrize(
    ("localizado", "esperado"),
    [(True, RequestStatus.REGISTERED), (False, RequestStatus.PENDING_VERIFICATION)],
)
def test_el_estado_inicial_depende_de_si_el_solicitante_fue_localizado(
    localizado, esperado
) -> None:
    assert estado_inicial(localizado) == esperado
