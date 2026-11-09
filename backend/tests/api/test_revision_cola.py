"""Pruebas del umbral de confianza y la cola de revisión (S4-14, HU-02.2 AC1).

- Con confianza 0.74 la decisión es «Por revisar»; con 0.75, «Clasificada» (RN-06).
- `GET /revision/cola` devuelve solo solicitudes «Por revisar», de la más antigua a la
  más reciente, con la forma de `RevisionItem` del frontend.
- Un `requester` recibe 403.
"""

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.permissions import Permission, RoleName, has_permission
from app.db.base import Base
from app.db.session import get_session
from app.domain.clasificacion import requiere_revision
from app.main import app as fastapi_app
from app.models.catalog import Categoria
from app.models.classification import ClassificationResult, ModelVersion
from app.models.enums import (
    ClassificationSource,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
)
from app.models.identity import User
from app.models.request import Request
from app.schemas.revision import RevisionItem
from app.services.revision_service import decidir_estatus

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
REVISION_TS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "revision.ts"


# ------------------------------------------------------------------ regla y decisión


def test_requiere_revision_es_estrictamente_menor_que_el_umbral() -> None:
    assert requiere_revision(0.74, 0.75)
    assert not requiere_revision(0.75, 0.75)
    assert not requiere_revision(0.9, 0.75)


def test_decidir_estatus_con_el_umbral_de_la_configuracion() -> None:
    assert settings.classification_confidence_threshold == 0.75
    assert decidir_estatus(SimpleNamespace(confidence=0.74)) == RequestStatus.PENDING_REVIEW
    assert decidir_estatus(SimpleNamespace(confidence=0.75)) == RequestStatus.CLASSIFIED


def test_decidir_estatus_acepta_la_confianza_como_decimal() -> None:
    from decimal import Decimal

    assert decidir_estatus(SimpleNamespace(confidence=Decimal("0.7499"))) == (
        RequestStatus.PENDING_REVIEW
    )
    assert decidir_estatus(SimpleNamespace(confidence=Decimal("0.7500"))) == (
        RequestStatus.CLASSIFIED
    )


def test_decidir_estatus_sigue_al_umbral_configurado(monkeypatch) -> None:
    monkeypatch.setattr(settings, "classification_confidence_threshold", 0.9)
    assert decidir_estatus(SimpleNamespace(confidence=0.8)) == RequestStatus.PENDING_REVIEW


@pytest.mark.parametrize(
    ("role", "permitido"),
    [
        (RoleName.CLASSIFIER, True),
        (RoleName.SUPPORT_AGENT, True),
        (RoleName.ADMINISTRATOR, True),
        (RoleName.REQUESTER, False),
    ],
)
def test_permiso_de_revision_por_rol(role: RoleName, permitido: bool) -> None:
    assert has_permission(role, Permission.CLASSIFICATION_REVIEW) is permitido


# ---------------------------------------------------------- contrato con el frontend


def _campos_revision_item_frontend() -> set[str]:
    texto = REVISION_TS.read_text(encoding="utf-8")
    bloque = re.search(r"export type RevisionItem = \{(.*?)\n\}", texto, re.DOTALL)
    assert bloque is not None, "No se encontró `RevisionItem` en revision.ts"
    return set(re.findall(r"^\s*(\w+)\??:", bloque.group(1), re.MULTILINE))


def test_revision_item_coincide_campo_por_campo_con_el_frontend() -> None:
    campos_frontend = _campos_revision_item_frontend()
    assert campos_frontend  # el análisis encontró campos
    assert set(RevisionItem.model_fields) == campos_frontend


# --------------------------------------------------------------------------- API


