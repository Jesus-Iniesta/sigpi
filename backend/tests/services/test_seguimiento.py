"""Pruebas de resolución y confirmación de solicitudes (S3-14, HU-04.1).

Cubren los dos criterios de aceptación:
- AC1: resolver una solicitud (cambia a «Resuelta», calcula SLA, bitácora)
- AC2: confirmar una solicitud resuelta (cambia a «Cerrada», bitácora)
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.permissions import RoleName
from app.db.base import Base
from app.models.catalog import AreaServicio, Categoria
from app.models.enums import RequestChannel, RequestStatus, UserType
from app.models.identity import Role, User, UserRole
from app.models.organization import OrganizationalUnit
from app.models.request import Request
from app.services.seguimiento_service import SeguimientoService
from app.services.sla_clock_service import EstadoInvalidoError, SolicitudNoEncontradaError

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _create_engine_and_maker():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, maker


async def _seed_roles(session: AsyncSession) -> dict[RoleName, uuid.UUID]:
    """Crea los roles base y devuelve sus IDs."""
    role_ids: dict[RoleName, uuid.UUID] = {}
    for role_name in RoleName:
        role = Role(name=role_name, description=f"Rol {role_name.value}")
        session.add(role)
        await session.flush()
        role_ids[role_name] = role.id
    await session.commit()
    return role_ids


async def _seed_user(
    session: AsyncSession,
    role_ids: dict[RoleName, uuid.UUID],
    role_names: set[RoleName],
    institutional_id: str,
    full_name: str,
    email: str,
) -> uuid.UUID:
    """Crea un usuario con los roles indicados y devuelve su ID."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=full_name,
        email=email,
        password_hash="hash-falso",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    for role_name in role_names:
        session.add(
            UserRole(user_id=user_id, role_id=role_ids[role_name])
        )
    await session.commit()
    return user_id


async def _seed_category(session: AsyncSession) -> uuid.UUID:
    """Crea unidad → área → categoría y devuelve el ID de la categoría."""
    unit = OrganizationalUnit(name="DTIC", unit_type="department")
    session.add(unit)
    await session.flush()
    area = AreaServicio(unit_id=unit.id, name="Redes")
    session.add(area)
    await session.flush()
    category = Categoria(area_id=area.id, name="Conectividad", is_active=True)
    session.add(category)
    await session.commit()
    return category.id


async def _seed_request(
    session: AsyncSession,
    requester_id: uuid.UUID,
    category_id: uuid.UUID,
    status: RequestStatus = RequestStatus.ASSIGNED,
    folio: str = "SIG-0001",
) -> uuid.UUID:
    """Crea una solicitud en el estado indicado y devuelve su ID."""
    request = Request(
        requester_id=requester_id,
        category_id=category_id,
        folio=folio,
        title="No hay conexión a la red",
        description="El laboratorio perdió conectividad.",
        physical_location="Edificio A, laboratorio 2",
        channel=RequestChannel.PORTAL,
        status=status,
        urgency=2,
        impact=2,
        created_at=T0,
        updated_at=T0,
    )
    session.add(request)
    await session.commit()
    return request.id


@pytest_asyncio.fixture
async def session():
    engine, maker = _create_engine_and_maker()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as db_session:
        role_ids = await _seed_roles(db_session)

        # Usuario administrador (tiene REQUESTS_RESOLVE y REQUESTS_CLOSE)
        admin_id = await _seed_user(
            db_session,
            role_ids,
            {RoleName.ADMINISTRATOR},
            "uaem2026001",
            "Admin Sistema",
            "admin@uaemex.mx",
        )

        # Usuario service manager (tiene REQUESTS_RESOLVE y REQUESTS_CLOSE)
        sm_id = await _seed_user(
            db_session,
            role_ids,
            {RoleName.SERVICE_MANAGER},
            "uaem2026002",
            "Service Manager",
            "sm@uaemex.mx",
        )

        # Usuario requester (solo REQUESTS_READ, REQUESTS_CREATE, KNOWLEDGE_READ)
        requester_id = await _seed_user(
            db_session,
            role_ids,
            {RoleName.REQUESTER},
            "uaem2026003",
            "Solicitante Prueba",
            "req@uaemex.mx",
        )

        # Categoría para la solicitud
        category_id = await _seed_category(db_session)

        # Solicitud asignada (resoluble)
        request_id = await _seed_request(db_session, requester_id, category_id)

        yield {
            "session": db_session,
            "admin_id": admin_id,
            "sm_id": sm_id,
            "requester_id": requester_id,
            "request_id": request_id,
            "category_id": category_id,
            "role_ids": role_ids,
        }
    await engine.dispose()


