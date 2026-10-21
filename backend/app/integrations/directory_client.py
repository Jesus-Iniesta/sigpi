"""Stand-in for the institutional directory used when provisioning accounts.

The team decided not to integrate Microsoft 365 (S3-03): SIGPI keeps its own
credentials and validates them itself. This client only supplies the profile
data (name, email, user type) for an institutional ID when an account is created.
It implements the `DirectoryClient` protocol from `app.domain.directory`.
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
    "uaem2026002": DirectoryProfile(
        institutional_id="uaem2026002",
        full_name="Carlos López Hernández",
        email="clopez@uaemex.mx",
        user_type=UserType.STUDENT,
    ),
    "uaem2026003": DirectoryProfile(
        institutional_id="uaem2026003",
        full_name="María González Pérez",
        email="mgonzalez@uaemex.mx",
        user_type=UserType.ADMINISTRATIVE,
    ),
    "uaem2026004": DirectoryProfile(
        institutional_id="uaem2026004",
        full_name="José Ramírez Torres",
        email="jramirez@uaemex.mx",
        user_type=UserType.TECHNICAL,
    ),
}


class StubDirectoryClient:
    def __init__(self, known_profiles: dict[str, DirectoryProfile] | None = None) -> None:
        self._profiles = known_profiles if known_profiles is not None else dict(_DEMO_PROFILES)

    async def fetch_profile(self, institutional_id: str) -> DirectoryProfile | None:
        return self._profiles.get(institutional_id)
