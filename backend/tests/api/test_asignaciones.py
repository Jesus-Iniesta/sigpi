"""Pruebas de la asignación de técnicos (S5-03: HU-03.1, HU-03.3, HU-07.1).

- La propuesta pone primero a los técnicos con especialidad de la categoría y menor carga,
  con el desglose del puntaje.
- Asignar deja la solicitud «Asignada», cierra la asignación anterior, escribe bitácora y
  avisa `request_assigned` al solicitante y al técnico; todo queda confirmado.
- Una solicitud que queda en P1 se asigna sola al mejor candidato.
- Una P1 sin candidatos avisa `p1_unassigned` a los jefes y no cambia de estado.
- `GET /asignaciones/{id}` (S5-12) devuelve el técnico asignado con el desglose de su
  puntaje; `null` si no tiene técnico; sin puntaje guardado, sin componentes.
- Técnico inactivo o solicitud cerrada: 422; técnico inexistente: 404; sin sesión: 401;
  sin permiso: 403.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.api.routers.solicitudes import get_clasificacion_service
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.models.enums import (
    ClassificationSource,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
)
from app.models.identity import Role, User, UserRole
from app.models.notification import Notification
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestAssignment, RequestLog
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services.asignacion_service import AsignacionService
from app.services.clasificacion_service import ClasificacionService
from app.services.notificacion_service import NotificacionService

RESOLUCION_MINUTOS = {Priority.P1: 120, Priority.P2: 240, Priority.P3: 480, Priority.P4: 960}
TECNICOS = ("ana", "beto", "carla", "inactivo")


class ClasificadorFalso:
    """Predice «Redes» con urgencia e impacto altos: la solicitud queda en P1."""

    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)
    version = "falso-v1"

    def predecir(self, texto: str):
        from app.integrations.clasificador_client import Prediccion

        return Prediccion(
            categoria="Redes",
            urgencia=3,
            impacto=3,
            confianza=0.95,
            fuente=self.fuente,
            version=self.version,
        )


def _correr(maker, escenario):
    async def correr():
        async with maker() as session:
            return await escenario(session)

    return asyncio.run(correr())


@pytest.fixture
def entorno():
    """Catálogo con «Redes» y «Software», técnicos, solicitante, jefe y acuerdos de SLA.

    * ana: especialidad de Redes, activa.  * beto: sin especialidad, activo.
    * carla: especialidad de Software, activa.  * inactivo: especialidad de Redes, inactivo.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    claves = (*TECNICOS, "solicitante", "jefe", "agente")
    ids = {clave: uuid.uuid4() for clave in claves}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            unidad = OrganizationalUnit(name="Facultad de prueba", unit_type="facultad")
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
            ofimatica = Especialidad(category_id=ids["Software"], name="Ofimática")
            turno = Turno(name="Matutino", start_minute=7 * 60, end_minute=15 * 60)
            session.add_all([conectividad, ofimatica, turno])
            await session.flush()
            ids["turno"] = turno.id
            especialidades = {
                "ana": [conectividad],
                "beto": [],
                "carla": [ofimatica],
                "inactivo": [conectividad],
            }
            for clave in claves:
                tecnico = clave in TECNICOS
                session.add(
                    User(
                        id=ids[clave],
                        institutional_id=f"u-{clave}",
                        full_name=clave.title(),
                        email=f"{clave}@example.test",
                        user_type=UserType.TECHNICAL if tecnico else UserType.ADMINISTRATIVE,
                        is_active=clave != "inactivo",
                        specialties=especialidades.get(clave, []),
                    )
                )
            jefes = Role(name=RoleName.SERVICE_MANAGER)
            session.add(jefes)
            await session.flush()
            session.add(UserRole(user_id=ids["jefe"], role_id=jefes.id))
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
def cliente(entorno):
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    def como(rol: str | None, persona: str = "agente") -> TestClient:
        if rol is None:
            fastapi_app.dependency_overrides.pop(get_current_user, None)
        else:
            fastapi_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
                id=ids[persona],
                is_active=True,
                roles=[SimpleNamespace(role=SimpleNamespace(name=rol))],
            )
        return client

    def clasificacion(session: AsyncSession = Depends(get_session)) -> ClasificacionService:
        return ClasificacionService(session, clasificador=ClasificadorFalso())

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_clasificacion_service] = clasificacion
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    try:
        yield SimpleNamespace(como=como, maker=maker, ids=ids)
    finally:
        fastapi_app.dependency_overrides.clear()


