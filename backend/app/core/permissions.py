from enum import StrEnum


class Permission(StrEnum):
    REQUESTS_READ = "requests.read"
    REQUESTS_CREATE = "requests.create"
    REQUESTS_UPDATE = "requests.update"
    REQUESTS_ASSIGN = "requests.assign"
    REQUESTS_CLOSE = "requests.close"
    CLASSIFICATION_READ = "classification.read"
    CLASSIFICATION_REVIEW = "classification.review"
    SLA_READ = "sla.read"
    SLA_MANAGE = "sla.manage"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_MANAGE = "knowledge.manage"
    INVENTORY_READ = "inventory.read"
    INVENTORY_MANAGE = "inventory.manage"
    MAINTENANCE_READ = "maintenance.read"
    MAINTENANCE_MANAGE = "maintenance.manage"
    CATALOG_READ = "catalog.read"
    CATALOG_MANAGE = "catalog.manage"
    IDENTITY_READ = "identity.read"
    IDENTITY_MANAGE = "identity.manage"
    REPORTS_READ = "reports.read"


class RoleName(StrEnum):
    ADMINISTRATOR = "administrator"
    SERVICE_MANAGER = "service_manager"
    SUPPORT_AGENT = "support_agent"
    CLASSIFIER = "classifier"
    KNOWLEDGE_MANAGER = "knowledge_manager"
    AUDITOR = "auditor"
    REQUESTER = "requester"


ROLE_PERMISSIONS: dict[RoleName, frozenset[Permission]] = {
    RoleName.ADMINISTRATOR: frozenset(Permission),
    RoleName.SERVICE_MANAGER: frozenset(
        {
            Permission.REQUESTS_READ,
            Permission.REQUESTS_UPDATE,
            Permission.REQUESTS_ASSIGN,
            Permission.REQUESTS_CLOSE,
            Permission.CLASSIFICATION_READ,
            Permission.CLASSIFICATION_REVIEW,
            Permission.SLA_READ,
            Permission.SLA_MANAGE,
            Permission.KNOWLEDGE_READ,
            Permission.KNOWLEDGE_MANAGE,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_MANAGE,
            Permission.MAINTENANCE_READ,
            Permission.MAINTENANCE_MANAGE,
            Permission.CATALOG_READ,
            Permission.CATALOG_MANAGE,
            Permission.REPORTS_READ,
        }
    ),
    RoleName.SUPPORT_AGENT: frozenset(
        {
            Permission.REQUESTS_READ,
            Permission.REQUESTS_UPDATE,
            Permission.REQUESTS_ASSIGN,
            Permission.REQUESTS_CLOSE,
            Permission.CLASSIFICATION_READ,
            Permission.KNOWLEDGE_READ,
            Permission.INVENTORY_READ,
            Permission.MAINTENANCE_READ,
            Permission.CATALOG_READ,
        }
    ),
    RoleName.CLASSIFIER: frozenset(
        {
            Permission.REQUESTS_READ,
            Permission.CLASSIFICATION_READ,
            Permission.CLASSIFICATION_REVIEW,
            Permission.CATALOG_READ,
        }
    ),
    RoleName.KNOWLEDGE_MANAGER: frozenset(
        {Permission.REQUESTS_READ, Permission.KNOWLEDGE_READ, Permission.KNOWLEDGE_MANAGE}
    ),
    RoleName.AUDITOR: frozenset(
        {
            Permission.REQUESTS_READ,
            Permission.SLA_READ,
            Permission.KNOWLEDGE_READ,
            Permission.INVENTORY_READ,
            Permission.MAINTENANCE_READ,
            Permission.CATALOG_READ,
            Permission.IDENTITY_READ,
            Permission.REPORTS_READ,
        }
    ),
    RoleName.REQUESTER: frozenset(
        {Permission.REQUESTS_READ, Permission.REQUESTS_CREATE, Permission.KNOWLEDGE_READ}
    ),
}


def permissions_for_role(role: RoleName | str) -> frozenset[Permission]:
    """Return the immutable permission set assigned to a role."""
    try:
        role_name = role if isinstance(role, RoleName) else RoleName(role)
    except ValueError:
        return frozenset()
    return ROLE_PERMISSIONS.get(role_name, frozenset())


def has_permission(role: RoleName | str, permission: Permission | str) -> bool:
    """Check one permission without granting access to unknown roles or permissions."""
    try:
        permission_name = (
            permission if isinstance(permission, Permission) else Permission(permission)
        )
    except ValueError:
        return False
    return permission_name in permissions_for_role(role)
