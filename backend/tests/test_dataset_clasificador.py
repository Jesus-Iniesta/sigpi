"""Pruebas del conjunto de datos etiquetado del clasificador (S4-11, HU-02.1).

Verifican que `ml/data/dataset_v1.csv` esté balanceado por categoría, use las categorías
del catálogo y niveles válidos, y que coincida con lo que genera `ml/etl/build_dataset.py`
a partir de los ejemplos del equipo.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from ml.etl.build_dataset import (
    CATEGORIAS,
    COLUMNAS,
    LONGITUD_MINIMA,
    RUTA_SALIDA,
    DatasetInvalidoError,
    construir_filas,
    escribir_csv,
)
from ml.etl.ejemplos_equipo import EJEMPLOS

from app.seeds.data import CATEGORY_SEEDS

POR_CATEGORIA = 30


def _leer(ruta: Path) -> list[dict[str, str]]:
    with ruta.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


@pytest.fixture(scope="module")
def filas() -> list[dict[str, str]]:
    return _leer(RUTA_SALIDA)


def _ejemplo(categoria: str = "Hardware", urgencia: int = 2, impacto: int = 2, texto: str = ""):
    texto = texto or f"Texto de prueba suficientemente largo para {categoria} {urgencia}{impacto}"
    return (categoria, urgencia, impacto, texto)


def _balanceados(por_categoria: int = 2) -> list[tuple[str, int, int, str]]:
    return [
        _ejemplo(categoria, texto=f"Ejemplo número {numero} de la categoría {categoria}")
        for categoria in CATEGORIAS
        for numero in range(por_categoria)
    ]


# --- El archivo generado ---------------------------------------------------------------


def test_el_csv_tiene_las_columnas_esperadas() -> None:
    with RUTA_SALIDA.open(encoding="utf-8", newline="") as archivo:
        assert tuple(next(csv.reader(archivo))) == COLUMNAS


def test_las_categorias_coinciden_con_las_del_catalogo() -> None:
    assert set(CATEGORIAS) == {nombre for nombre, _descripcion in CATEGORY_SEEDS}


def test_el_conjunto_esta_balanceado_por_categoria(filas) -> None:
    conteo = Counter(fila["category"] for fila in filas)
    assert conteo == {categoria: POR_CATEGORIA for categoria in CATEGORIAS}


def test_urgencia_e_impacto_son_niveles_validos(filas) -> None:
    for fila in filas:
        assert fila["urgency"] in {"1", "2", "3"}, fila["id"]
        assert fila["impact"] in {"1", "2", "3"}, fila["id"]


def test_aparecen_las_nueve_combinaciones_de_urgencia_e_impacto(filas) -> None:
    combinaciones = {(fila["urgency"], fila["impact"]) for fila in filas}
    assert len(combinaciones) == 9


def test_cada_categoria_cubre_los_tres_niveles_de_urgencia_y_de_impacto(filas) -> None:
    for categoria in CATEGORIAS:
        propias = [fila for fila in filas if fila["category"] == categoria]
        assert {fila["urgency"] for fila in propias} == {"1", "2", "3"}, categoria
        assert {fila["impact"] for fila in propias} == {"1", "2", "3"}, categoria


def test_los_textos_son_unicos_y_tienen_longitud_suficiente(filas) -> None:
    textos = [fila["text"].casefold() for fila in filas]
    assert len(set(textos)) == len(textos)
    assert all(len(fila["text"]) >= LONGITUD_MINIMA for fila in filas)


def test_los_identificadores_son_unicos(filas) -> None:
    identificadores = [fila["id"] for fila in filas]
    assert len(set(identificadores)) == len(identificadores)


def test_el_csv_esta_actualizado_respecto_de_los_ejemplos(filas) -> None:
    """Si cambian los ejemplos hay que regenerar: `python -m ml.etl.build_dataset`."""
    esperado = [
        {columna: str(fila[columna]) for columna in COLUMNAS} for fila in construir_filas(EJEMPLOS)
    ]
    assert filas == esperado


def test_la_generacion_es_reproducible(tmp_path) -> None:
    primero, segundo = tmp_path / "a.csv", tmp_path / "b.csv"
    escribir_csv(construir_filas(EJEMPLOS), primero)
    escribir_csv(construir_filas(EJEMPLOS), segundo)
    assert primero.read_bytes() == segundo.read_bytes()


# --- Las validaciones del generador -----------------------------------------------------


def test_rechaza_una_categoria_desconocida() -> None:
    ejemplos = [*_balanceados(), _ejemplo("Impresoras")]
    with pytest.raises(DatasetInvalidoError, match="categoría desconocida"):
        construir_filas(ejemplos)


@pytest.mark.parametrize("valor", [0, 4, "2", 2.0, True])
def test_rechaza_urgencia_o_impacto_fuera_de_rango(valor) -> None:
    for ejemplo in (_ejemplo(urgencia=valor), _ejemplo(impacto=valor)):
        with pytest.raises(DatasetInvalidoError, match="entero de 1 a 3"):
            construir_filas([*_balanceados(), ejemplo])


def test_rechaza_un_texto_demasiado_corto() -> None:
    with pytest.raises(DatasetInvalidoError, match="mínimo"):
        construir_filas([*_balanceados(), _ejemplo(texto="No prende")])


def test_rechaza_textos_repetidos_aunque_cambien_las_mayusculas_o_los_espacios() -> None:
    original = _ejemplo(texto="La impresora de la coordinación no imprime desde ayer")
    repetido = _ejemplo(texto="  la IMPRESORA de la coordinación   no imprime desde ayer ")
    with pytest.raises(DatasetInvalidoError, match="repetido"):
        construir_filas([*_balanceados(), original, repetido])


def test_rechaza_un_conjunto_desbalanceado() -> None:
    with pytest.raises(DatasetInvalidoError, match="mismos ejemplos en cada categoría"):
        construir_filas(
            [*_balanceados(), _ejemplo("Redes", texto="Un ejemplo extra de redes largo")]
        )


def test_rechaza_un_conjunto_sin_alguna_categoria() -> None:
    sin_redes = [ejemplo for ejemplo in _balanceados() if ejemplo[0] != "Redes"]
    with pytest.raises(DatasetInvalidoError, match="mismos ejemplos en cada categoría"):
        construir_filas(sin_redes)