def _crear(
    cliente,
    *,
    categoria: str | None = "Redes",
    status: RequestStatus = RequestStatus.CLASSIFIED,
    priority: Priority = Priority.P2,
    tecnico: str | None = None,
) -> uuid.UUID:
    """Solicitud directa en la base; con `tecnico`, queda con esa asignación vigente."""

    async def crear(session):
        request = Request(
            requester_id=cliente.ids["solicitante"],
            category_id=cliente.ids[categoria] if categoria else None,
            folio=f"SIG-{uuid.uuid4().hex[:6]}",
            title="Sin red en el laboratorio",
            description="Sin red",
            physical_location="Edificio B",
            channel=RequestChannel.PORTAL,
            status=status,
            priority=priority,
        )
        session.add(request)
        await session.flush()
        if tecnico is not None:
            session.add(
                RequestAssignment(
                    request_id=request.id,
                    technician_id=cliente.ids[tecnico],
                    assigned_at=datetime.now(UTC) - timedelta(hours=1),
                    is_automatic=False,
                )
            )
        await session.commit()
        return request.id

    return _correr(cliente.maker, crear)


def _asignaciones(cliente, request_id: uuid.UUID) -> list[RequestAssignment]:
    async def leer(session):
        result = await session.scalars(
            select(RequestAssignment)
            .where(RequestAssignment.request_id == request_id)
            .order_by(RequestAssignment.assigned_at)
        )
        return list(result)

    return _correr(cliente.maker, leer)


def _solicitud(cliente, request_id: uuid.UUID) -> Request:
    return _correr(cliente.maker, lambda s: s.get(Request, request_id))


def _avisos(cliente, request_id: uuid.UUID) -> list[Notification]:
    async def leer(session):
        result = await session.scalars(
            select(Notification).where(Notification.request_id == request_id)
        )
        return list(result)

    return _correr(cliente.maker, leer)


def _bitacora(cliente, request_id: uuid.UUID) -> list[RequestLog]:
    async def leer(session):
        result = await session.scalars(
            select(RequestLog).where(RequestLog.request_id == request_id)
        )
        return list(result)

    return _correr(cliente.maker, leer)


# --------------------------------------------------------------------- propuesta


def test_propuesta_ordena_por_especialidad_y_carga_con_desglose(cliente):
    # Ana tiene la especialidad pero ya atiende dos solicitudes; Beto, sin especialidad,
    # no atiende ninguna. Una tercera técnica de Redes sin carga debe quedar primero.
    async def nueva_tecnica(session):
        conectividad = (await session.scalars(select(Especialidad))).first()
        session.add(
            User(
                id=cliente.ids.setdefault("dora", uuid.uuid4()),
                institutional_id="u-dora",
                full_name="Dora",
                email="dora@example.test",
                user_type=UserType.TECHNICAL,
                is_active=True,
                specialties=[conectividad],
            )
        )
        await session.commit()

    _correr(cliente.maker, nueva_tecnica)
    _crear(cliente, tecnico="ana", status=RequestStatus.ASSIGNED)
    _crear(cliente, tecnico="ana", status=RequestStatus.IN_PROGRESS)
    _crear(cliente, tecnico="beto", status=RequestStatus.CLOSED)  # cerrada: no es carga
    request_id = _crear(cliente)

    respuesta = cliente.como("support_agent").get(f"/asignaciones/{request_id}/propuesta")

    assert respuesta.status_code == 200, respuesta.text
    candidatos = respuesta.json()
    nombres = [c["full_name"] for c in candidatos]
    assert nombres[:2] == ["Dora", "Ana"]
    assert set(nombres[2:]) == {"Beto", "Carla"}
    assert "Inactivo" not in nombres
    dora, ana = candidatos[0], candidatos[1]
    assert dora["score"] > ana["score"] > candidatos[2]["score"]
    assert ana["active_load"] == 2
    assert [c["concepto"] for c in ana["components"]] == ["Especialidad", "Turno", "Carga"]
    assert ana["components"][0]["puntos"] == 100
    assert "Especialidad +100" in ana["score_breakdown"]
    assert "2 solicitudes activas" in ana["score_breakdown"]


