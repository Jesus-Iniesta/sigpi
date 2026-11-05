"""Pruebas del contrato simulado del acuerdo de servicio en PDF (COR-06A, HU-08.1).

Cubren `GET /sla/agreements/{agreement_id}/contrato.pdf`:

- El PDF inicia con `%PDF` y su texto (extraído con `pypdf`) incluye el nombre del
  acuerdo, las cuatro prioridades y el folio.
- `requester` y `administrator` lo descargan; `support_agent` recibe 403 y sin sesión, 401.
- Acuerdo inexistente: 404. Acuerdo sin versión vigente: 422 `sla_without_current_version`.

`pypdf` es solo dependencia de pruebas (`requirements-dev.txt`). Se importa a nivel de
módulo a propósito: si falta, el módulo no se puede recolectar y la ejecución falla
en lugar de omitir las pruebas.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import pypdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.permissions import Permission, RoleName, has_permission
from app.db.base import Base
from app.db.session import get_session
from app.domain.sla_options import (
    AGREEMENT_DEFAULT_NAME,
    SERVICE_DESCRIPTIONS,
    SERVICE_TYPE_NAMES,
)
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria
from app.models.organization import OrganizationalUnit
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services.contrato_sla_service import duracion_legible, folio_contrato, slugify

NOMBRE = "Conectividad y redes"
USUARIO_NOMBRE = "Ana Solicitante"
USUARIO_CORREO = "ana@alumno.uaemex.mx"
TIEMPOS = {"P1": (30, 240), "P2": (60, 480), "P3": (120, 1440), "P4": (240, 2880)}


def _como(role: str) -> SimpleNamespace:
    """Usuario autenticado con un solo rol (lo que consulta `require_permission`)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        full_name=USUARIO_NOMBRE,
        email=USUARIO_CORREO,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """SQLite en memoria con un acuerdo por categoría, uno predeterminado y uno sin versión."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"categoria": uuid.uuid4(), "predeterminado": uuid.uuid4(), "sin_version": uuid.uuid4()}
    ayer = datetime.now(UTC) - timedelta(days=1)
    hace_un_mes = ayer - timedelta(days=30)

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            unit = OrganizationalUnit(name="DTIC", unit_type="department")
            session.add(unit)
            await session.flush()
            area = AreaServicio(unit_id=unit.id, name="Redes")
            session.add(area)
            await session.flush()
            categoria = Categoria(area_id=area.id, name="Conectividad")
            session.add(categoria)
            await session.flush()
            session.add_all(
                [
                    ServiceLevelAgreement(
                        id=ids["categoria"], name=NOMBRE, category_id=categoria.id
                    ),
                    ServiceLevelAgreement(
                        id=ids["predeterminado"], name=AGREEMENT_DEFAULT_NAME, is_default=True
                    ),
                    ServiceLevelAgreement(
                        id=ids["sin_version"],
                        name=SERVICE_TYPE_NAMES[0],
                        category_id=categoria.id,
                        is_active=False,
                    ),
                ]
            )
            await session.flush()
            # v1 cerrada y v2 vigente en el acuerdo por categoría.
            for priority, (primera, resolucion) in TIEMPOS.items():
                session.add_all(
                    [
                        ServiceLevelVersion(
                            agreement_id=ids["categoria"],
                            version=1,
                            priority=priority,
                            first_response_minutes=primera * 2,
                            resolution_minutes=resolucion * 2,
                            valid_from=hace_un_mes,
                            valid_to=ayer,
                        ),
                        ServiceLevelVersion(
                            agreement_id=ids["categoria"],
                            version=2,
                            priority=priority,
                            first_response_minutes=primera,
                            resolution_minutes=resolucion,
                            valid_from=ayer,
                        ),
                        ServiceLevelVersion(
                            agreement_id=ids["predeterminado"],
                            version=1,
                            priority=priority,
                            first_response_minutes=primera,
                            resolution_minutes=resolucion,
                            valid_from=ayer,
                        ),
                    ]
                )
            await session.commit()

    asyncio.run(preparar())

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    try:
        yield TestClient(fastapi_app), ids
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _autenticar_como(role: str) -> None:
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(role)


def _url(agreement_id: uuid.UUID | str) -> str:
    return f"/sla/agreements/{agreement_id}/contrato.pdf"


def _texto_pdf(contenido: bytes) -> str:
    lector = pypdf.PdfReader(BytesIO(contenido))
    texto = " ".join(pagina.extract_text() for pagina in lector.pages)
    # Se normalizan los espacios: el ajuste de línea del PDF no debe afectar las pruebas.
    return " ".join(texto.split())


# --- contenido del PDF --------------------------------------------------------
def test_requester_descarga_pdf_con_nombre_prioridades_y_folio(entorno) -> None:
    client, ids = entorno
    _autenticar_como(RoleName.REQUESTER.value)

    response = client.get(_url(ids["categoria"]))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="contrato-conectividad-y-redes-v2.pdf"'
    )
    assert response.content.startswith(b"%PDF")

    texto = _texto_pdf(response.content)
    assert NOMBRE in texto
    for priority in ("P1", "P2", "P3", "P4"):
        assert priority in texto
    assert folio_contrato(ids["categoria"], 2) in texto
    assert "Conectividad" in texto
    assert "DTIC-FI" in texto
    assert USUARIO_NOMBRE in texto and USUARIO_CORREO in texto
    assert SERVICE_DESCRIPTIONS[NOMBRE][:40] in texto
    assert "Documento sin validez oficial" in texto
    # Tiempos de la versión vigente (v2), no de la cerrada (v1).
    assert "30 min" in texto and "4 h" in texto and "48 h" in texto


def test_predeterminado_aplica_a_todas_las_categorias(entorno) -> None:
    client, ids = entorno
    _autenticar_como(RoleName.ADMINISTRATOR.value)

    response = client.get(_url(ids["predeterminado"]))

    assert response.status_code == 200
    texto = _texto_pdf(response.content)
    assert AGREEMENT_DEFAULT_NAME in texto
    assert "Aplica a todas las categorías" in texto
    assert folio_contrato(ids["predeterminado"], 1) in texto


# --- permisos -----------------------------------------------------------------
@pytest.mark.parametrize("role", [RoleName.REQUESTER.value, RoleName.ADMINISTRATOR.value])
def test_roles_permitidos_reciben_200(entorno, role: str) -> None:
    client, ids = entorno
    _autenticar_como(role)

    response = client.get(_url(ids["categoria"]))

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_support_agent_recibe_403(entorno) -> None:
    client, ids = entorno
    _autenticar_como(RoleName.SUPPORT_AGENT.value)

    response = client.get(_url(ids["categoria"]))

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_sin_sesion_recibe_401(entorno) -> None:
    client, ids = entorno  # sin override de get_current_user

    response = client.get(_url(ids["categoria"]))

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_permiso_de_descarga_solo_para_requester_y_administrator() -> None:
    permitidos = {RoleName.REQUESTER, RoleName.ADMINISTRATOR}
    for role in RoleName:
        assert has_permission(role, Permission.SLA_CONTRACT_DOWNLOAD) == (role in permitidos)


# --- errores ------------------------------------------------------------------
def test_acuerdo_inexistente_responde_404(entorno) -> None:
    client, _ = entorno
    _autenticar_como(RoleName.REQUESTER.value)

    response = client.get(_url(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_acuerdo_sin_version_vigente_responde_422(entorno) -> None:
    client, ids = entorno
    _autenticar_como(RoleName.REQUESTER.value)

    response = client.get(_url(ids["sin_version"]))

    assert response.status_code == 422
    assert response.json()["code"] == "sla_without_current_version"


# --- utilidades de formato ----------------------------------------------------
@pytest.mark.parametrize(
    ("minutos", "esperado"),
    [(45, "45 min"), (60, "1 h"), (90, "1 h 30 min"), (2880, "48 h"), (None, "No definido")],
)
def test_duracion_legible(minutos, esperado) -> None:
    assert duracion_legible(minutos) == esperado


def test_slug_y_folio() -> None:
    agreement_id = uuid.UUID("0123abcd-0000-0000-0000-000000000000")
    assert slugify("Soporte a equipo de cómputo y periféricos") == (
        "soporte-a-equipo-de-computo-y-perifericos"
    )
    assert folio_contrato(agreement_id, 3) == "SLA-0123ABCD-v3"


def test_cada_tipo_de_servicio_tiene_descripcion() -> None:
    for nombre in (AGREEMENT_DEFAULT_NAME, *SERVICE_TYPE_NAMES):
        assert SERVICE_DESCRIPTIONS[nombre]
