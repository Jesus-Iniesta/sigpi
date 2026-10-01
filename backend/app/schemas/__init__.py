"""Pydantic request and response contracts."""

from app.schemas.catalog import (
    CategoryCreate,
    CategoryRead,
    ServiceAreaCreate,
    ServiceAreaRead,
    ShiftCreate,
    ShiftRead,
    SpecialtyCreate,
    SpecialtyRead,
    TechnicianProfileUpdate,
    TechnicianRead,
)
from app.schemas.identity import UserCreate, UserRead
from app.schemas.request import (
    RequestCreate,
    RequestListItem,
    RequestLogCreate,
    RequestLogRead,
    RequestRead,
    RequestUpdate,
)

__all__ = [
    "CategoryCreate",
    "CategoryRead",
    "RequestCreate",
    "RequestListItem",
    "RequestLogCreate",
    "RequestLogRead",
    "RequestRead",
    "RequestUpdate",
    "ServiceAreaCreate",
    "ServiceAreaRead",
    "ShiftCreate",
    "ShiftRead",
    "SpecialtyCreate",
    "SpecialtyRead",
    "TechnicianProfileUpdate",
    "TechnicianRead",
    "UserCreate",
    "UserRead",
]