def test_propuesta_de_solicitud_inexistente_responde_404(cliente):
    respuesta = cliente.como("support_agent").get(f"/asignaciones/{uuid.uuid4()}/propuesta")

    assert respuesta.status_code == 404


def test_turno_vigente_suma_puntos(entorno):
    maker, ids = entorno

    async def escenario(session):
        await session.execute(
            update(User).where(User.id == ids["beto"]).values(shift_id=ids["turno"])
        )
        request = Request(
            requester_id=ids["solicitante"],
            folio="SIG-TURNO",
            title="t",
            description="d",
            physical_location="p",
            channel=RequestChannel.PORTAL,
            status=RequestStatus.CLASSIFIED,
        )
        session.add(request)
        await session.commit()
        servicio = AsignacionService(session)
        # 18:00 UTC = 12:00 en el centro de México: dentro del turno matutino.
        en_turno = await servicio.proponer(request.id, datetime(2026, 11, 2, 18, tzinfo=UTC))
        # 03:00 UTC = 21:00 del día anterior: fuera de turno.
        fuera = await servicio.proponer(request.id, datetime(2026, 11, 2, 3, tzinfo=UTC))
        return en_turno, fuera

    en_turno, fuera = _correr(maker, escenario)
    beto_en = next(p for p in en_turno if p.technician_id == ids["beto"])
    beto_fuera = next(p for p in fuera if p.technician_id == ids["beto"])
    assert beto_en.score - beto_fuera.score == 20
    assert "Matutino: en turno" in beto_en.score_breakdown


# ---------------------------------------------------------------------- asignar


def test_asignar_cierra_la_anterior_escribe_bitacora_y_avisa(cliente):
    request_id = _crear(cliente, tecnico="beto", status=RequestStatus.CLASSIFIED)

    respuesta = cliente.como("support_agent").post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["ana"])}
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["request_status"] == RequestStatus.ASSIGNED
    assert cuerpo["is_automatic"] is False
    assert cuerpo["score"] is not None and cuerpo["score_breakdown"]
    # Se lee con otra sesión: el servicio confirmó la transacción.
    assert _solicitud(cliente, request_id).status == RequestStatus.ASSIGNED
    anterior, vigente = _asignaciones(cliente, request_id)
    assert anterior.technician_id == cliente.ids["beto"]
    assert anterior.unassigned_at is not None
    assert vigente.technician_id == cliente.ids["ana"]
    assert vigente.unassigned_at is None
    assert vigente.is_automatic is False
    entradas = [e for e in _bitacora(cliente, request_id) if e.action == "Técnico asignado"]
    assert len(entradas) == 1
    assert entradas[0].author_id == cliente.ids["agente"]
    assert entradas[0].previous_status == RequestStatus.CLASSIFIED
    assert entradas[0].new_status == RequestStatus.ASSIGNED
    avisos = _avisos(cliente, request_id)
    assert {a.recipient_id for a in avisos} == {cliente.ids["solicitante"], cliente.ids["ana"]}
    assert all(a.subject.endswith("asignada") for a in avisos)
    assert all("Técnico: Ana" in a.body for a in avisos)


def test_reasignar_en_proceso_conserva_el_estado(cliente):
    request_id = _crear(cliente, tecnico="beto", status=RequestStatus.IN_PROGRESS)

    respuesta = cliente.como("service_manager", "jefe").post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["carla"])}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["request_status"] == RequestStatus.IN_PROGRESS
    vigentes = [a for a in _asignaciones(cliente, request_id) if a.unassigned_at is None]
    assert [a.technician_id for a in vigentes] == [cliente.ids["carla"]]


def test_asignar_tecnico_inactivo_responde_422(cliente):
    request_id = _crear(cliente)

    respuesta = cliente.como("support_agent").post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["inactivo"])}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "technician_unavailable"
    assert _asignaciones(cliente, request_id) == []


def test_asignar_a_quien_no_es_tecnico_responde_422(cliente):
    request_id = _crear(cliente)

    respuesta = cliente.como("support_agent").post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["solicitante"])}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "technician_unavailable"