def _en_sesion(role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """Solicitudes en varios estatus con resultados de clasificación."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {
        k: uuid.uuid4()
        for k in ("solicitante", "area", "categoria", "modelo", "antigua", "reciente", "lista")
    }

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add(
                User(
                    id=ids["solicitante"],
                    institutional_id="u-0001",
                    full_name="Sara Solicitante",
                    email="sara@example.test",
                    user_type=UserType.ACADEMIC,
                )
            )
            session.add(Categoria(id=ids["categoria"], area_id=ids["area"], name="Redes"))
            session.add(
                ModelVersion(id=ids["modelo"], version="v1.0", trained_at=INICIO, is_active=True)
            )
            await session.flush()

            def solicitud(key: str, folio: str, status: RequestStatus, minutos: int) -> Request:
                return Request(
                    id=ids[key],
                    requester_id=ids["solicitante"],
                    folio=folio,
                    title=f"Título {folio}",
                    description=f"Descripción {folio}",
                    physical_location="Edificio B",
                    channel=RequestChannel.PORTAL,
                    status=status,
                    priority=Priority.P3,
                    created_at=INICIO + timedelta(minutes=minutos),
                )

            # Se insertan en desorden para comprobar que la cola ordena por antigüedad.
            session.add(solicitud("reciente", "SIG-0003", RequestStatus.PENDING_REVIEW, 30))
            session.add(solicitud("lista", "SIG-0002", RequestStatus.CLASSIFIED, 20))
            session.add(solicitud("antigua", "SIG-0001", RequestStatus.PENDING_REVIEW, 10))
            await session.flush()

            session.add_all(
                [
                    # La antigua tiene dos resultados: la cola usa el último.
                    ClassificationResult(
                        request_id=ids["antigua"],
                        source=ClassificationSource.RULES,
                        confidence=0.4,
                        urgency=1,
                        impact=1,
                        created_at=INICIO + timedelta(minutes=11),
                    ),
                    ClassificationResult(
                        request_id=ids["antigua"],
                        model_version_id=ids["modelo"],
                        category_id=ids["categoria"],
                        source=ClassificationSource.MODEL,
                        confidence=0.62,
                        urgency=2,
                        impact=1,
                        created_at=INICIO + timedelta(minutes=12),
                    ),
                    ClassificationResult(
                        request_id=ids["reciente"],
                        source=ClassificationSource.RULES,
                        confidence=0.5,
                        urgency=3,
                        impact=2,
                        created_at=INICIO + timedelta(minutes=31),
                    ),
                    ClassificationResult(
                        request_id=ids["lista"],
                        source=ClassificationSource.MODEL,
                        confidence=0.95,
                        urgency=1,
                        impact=2,
                        created_at=INICIO + timedelta(minutes=21),
                    ),
                ]
            )
            await session.commit()

    asyncio.run(preparar())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    client = TestClient(fastapi_app)

    def como(role: str) -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(role)
        return client

    try:
        yield como, ids
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_cola_devuelve_solo_por_revisar_de_la_mas_antigua_a_la_mas_reciente(entorno) -> None:
    como, ids = entorno
    response = como(RoleName.CLASSIFIER.value).get("/revision/cola")

    assert response.status_code == 200
    cola = response.json()
    assert [item["folio"] for item in cola] == ["SIG-0001", "SIG-0003"]
    assert [item["request_id"] for item in cola] == [str(ids["antigua"]), str(ids["reciente"])]


def test_cola_tiene_la_forma_de_revision_item_y_usa_el_ultimo_resultado(entorno) -> None:
    como, ids = entorno
    cola = como(RoleName.SUPPORT_AGENT.value).get("/revision/cola").json()

    assert all(set(item) == _campos_revision_item_frontend() for item in cola)
    primero = cola[0]
    assert primero["category_id"] == str(ids["categoria"])
    assert primero["category_name"] == "Redes"
    assert primero["confidence"] == pytest.approx(0.62)
    assert primero["source"] == "model"
    assert primero["model_version"] == "v1.0"
    assert (primero["urgency"], primero["impact"]) == (2, 1)
    assert primero["priority"] == "P3"
    assert primero["title"] == "Título SIG-0001"
    assert primero["description"] == "Descripción SIG-0001"

    segundo = cola[1]
    assert segundo["category_id"] is None
    assert segundo["category_name"] is None
    assert segundo["model_version"] is None
    assert segundo["source"] == "rules"


def test_administrador_consulta_la_cola(entorno) -> None:
    como, _ = entorno
    assert como(RoleName.ADMINISTRATOR.value).get("/revision/cola").status_code == 200


def test_solicitante_recibe_403_en_la_cola(entorno) -> None:
    como, _ = entorno
    response = como(RoleName.REQUESTER.value).get("/revision/cola")

    assert response.status_code == 403


def test_cola_sin_sesion_responde_401(entorno) -> None:
    como, _ = entorno
    client = como(RoleName.CLASSIFIER.value)
    fastapi_app.dependency_overrides.pop(get_current_user, None)

    assert client.get("/revision/cola").status_code == 401
