from enum import StrEnum


class UserType(StrEnum):
    STUDENT = "student"
    ACADEMIC = "academic"
    ADMINISTRATIVE = "administrative"
    TECHNICAL = "technical"


class SupportLevel(StrEnum):
    LEVEL_1 = "level_1"
    LEVEL_2 = "level_2"


class RequestChannel(StrEnum):
    PORTAL = "portal"
    PHONE = "phone"
    IN_PERSON = "in_person"


class RequestStatus(StrEnum):
    REGISTERED = "registered"
    CLASSIFIED = "classified"
    PENDING_REVIEW = "pending_review"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CLOSED_UNVERIFIED = "closed_unverified"


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class ClassificationSource(StrEnum):
    MODEL = "model"
    RULES = "rules"
    HUMAN = "human"


class EscalationType(StrEnum):
    FUNCTIONAL = "functional"
    HIERARCHICAL = "hierarchical"
    EXTERNAL = "external"


class EscalationStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ArticleStatus(StrEnum):
    DRAFT = "draft"
    PENDING_VALIDATION = "pending_validation"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AssetStatus(StrEnum):
    ACTIVE = "active"
    IN_MAINTENANCE = "in_maintenance"
    RETIRED = "retired"
    PENDING_REGULARIZATION = "pending_regularization"


class MaintenanceType(StrEnum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"


class MaintenanceStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