def test_asignar_tecnico_inexistente_responde_404(cliente):
    request_id = _crear(cliente)

    respuesta = cliente.como("support_agent").post(
        f"/asignaciones/{request_id}", json={"technician_id": str(uuid.uuid4())}
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["code"] == "technician_not_found"


@pytest.mark.parametrize("estado", [RequestStatus.CLOSED, RequestStatus.RESOLVED])
def test_asignar_solicitud_cerrada_o_resuelta_responde_422(cliente, estado):
    request_id = _crear(cliente, status=estado)

    respuesta = cliente.como("support_agent").post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["ana"])}
    )

    assert respuesta.status_code == 422
    assert _asignaciones(cliente, request_id) == []
    assert _solicitud(cliente, request_id).status == estado


def test_asignar_solicitud_inexistente_responde_404(cliente):
    respuesta = cliente.como("support_agent").post(
        f"/asignaciones/{uuid.uuid4()}", json={"technician_id": str(cliente.ids["ana"])}
    )

    assert respuesta.status_code == 404


def test_sin_sesion_responde_401(cliente):
    request_id = _crear(cliente)
    anonimo = cliente.como(None)

    assert anonimo.get(f"/asignaciones/{request_id}/propuesta").status_code == 401
    respuesta = anonimo.post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["ana"])}
    )
    assert respuesta.status_code == 401


def test_sin_permiso_responde_403(cliente):
    request_id = _crear(cliente)
    solicitante = cliente.como("requester", "solicitante")

    assert solicitante.get(f"/asignaciones/{request_id}/propuesta").status_code == 403
    respuesta = solicitante.post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["ana"])}
    )
    assert respuesta.status_code == 403


# ------------------------------------------------------- asignación vigente (S5-12)


def test_la_asignacion_vigente_trae_el_tecnico_y_el_desglose_de_su_puntaje(cliente):
    request_id = _crear(cliente, tecnico="beto", status=RequestStatus.CLASSIFIED)
    agente = cliente.como("support_agent")
    agente.post(f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["ana"])})

    respuesta = agente.get(f"/asignaciones/{request_id}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["technician_id"] == str(cliente.ids["ana"])
    assert cuerpo["full_name"] == "Ana"
    assert cuerpo["is_automatic"] is False
    assert [c["concepto"] for c in cuerpo["components"]] == ["Especialidad", "Turno", "Carga"]
    assert cuerpo["components"][0]["puntos"] == 100
    assert cuerpo["score"] == sum(c["puntos"] for c in cuerpo["components"])
    assert cuerpo["score_breakdown"].startswith("Especialidad +100")


def test_la_asignacion_vigente_es_la_ultima_tras_reasignar(cliente):
    request_id = _crear(cliente, tecnico="beto", status=RequestStatus.IN_PROGRESS)
    agente = cliente.como("support_agent")
    agente.post(f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["carla"])})

    cuerpo = agente.get(f"/asignaciones/{request_id}").json()

    assert cuerpo["full_name"] == "Carla"


