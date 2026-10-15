"""Contratos del inicio de sesión (S3-03)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import INSTITUTIONAL_EMAIL_DOMAIN, is_institutional_email
from app.schemas.identity import UserRead


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _institutional_email(cls, value: str) -> str:
        value = value.strip()
        if not is_institutional_email(value):
            raise ValueError(
                f"El correo debe tener el formato usuario@{INSTITUTIONAL_EMAIL_DOMAIN}."
            )
        return value.lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
