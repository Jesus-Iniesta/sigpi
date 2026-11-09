"""Exporta las correcciones de clasificación como ejemplos de reentrenamiento (S4-16, HU-02.2).

Lee de la base de datos las solicitudes cuya clasificación corrigió una persona revisora
y escribe un CSV con las mismas columnas que `ml/data/dataset_v1.csv`, con
`source="correccion"`. No modifica `dataset_v1.csv`: unir ambos archivos es parte del
reentrenamiento.

Uso, desde la raíz del repositorio y con el entorno del backend activo (lee
`DATABASE_URL` igual que la API):

    python -m ml.etl.exportar_correcciones [--salida ml/data/correcciones.csv]
"""

import argparse
import asyncio
import sys
from collections.abc import Iterable
from pathlib import Path

from ml.etl.build_dataset import _normalizar, escribir_csv

RAIZ = Path(__file__).resolve().parents[2]
# El backend no es un paquete instalado: se agrega a la ruta para reutilizar su repositorio.
if str(RAIZ / "backend") not in sys.path:
    sys.path.insert(0, str(RAIZ / "backend"))

from app.repositories.correccion_repository import (
    CorreccionRepository,
    EjemploCorregido,
)

FUENTE = "correccion"
RUTA_SALIDA = RAIZ / "ml" / "data" / "correcciones.csv"


def texto_del_ejemplo(ejemplo: EjemploCorregido) -> str:
    """Mismo texto que clasifica el servicio (`texto_de`): título y descripción."""
    return _normalizar(f"{ejemplo.titulo}. {ejemplo.descripcion}")


def construir_filas(ejemplos: Iterable[EjemploCorregido]) -> list[dict[str, str | int]]:
    """Filas con las columnas de `dataset_v1.csv`; el `id` es el folio de la solicitud."""
    return [
        {
            "id": ejemplo.folio,
            "text": texto_del_ejemplo(ejemplo),
            "category": ejemplo.categoria,
            "urgency": ejemplo.urgencia,
            "impact": ejemplo.impacto,
            "source": FUENTE,
        }
        for ejemplo in ejemplos
    ]


async def cargar_ejemplos() -> list[EjemploCorregido]:
    """Consulta las correcciones con la sesión de la aplicación (solo lectura)."""
    from app.db.session import SessionLocal, engine

    try:
        async with SessionLocal() as session:
            return await CorreccionRepository(session).ejemplos_para_reentrenamiento()
    finally:
        await engine.dispose()


def main(salida: Path = RUTA_SALIDA) -> None:
    filas = construir_filas(asyncio.run(cargar_ejemplos()))
    escribir_csv(filas, salida)
    print(f"Correcciones exportadas en {salida}")
    print(f"Total de ejemplos: {len(filas)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=RUTA_SALIDA, help="ruta del CSV")
    main(parser.parse_args().salida)