def test_la_asignacion_sin_puntaje_guardado_no_trae_componentes(cliente):
    request_id = _crear(cliente, tecnico="beto")

    respuesta = cliente.como("support_agent").get(f"/asignaciones/{request_id}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["full_name"] == "Beto"
    assert cuerpo["score"] is None
    assert cuerpo["score_breakdown"] is None
    assert cuerpo["components"] == []


def test_una_solicitud_sin_tecnico_responde_null(cliente):
    request_id = _crear(cliente)

    respuesta = cliente.como("support_agent").get(f"/asignaciones/{request_id}")

    assert respuesta.status_code == 200
    assert respuesta.json() is None


def test_consultar_la_asignacion_de_una_solicitud_inexistente_responde_404(cliente):
    respuesta = cliente.como("support_agent").get(f"/asignaciones/{uuid.uuid4()}")

    assert respuesta.status_code == 404


def test_consultar_la_asignacion_exige_sesion_y_permiso(cliente):
    request_id = _crear(cliente, tecnico="beto")

    assert cliente.como(None).get(f"/asignaciones/{request_id}").status_code == 401
    solicitante = cliente.como("requester", "solicitante")
    assert solicitante.get(f"/asignaciones/{request_id}").status_code == 403


def test_si_el_aviso_falla_no_se_guarda_la_asignacion(entorno, monkeypatch):
    maker, ids = entorno

    async def falla(*_args, **_kwargs):
        raise RuntimeError("no se pudo escribir el aviso")

    monkeypatch.setattr(NotificacionService, "emitir", falla)

    async def crear(session):
        request = Request(
            requester_id=ids["solicitante"],
            folio="SIG-FALLA",
            title="t",
            description="d",
            physical_location="p",
            channel=RequestChannel.PORTAL,
            status=RequestStatus.CLASSIFIED,
        )
        session.add(request)
        await session.commit()
        request_id = request.id
        with pytest.raises(RuntimeError):
            await AsignacionService(session).asignar(request_id, ids["ana"], ids["agente"])
        return request_id

    request_id = _correr(maker, crear)
    assert _correr(maker, lambda s: s.get(Request, request_id)).status == RequestStatus.CLASSIFIED

    async def contar(session):
        return list(await session.scalars(select(RequestAssignment)))

    assert _correr(maker, contar) == []


# ------------------------------------------------------------- asignación automática


def _alta(cliente) -> dict:
    respuesta = cliente.como("requester", "solicitante").post(
        "/solicitudes",
        json={
            "requester_id": str(cliente.ids["solicitante"]),
            "title": "No hay internet",
            "description": "El wifi del edificio no tiene conexion",
            "physical_location": "Edificio A",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_solicitud_p1_se_asigna_automaticamente_al_mejor_candidato(cliente):
    alta = _alta(cliente)

    request_id = uuid.UUID(alta["id"])
    assert alta["priority"] == Priority.P1
    assert alta["status"] == RequestStatus.ASSIGNED
    (asignacion,) = _asignaciones(cliente, request_id)
    assert asignacion.technician_id == cliente.ids["ana"]
    assert asignacion.is_automatic is True
    assert asignacion.score_breakdown and "Especialidad +100" in asignacion.score_breakdown
    assert any(e.action == "Asignación automática" for e in _bitacora(cliente, request_id))
    asignados = [a for a in _avisos(cliente, request_id) if a.subject.endswith("asignada")]
    assert {a.recipient_id for a in asignados} == {
        cliente.ids["solicitante"],
        cliente.ids["ana"],
    }


def test_solicitud_p1_sin_candidatos_avisa_a_los_jefes(cliente):
    async def desactivar(session):
        await session.execute(
            update(User).where(User.user_type == UserType.TECHNICAL).values(is_active=False)
        )
        await session.commit()

    _correr(cliente.maker, desactivar)

    alta = _alta(cliente)

    request_id = uuid.UUID(alta["id"])
    assert alta["priority"] == Priority.P1
    assert alta["status"] == RequestStatus.CLASSIFIED
    assert _asignaciones(cliente, request_id) == []
    criticos = [a for a in _avisos(cliente, request_id) if "sin asignar" in a.subject]
    assert [a.recipient_id for a in criticos] == [cliente.ids["jefe"]]


def test_asignacion_automatica_sin_candidatos_no_p1_no_avisa(entorno):
    maker, ids = entorno

    async def escenario(session):
        await session.execute(
            update(User).where(User.user_type == UserType.TECHNICAL).values(is_active=False)
        )
        request = Request(
            requester_id=ids["solicitante"],
            folio="SIG-P3",
            title="t",
            description="d",
            physical_location="p",
            channel=RequestChannel.PORTAL,
            status=RequestStatus.CLASSIFIED,
            priority=Priority.P3,
        )
        session.add(request)
        await session.commit()
        resultado = await AsignacionService(session).asignar_automaticamente(request.id)
        avisos = list(await session.scalars(select(Notification)))
        return resultado, avisos

    resultado, avisos = _correr(maker, escenario)
    assert resultado is None
    assert avisos == []


def test_fallo_de_la_asignacion_automatica_no_tumba_el_alta(cliente, monkeypatch):
    async def falla(*_args, **_kwargs):
        raise RuntimeError("motor caído")

    monkeypatch.setattr(AsignacionService, "asignar_automaticamente", falla)

    alta = _alta(cliente)

    assert alta["priority"] == Priority.P1
    assert alta["status"] == RequestStatus.CLASSIFIED