async def _get_service(session: AsyncSession) -> SeguimientoService:
    return SeguimientoService(session)


# ============================================================================
# AC1: Resolución de solicitud
# ============================================================================


@pytest.mark.asyncio
async def test_resolver_con_permiso_cambia_estado_a_resolved(session) -> None:
    """Un usuario con REQUESTS_RESOLVE resuelve la solicitud."""
    svc = await _get_service(session["session"])
    result = await svc.resolver(
        session["request_id"], session["admin_id"], "Reemplazado el cable de red"
    )

    assert result.status == RequestStatus.RESOLVED
    assert result.resolved_at is not None
    assert result.solution == "Reemplazado el cable de red"
    assert result.resolution_minutes is not None
    assert result.resolution_minutes >= 0


@pytest.mark.asyncio
async def test_resolver_calcula_sla_al_resolver(session) -> None:
    """Al resolver, se calcula el tiempo efectivo de resolución (SLA)."""
    svc = await _get_service(session["session"])
    result = await svc.resolver(
        session["request_id"], session["admin_id"], "Solución aplicada"
    )

    assert result.resolution_minutes is not None
    assert isinstance(result.resolution_minutes, int)
    assert result.resolution_minutes >= 0


@pytest.mark.asyncio
async def test_resolver_registra_bitacora(session) -> None:
    """Al resolver, se crea una entrada en la bitácora."""
    svc = await _get_service(session["session"])
    before = await svc.listar_bitacora(session["request_id"])

    await svc.resolver(
        session["request_id"], session["admin_id"], "Solución aplicada"
    )

    after = await svc.listar_bitacora(session["request_id"])
    assert len(after) == len(before) + 1
    ultima = after[-1]
    assert ultima.new_status == RequestStatus.RESOLVED
    assert "Solución aplicada" in ultima.notes
    assert "Se solicita al solicitante confirmar" in ultima.notes


@pytest.mark.asyncio
async def test_resolver_ya_resuelto_rechaza(session) -> None:
    """Intentar resolver una solicitud ya resuelta falla."""
    svc = await _get_service(session["session"])
    await svc.resolver(session["request_id"], session["admin_id"], "Primera resolución")

    with pytest.raises(EstadoInvalidoError):
        await svc.resolver(session["request_id"], session["admin_id"], "Segunda")


@pytest.mark.asyncio
async def test_resolver_solicitud_no_resoluble_rechaza(session) -> None:
    """Una solicitud en estado REGISTERED no puede resolverse."""
    request_id = await _seed_request(
        session["session"],
        session["requester_id"],
        session["category_id"],
        RequestStatus.REGISTERED,
        "SIG-0002",
    )
    svc = await _get_service(session["session"])

    with pytest.raises(EstadoInvalidoError):
        await svc.resolver(request_id, session["admin_id"], "Solución")


@pytest.mark.asyncio
async def test_resolver_solicitud_inexistente_rechaza(session) -> None:
    """Resolver una solicitud que no existe falla."""
    svc = await _get_service(session["session"])

    with pytest.raises(SolicitudNoEncontradaError):
        await svc.resolver(uuid.uuid4(), session["admin_id"], "Solución")


# ============================================================================
# AC2: Confirmación de solicitud
# ============================================================================


