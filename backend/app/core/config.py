from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.network import parse_trusted_proxies


class Settings(BaseSettings):
    app_name: str = "SIGPI"
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "sigpi"
    database_user: str = ""
    database_password: str = ""
    # RN-06: confianza mínima (de 0 a 1) para aceptar una clasificación sin revisión humana.
    classification_confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    # Conjunto de datos del clasificador (S4-12), relativo a la raíz del repositorio.
    classifier_dataset_path: str = "ml/data/dataset_v1.csv"
    sla_warning_threshold: float = 0.80
    # Monitor del umbral de riesgo del SLA (S4-08). Apagado por defecto (y en pruebas);
    # actívalo con SLA_MONITOR_ENABLED=true donde se despliegue la aplicación.
    sla_monitor_enabled: bool = False
    sla_monitor_interval_seconds: float = 30
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Proxies de confianza (S5-08): IPs o redes CIDR separadas por comas. Solo si la
    # conexión directa viene de uno de ellos se usa `X-Forwarded-For` como IP auditada.
    # Vacío por omisión: se audita siempre la IP del cliente directo.
    trusted_proxies: str = ""

    # Registro de eventos (S3-01): DEBUG, INFO, WARNING o ERROR.
    log_level: str = "INFO" 

    # Autenticación (S3-03). Define JWT_SECRET_KEY en tu .env; el valor por defecto
    # solo sirve para desarrollo local y nunca debe usarse en producción.
    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    max_failed_login_attempts: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("trusted_proxies")
    @classmethod
    def _validar_proxies(cls, value: str) -> str:
        """Falla al arrancar si `TRUSTED_PROXIES` trae algo que no es IP ni red CIDR."""
        parse_trusted_proxies(value)
        return value

    @property
    def database_url(self) -> str:
        user = quote_plus(self.database_user)
        password = quote_plus(self.database_password)
        return (
            f"postgresql+asyncpg://{user}:{password}@{self.database_host}:"
            f"{self.database_port}/{self.database_name}"
        )

    @property
    def database_sync_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg2")


settings = Settings()
