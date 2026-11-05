"""CORS: encabezados que el navegador puede leer desde el frontend (COR-06B)."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_expone_content_disposition_al_frontend():
    """Sin exponerlo, el navegador no lee el nombre del contrato descargado."""
    origen = settings.cors_origins[0]
    respuesta = TestClient(app).get("/health", headers={"Origin": origen})

    assert respuesta.status_code == 200
    expuestos = respuesta.headers["access-control-expose-headers"].lower()
    assert "content-disposition" in expuestos
    assert "x-request-id" in expuestos
