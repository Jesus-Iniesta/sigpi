"""Acceso a datos de la administración del clasificador (S5-06, HU-12.1, HU-12.2).

No confirma la transacción (COR-02): lo hace `services/clasificador_admin_service.py`.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.classification import ClassificationCorrection, ClassifierModel
from app.models.enums import RequestStatus
from app.models.request import RequestLog


class ClasificadorAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- ajustes -------------------------------------------------------------

    async def get_ajuste(self, clave: str) -> AppSetting | None:
        return await self._session.get(AppSetting, clave)

    async def guardar_ajuste(
        self, clave: str, valor: str, actor_id: uuid.UUID | None
    ) -> AppSetting:
        """Crea o actualiza el ajuste en la transacción en curso, sin confirmarla."""
        ajuste = await self.get_ajuste(clave)
        if ajuste is None:
            ajuste = AppSetting(key=clave, value=valor, updated_by=actor_id)
            self._session.add(ajuste)
        else:
            ajuste.value = valor
            ajuste.updated_by = actor_id
        await self._session.flush()
        return ajuste

    # --- modelos -------------------------------------------------------------

    async def modelo_activo(self) -> ClassifierModel | None:
        return await self._session.scalar(
            select(ClassifierModel)
            .where(ClassifierModel.is_active.is_(True))
            .order_by(ClassifierModel.created_at.desc())
            .limit(1)
        )

    async def versiones(self) -> list[str]:
        return list(await self._session.scalars(select(ClassifierModel.version)))

    async def agregar_modelo(self, modelo: ClassifierModel, *, activar: bool) -> ClassifierModel:
        """Guarda el modelo; con `activar`, desactiva los demás y lo deja vigente."""
        if activar:
            await self._session.execute(
                update(ClassifierModel)
                .where(ClassifierModel.is_active.is_(True))
                .values(is_active=False)
            )
        modelo.is_active = activar
        self._session.add(modelo)
        await self._session.flush()
        return modelo

    # --- indicadores ---------------------------------------------------------

    async def contar_correcciones_desde(self, desde: datetime | None) -> int:
        consulta = select(func.count(ClassificationCorrection.id))
        if desde is not None:
            consulta = consulta.where(ClassificationCorrection.created_at > desde)
        return int(await self._session.scalar(consulta) or 0)

    async def decisiones_de_clasificacion(self, accion: str, desde: datetime) -> tuple[int, int]:
        """`(total, a_revision)` de las clasificaciones automáticas desde la fecha."""
        filas = await self._session.execute(
            select(RequestLog.new_status, func.count(RequestLog.id))
            .where(RequestLog.action == accion, RequestLog.created_at >= desde)
            .group_by(RequestLog.new_status)
        )
        conteos = {estatus: n for estatus, n in filas}
        return sum(conteos.values()), conteos.get(RequestStatus.PENDING_REVIEW, 0)
