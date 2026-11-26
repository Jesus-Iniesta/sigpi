"""Lectura inversa del desglose del puntaje (S5-12, HU-03.1).

La asignación guarda el desglose como texto (`Propuesta.score_breakdown`); la interfaz
necesita los componentes por separado para mostrarlos. `desglose_desde_texto` los
reconstruye y, si el texto no tiene el formato esperado, devuelve `()` para que se
muestre el texto tal cual.
"""

import uuid

import pytest

from app.domain.asignacion import TecnicoCandidato, desglose_desde_texto, puntuar

REDES = uuid.uuid4()
MEDIODIA = 12 * 60
MATUTINO = {"turno": "Matutino", "turno_inicio": 7 * 60, "turno_fin": 15 * 60}
VESPERTINO = {"turno": "Vespertino", "turno_inicio": 15 * 60, "turno_fin": 23 * 60}


def _tecnico(nombre: str, **datos) -> TecnicoCandidato:
    return TecnicoCandidato(id=uuid.uuid4(), nombre=nombre, activo=True, **datos)


@pytest.mark.parametrize(
    "tecnico",
    [
        _tecnico("Ana", categorias=frozenset({REDES}), carga=2, **MATUTINO),
        _tecnico("Beto", categorias=frozenset({REDES}), carga=1, **VESPERTINO),
        _tecnico("Carla"),
        _tecnico("Dani", carga=40, turno="Matutino (A)", turno_inicio=420, turno_fin=900),
    ],
)
def test_el_desglose_guardado_como_texto_se_reconstruye_igual(tecnico) -> None:
    original = puntuar(tecnico, REDES, MEDIODIA)

    assert desglose_desde_texto(original.score_breakdown) == original.desglose


def test_lee_el_texto_con_concepto_puntos_y_detalle() -> None:
    componentes = desglose_desde_texto(
        "Especialidad +100 (atiende la categoría) · Carga +8 (2 solicitudes activas)"
    )

    assert [(c.concepto, c.puntos, c.detalle) for c in componentes] == [
        ("Especialidad", 100, "atiende la categoría"),
        ("Carga", 8, "2 solicitudes activas"),
    ]


@pytest.mark.parametrize(
    "texto",
    [
        None,
        "",
        "   ",
        "sin formato",
        "Especialidad +100 (atiende la categoría) · Turno sin puntos",
        "Especialidad 100 (atiende la categoría)",
    ],
)
def test_un_texto_vacio_o_sin_formato_no_produce_componentes(texto) -> None:
    assert desglose_desde_texto(texto) == ()
