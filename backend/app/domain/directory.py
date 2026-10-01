"""Abstraction for the institutional directory, independent of any concrete provider.

The real Microsoft 365 adapter (see tarjeta S3-03) will implement this same
protocol, so nothing in the service or API layer needs to change when it arrives.
"""

from dataclasses import dataclass
from typing import Protocol

from app.models.enums import UserType


@dataclass(frozen=True)
class DirectoryProfile:
    institutional_id: str
    full_name: str
    email: str
    user_type: UserType


class DirectoryClient(Protocol):
    async def fetch_profile(self, institutional_id: str) -> DirectoryProfile | None:
        """Return the profile for an institutional account, or None if unknown."""
        ...