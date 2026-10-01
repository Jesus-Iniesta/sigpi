"""Temporary stand-in for the Microsoft 365 institutional directory.

TODO(S3-03): replace with the real adapter once the directory integration
exists. It must implement the same `DirectoryClient` protocol from
`app.domain.directory` so no other code needs to change.
"""

from app.domain.directory import DirectoryProfile
from app.models.enums import UserType

# Perfiles de ejemplo para pruebas manuales en Swagger mientras no existe el
# directorio real. No tiene ningún significado de negocio, solo conveniencia.
_DEMO_PROFILES: dict[str, DirectoryProfile] = {
    "uaem2026001": DirectoryProfile(
        institutional_id="uaem2026001",
        full_name="Ana Martínez Soto",
        email="amartinez@uaemex.mx",
        user_type=UserType.ACADEMIC,
    ),
}


class StubDirectoryClient:
    def __init__(self, known_profiles: dict[str, DirectoryProfile] | None = None) -> None:
        self._profiles = known_profiles if known_profiles is not None else dict(_DEMO_PROFILES)

    async def fetch_profile(self, institutional_id: str) -> DirectoryProfile | None:
        return self._profiles.get(institutional_id)
