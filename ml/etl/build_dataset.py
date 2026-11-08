"""Construye el conjunto de datos etiquetado del clasificador (S4-11, HU-02.1).

Lee los ejemplos redactados por el equipo (`ejemplos_equipo.py`), los valida, comprueba
que estén balanceados por categoría y escribe `ml/data/dataset_v1.csv`.

Uso, desde la raíz del repositorio (no requiere dependencias externas):

    python -m ml.etl.build_dataset
"""

import argparse
import csv
import random
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from ml.etl.ejemplos_equipo import EJEMPLOS

# Debe coincidir con las categorías sembradas en `backend/app/seeds/data.py`
# (lo verifica `backend/tests/test_dataset_clasificador.py`).
CATEGORIAS: tuple[str, ...] = ("Hardware", "Software", "Redes", "Cuentas y accesos")
NIVELES: tuple[int, ...] = (1, 2, 3)
COLUMNAS: tuple[str, ...] = ("id", "text", "category", "urgency", "impact", "source")
FUENTE = "equipo"
LONGITUD_MINIMA = 30  # igual que el mínimo de la descripción de una solicitud (HU-01.1)
SEMILLA = 42
RUTA_SALIDA = Path(__file__).resolve().parents[1] / "data" / "dataset_v1.csv"


class DatasetInvalidoError(ValueError):
    """Un ejemplo o el conjunto completo incumple las reglas del conjunto de datos."""


def _normalizar(texto: str) -> str:
    """Quita espacios sobrantes y saltos de línea dentro del texto."""
    return re.sub(r"\s+", " ", texto).strip()


def construir_filas(
    ejemplos: Iterable[tuple[str, int, int, str]], semilla: int = SEMILLA
) -> list[dict[str, str | int]]:
    """Valida los ejemplos y devuelve las filas del conjunto, en un orden reproducible."""
    limpios: list[tuple[str, int, int, str]] = []
    vistos: set[str] = set()

    for posicion, (categoria, urgencia, impacto, texto) in enumerate(ejemplos, start=1):
        if categoria not in CATEGORIAS:
            raise DatasetInvalidoError(
                f"Ejemplo {posicion}: categoría desconocida «{categoria}»."
            )
        for nombre, valor in (("urgencia", urgencia), ("impacto", impacto)):
            if type(valor) is not int or valor not in NIVELES:
                raise DatasetInvalidoError(
                    f"Ejemplo {posicion}: {nombre} debe ser un entero de 1 a 3, no {valor!r}."
                )
        texto = _normalizar(texto)
        if len(texto) < LONGITUD_MINIMA:
            raise DatasetInvalidoError(
                f"Ejemplo {posicion}: el texto tiene {len(texto)} caracteres y el mínimo "
                f"es {LONGITUD_MINIMA}."
            )
        clave = texto.casefold()
        if clave in vistos:
            raise DatasetInvalidoError(f"Ejemplo {posicion}: texto repetido «{texto}».")
        vistos.add(clave)
        limpios.append((categoria, urgencia, impacto, texto))

    conteo = Counter(categoria for categoria, *_ in limpios)
    if set(conteo) != set(CATEGORIAS) or len(set(conteo.values())) != 1:
        detalle = ", ".join(f"{c}: {conteo.get(c, 0)}" for c in CATEGORIAS)
        raise DatasetInvalidoError(
            f"El conjunto debe tener los mismos ejemplos en cada categoría ({detalle})."
        )

    random.Random(semilla).shuffle(limpios)
    return [
        {
            "id": f"SOL-{numero:03d}",
            "text": texto,
            "category": categoria,
            "urgency": urgencia,
            "impact": impacto,
            "source": FUENTE,
        }
        for numero, (categoria, urgencia, impacto, texto) in enumerate(limpios, start=1)
    ]


def escribir_csv(filas: list[dict[str, str | int]], ruta: Path) -> None:
    """Escribe el CSV en UTF-8 y con saltos de línea `\\n`, igual en cualquier sistema."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(filas)


def main(salida: Path = RUTA_SALIDA) -> None:
    filas = construir_filas(EJEMPLOS)
    escribir_csv(filas, salida)
    por_categoria = Counter(str(fila["category"]) for fila in filas)
    print(f"Conjunto de datos escrito en {salida}")
    print(f"Total de ejemplos: {len(filas)}")
    for categoria in CATEGORIAS:
        print(f"  {categoria}: {por_categoria[categoria]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=RUTA_SALIDA, help="ruta del CSV")
    main(parser.parse_args().salida)