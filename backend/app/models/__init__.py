"""SQLAlchemy persistence models for SIGPI."""

from app.models.academic import AcademicRecord, EducationalProgram
from app.models.audit import AuditLog
from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.models.classification import ClassificationCorrection, ClassificationResult, ModelVersion
from app.models.identity import Role, User, UserRole
from app.models.inventory import Asset, AssetCustody, PhysicalSpace
from app.models.knowledge import KnowledgeArticle, KnowledgeSearch
from app.models.maintenance import MaintenanceAct, MaintenanceOrder
from app.models.notification import Notification, NotificationTemplate
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestAssignment, RequestEscalation, RequestLog
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion

__all__ = [
    "AcademicRecord",
    "AreaServicio",
    "Asset",
    "AssetCustody",
    "AuditLog",
    "Categoria",
    "ClassificationCorrection",
    "ClassificationResult",
    "EducationalProgram",
    "Especialidad",
    "KnowledgeArticle",
    "KnowledgeSearch",
    "MaintenanceAct",
    "MaintenanceOrder",
    "ModelVersion",
    "Notification",
    "NotificationTemplate",
    "OrganizationalUnit",
    "PhysicalSpace",
    "Request",
    "RequestAssignment",
    "RequestEscalation",
    "RequestLog",
    "Role",
    "ServiceLevelAgreement",
    "ServiceLevelVersion",
    "Turno",
    "User",
    "UserRole",
]