@pytest.mark.asyncio
async def test_confirmar_con_rol_adecuado_cambia_estado_a_closed(session) -> None:
    """Un usuario con REQUESTS_CLOSE confirma y la solicitud se cierra."""
    svc = await _get_service(session["session"])
    await svc.resolver(session["request_id"], session["admin_id"], "Solución aplicada")

    result = await svc.confirmar(
        session["request_id"], session["sm_id"], "La solución funciona correctamente"
    )

    assert result.status == RequestStatus.CLOSED
    assert result.closed_at is not None


@pytest.mark.asyncio
async def test_confirmar_registra_bitacora(session) -> None:
    """Al confirmar, se crea una entrada en la bitácora."""
    svc = await _get_service(session["session"])
    await svc.resolver(session["request_id"], session["admin_id"], "Solución aplicada")

    before = await svc.listar_bitacora(session["request_id"])

    await svc.confirmar(session["request_id"], session["sm_id"], "Confirmado")

    after = await svc.listar_bitacora(session["request_id"])
    assert len(after) == len(before) + 1
    ultima = after[-1]
    assert ultima.new_status == RequestStatus.CLOSED
    assert ultima.action == "Solicitud confirmada"


@pytest.mark.asyncio
async def test_confirmar_solicitud_no_resuelta_rechaza(session) -> None:
    """Confirmar una solicitud que no está resuelta falla."""
    svc = await _get_service(session["session"])

    with pytest.raises(EstadoInvalidoError):
        await svc.confirmar(session["request_id"], session["sm_id"], "Confirmado")


@pytest.mark.asyncio
async def test_confirmar_ya_cerrada_rechaza(session) -> None:
    """Confirmar una solicitud ya cerrada falla."""
    svc = await _get_service(session["session"])
    await svc.resolver(session["request_id"], session["admin_id"], "Solución aplicada")
    await svc.confirmar(session["request_id"], session["sm_id"], "Confirmado")

    with pytest.raises(EstadoInvalidoError):
        await svc.confirmar(session["request_id"], session["sm_id"], "Otra vez")


@pytest.mark.asyncio
async def test_confirmar_solicitud_inexistente_rechaza(session) -> None:
    """Confirmar una solicitud que no existe falla."""
    svc = await _get_service(session["session"])

    with pytest.raises(SolicitudNoEncontradaError):
        await svc.confirmar(uuid.uuid4(), session["sm_id"], "Confirmado")


@pytest.mark.asyncio
async def test_flujo_completo_resolver_luego_confirmar(session) -> None:
    """Flujo completo: resolver y luego confirmar."""
    svc = await _get_service(session["session"])

    # Resolver
    resuelto = await svc.resolver(
        session["request_id"], session["admin_id"], "Solución aplicada"
    )
    assert resuelto.status == RequestStatus.RESOLVED
    assert resuelto.resolved_at is not None

    # Confirmar
    cerrado = await svc.confirmar(
        session["request_id"], session["sm_id"], "Está bien, gracias"
    )
    assert cerrado.status == RequestStatus.CLOSED
    assert cerrado.closed_at is not None

    # Bitácora completa
    log = await svc.listar_bitacora(session["request_id"])
    acciones = [e.action for e in log]
    assert "Solicitud resuelta" in acciones
    assert "Solicitud confirmada" in acciones


@pytest.mark.asyncio
async def test_resolver_con_notas_guardadas(session) -> None:
    """La solución y notas se guardan en la solicitud y bitácora."""
    svc = await _get_service(session["session"])
    solution = "Reinstalado el controlador de red"
    diagnosis = "Tarjeta de red con firmware desactualizado"

    result = await svc.resolver(
        session["request_id"], session["admin_id"], solution, diagnosis=diagnosis
    )

    assert result.solution == solution
    assert result.diagnosis == diagnosis

    log = await svc.listar_bitacora(session["request_id"])
    ultima = log[-1]
    assert solution in ultima.notes
