"""Pruebas del conjunto de datos ampliado del clasificador (S5-07, HU-12.2, riesgo RT-01).

Verifican que `ml/data/dataset_v2.csv` cargue, tenga las columnas de `dataset_v1.csv`,
no tenga filas vacías ni duplicadas, esté balanceado por categoría, tenga al menos 240
ejemplos y contenga íntegro `dataset_v1.csv`.
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from ml.etl.build_dataset import CATEGORIAS, COLUMNAS, LONGITUD_MINIMA

from app.integrations.clasificador_client import cargar_ejemplos

RUTA_V1 = RAIZ / "ml" / "data" / "dataset_v1.csv"
RUTA_V2 = RAIZ / "ml" / "data" / "dataset_v2.csv"
MINIMO_EJEMPLOS = 240


def _leer(ruta: Path) -> list[dict[str, str]]:
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def _clave(texto: str) -> str:
    """Texto comparable: sin espacios sobrantes y sin distinguir mayúsculas."""
    return re.sub(r"\s+", " ", texto).strip().casefold()


@pytest.fixture(scope="module")
def filas() -> list[dict[str, str]]:
    return _leer(RUTA_V2)


def test_el_csv_carga_con_el_lector_del_clasificador() -> None:
    ejemplos = cargar_ejemplos(RUTA_V2)
    assert len(ejemplos) >= MINIMO_EJEMPLOS
    assert {ejemplo.categoria for ejemplo in ejemplos} == set(CATEGORIAS)


def test_tiene_las_mismas_columnas_que_v1() -> None:
    with RUTA_V2.open(encoding="utf-8", newline="") as archivo:
        encabezado = tuple(next(csv.reader(archivo)))
    assert encabezado == COLUMNAS
    with RUTA_V1.open(encoding="utf-8", newline="") as archivo:
        assert tuple(next(csv.reader(archivo))) == encabezado


def test_no_hay_filas_ni_campos_vacios(filas) -> None:
    for numero, fila in enumerate(filas, start=2):
        assert None not in fila, f"línea {numero}: sobran columnas"
        for columna in COLUMNAS:
            assert (fila.get(columna) or "").strip(), f"línea {numero}: «{columna}» vacío"
    with RUTA_V2.open(encoding="utf-8", newline="") as archivo:
        assert all(linea.strip() for linea in archivo), "hay líneas en blanco"


def test_no_hay_filas_duplicadas(filas) -> None:
    identificadores = [fila["id"] for fila in filas]
    assert len(set(identificadores)) == len(identificadores)
    textos = [_clave(fila["text"]) for fila in filas]
    repetidos = [texto for texto, veces in Counter(textos).items() if veces > 1]
    assert repetidos == []


def test_tiene_al_menos_240_ejemplos_balanceados_por_categoria(filas) -> None:
    assert len(filas) >= MINIMO_EJEMPLOS
    conteo = Counter(fila["category"] for fila in filas)
    assert set(conteo) == set(CATEGORIAS)
    assert len(set(conteo.values())) == 1, conteo


def test_urgencia_impacto_y_longitud_son_validos(filas) -> None:
    for fila in filas:
        assert fila["urgency"] in {"1", "2", "3"}, fila["id"]
        assert fila["impact"] in {"1", "2", "3"}, fila["id"]
        assert len(fila["text"]) >= LONGITUD_MINIMA, fila["id"]


def test_cada_categoria_cubre_las_nueve_combinaciones_de_urgencia_e_impacto(filas) -> None:
    for categoria in CATEGORIAS:
        combinaciones = {
            (fila["urgency"], fila["impact"]) for fila in filas if fila["category"] == categoria
        }
        assert len(combinaciones) == 9, categoria


def test_contiene_v1_completo_y_al_menos_120_ejemplos_nuevos(filas) -> None:
    v1 = _leer(RUTA_V1)
    assert len(v1) == 120, "dataset_v1.csv no debe cambiar"
    assert filas[: len(v1)] == v1
    nuevos = filas[len(v1) :]
    assert len(nuevos) >= 120
    textos_v1 = {_clave(fila["text"]) for fila in v1}
    assert not any(_clave(fila["text"]) in textos_v1 for fila in nuevos)
    assert len(set(Counter(fila["category"] for fila in nuevos).values())) == 1
