"""Pruebas unitarias de `UsuarioService.update_user` (S5-24, HU-10.1).

Usan un repositorio y una auditoría simulados para cubrir los tres caminos:
usuario inexistente, rol sin configurar y cambios parciales.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core.permissions import RoleName
from app.domain.auditoria import AuditContext
from app.services.usuario_service import RoleNotConfiguredError, UsuarioService


class RepositorioSimulado:
    """Imita `UsuarioRepository` en memoria y anota lo que se le pide."""

    def __init__(self, usuario: SimpleNamespace, roles: dict[RoleName, SimpleNamespace]) -> None:
        self.usuario = usuario
        self.roles = roles
        self.campos_actualizados: list[dict] = []
        self.roles_reemplazados: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.commits = 0

    async def get_by_id(self, user_id: uuid.UUID):
        return self.usuario if user_id == self.usuario.id else None

    async def get_role_by_name(self, name: RoleName):
        return self.roles.get(name)

    async def replace_roles(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        self.roles_reemplazados.append((user_id, role_id))
        rol = next(r for r in self.roles.values() if r.id == role_id)
        self.usuario.roles = [SimpleNamespace(role=rol)]

    async def update_fields(self, user, fields: dict):
        self.campos_actualizados.append(dict(fields))
        for clave, valor in fields.items():
            setattr(user, clave, valor)
        return user

    async def commit(self) -> None:
        self.commits += 1


class AuditoriaSimulada:
    def __init__(self) -> None:
        self.registros: list[dict] = []

    async def registrar(self, contexto, **datos) -> None:
        self.registros.append({"contexto": contexto, **datos})


def _rol(nombre: RoleName) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=nombre.value)


def _usuario(rol: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        institutional_id="tec-001",
        full_name="Técnico Uno",
        email="tec-001@uaemex.mx",
        user_type="academic",
        unit_id=None,
        max_load=5,
        is_active=True,
        roles=[SimpleNamespace(role=rol)],
    )


@pytest.fixture
def entorno():
    tecnico = _rol(RoleName.SUPPORT_AGENT)
    gestor = _rol(RoleName.SERVICE_MANAGER)
    usuario = _usuario(tecnico)
    repositorio = RepositorioSimulado(
        usuario, {RoleName.SUPPORT_AGENT: tecnico, RoleName.SERVICE_MANAGER: gestor}
    )
    auditoria = AuditoriaSimulada()
    servicio = UsuarioService(repositorio, directory=None, auditoria=auditoria)
    return SimpleNamespace(
        servicio=servicio,
        repositorio=repositorio,
        auditoria=auditoria,
        usuario=usuario,
        gestor=gestor,
    )


def test_modificar_un_usuario_inexistente_lanza_lookup_error(entorno) -> None:
    with pytest.raises(LookupError, match="No existe un usuario"):
        asyncio.run(entorno.servicio.update_user(uuid.uuid4(), {"max_load": 3}))

    assert entorno.repositorio.campos_actualizados == []
    assert entorno.auditoria.registros == []
    assert entorno.repositorio.commits == 0


def test_un_rol_sin_configurar_se_rechaza_sin_tocar_al_usuario(entorno) -> None:
    with pytest.raises(RoleNotConfiguredError, match=RoleName.AUDITOR.value):
        asyncio.run(
            entorno.servicio.update_user(
                entorno.usuario.id, {"role": RoleName.AUDITOR, "max_load": 3}
            )
        )

    assert entorno.repositorio.roles_reemplazados == []
    assert entorno.repositorio.campos_actualizados == []
    assert entorno.usuario.max_load == 5
    assert entorno.auditoria.registros == []
    assert entorno.repositorio.commits == 0


def test_cambiar_solo_un_campo_no_toca_los_roles(entorno) -> None:
    contexto = AuditContext()

    resultado = asyncio.run(
        entorno.servicio.update_user(entorno.usuario.id, {"max_load": 3}, contexto)
    )

    assert resultado is entorno.usuario
    assert resultado.max_load == 3
    assert entorno.repositorio.roles_reemplazados == []
    assert entorno.repositorio.campos_actualizados == [{"max_load": 3}]
    assert entorno.repositorio.commits == 1
    [registro] = entorno.auditoria.registros
    assert registro["contexto"] is contexto
    assert registro["action"] == "usuario.modificado"
    assert registro["entity_id"] == entorno.usuario.id
    assert registro["old_values"] == {"max_load": 5}
    assert registro["new_values"] == {"max_load": 3}


def test_cambiar_solo_el_rol_no_actualiza_otros_campos(entorno) -> None:
    asyncio.run(
        entorno.servicio.update_user(entorno.usuario.id, {"role": RoleName.SERVICE_MANAGER})
    )

    assert entorno.repositorio.roles_reemplazados == [(entorno.usuario.id, entorno.gestor.id)]
    assert entorno.repositorio.campos_actualizados == []
    [registro] = entorno.auditoria.registros
    assert registro["old_values"] == {"roles": ["support_agent"]}
    assert registro["new_values"] == {"roles": ["service_manager"]}


def test_cambiar_rol_y_campos_a_la_vez_audita_ambos(entorno) -> None:
    asyncio.run(
        entorno.servicio.update_user(
            entorno.usuario.id,
            {"role": RoleName.SERVICE_MANAGER, "full_name": "Técnico Uno Pérez"},
        )
    )

    # El rol se quita del diccionario antes de actualizar los campos.
    assert entorno.repositorio.campos_actualizados == [{"full_name": "Técnico Uno Pérez"}]
    [registro] = entorno.auditoria.registros
    assert set(registro["new_values"]) == {"roles", "full_name"}


def test_sin_cambios_se_audita_un_registro_vacio(entorno) -> None:
    asyncio.run(entorno.servicio.update_user(entorno.usuario.id, {}))

    assert entorno.repositorio.campos_actualizados == []
    assert entorno.repositorio.roles_reemplazados == []
    [registro] = entorno.auditoria.registros
    assert registro["old_values"] == {} and registro["new_values"] == {}
    assert entorno.repositorio.commits == 1
