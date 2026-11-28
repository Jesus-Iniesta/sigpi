"""Reglas puras de la carga máxima y la prioridad P1 (S5-14, HU-03.3)."""

import uuid

from app.domain.asignacion import (
    TecnicoCandidato,
    con_capacidad,
    en_carga_maxima,
    proponer,
)

REDES = uuid.uuid4()
MEDIODIA = 12 * 60


def _tecnico(nombre: str, carga: int = 0, carga_maxima: int | None = None) -> TecnicoCandidato:
    return TecnicoCandidato(
        id=uuid.uuid4(),
        nombre=nombre,
        activo=True,
        categorias=frozenset({REDES}),
        carga=carga,
        carga_maxima=carga_maxima,
    )


def _nombres(propuestas) -> list[str]:
    return [p.nombre for p in propuestas]


def test_sin_tope_nunca_esta_al_limite():
    assert en_carga_maxima(50, None) is False


def test_por_debajo_del_tope_no_esta_al_limite():
    assert en_carga_maxima(4, 5) is False


def test_en_el_tope_o_por_encima_esta_al_limite():
    assert en_carga_maxima(5, 5) is True
    assert en_carga_maxima(7, 5) is True


def test_un_tope_de_cero_deja_al_tecnico_siempre_al_limite():
    assert en_carga_maxima(0, 0) is True


def test_la_propuesta_marca_quien_esta_al_limite():
    propuesta = proponer([_tecnico("Ana", 5, 5), _tecnico("Beto", 2, 5)], REDES, MEDIODIA)
    marcas = {p.nombre: p.al_limite for p in propuesta}
    assert marcas == {"Ana": True, "Beto": False}


def test_no_p1_descarta_a_los_tecnicos_en_su_carga_maxima():
    propuesta = proponer([_tecnico("Ana", 5, 5), _tecnico("Beto", 2, 5)], REDES, MEDIODIA)
    assert _nombres(con_capacidad(propuesta, es_p1=False)) == ["Beto"]


def test_p1_ignora_la_carga_maxima():
    propuesta = proponer([_tecnico("Ana", 5, 5), _tecnico("Beto", 2, 5)], REDES, MEDIODIA)
    assert _nombres(con_capacidad(propuesta, es_p1=True)) == ["Beto", "Ana"]


def test_no_p1_con_todos_al_limite_queda_sin_candidatos():
    propuesta = proponer([_tecnico("Ana", 3, 3), _tecnico("Beto", 9, 4)], REDES, MEDIODIA)
    assert con_capacidad(propuesta, es_p1=False) == []


def test_p1_con_todos_al_limite_sigue_teniendo_candidatos():
    propuesta = proponer([_tecnico("Ana", 3, 3), _tecnico("Beto", 9, 4)], REDES, MEDIODIA)
    assert _nombres(con_capacidad(propuesta, es_p1=True)) == ["Ana", "Beto"]


def test_sin_topes_configurados_nadie_se_descarta():
    propuesta = proponer([_tecnico("Ana", 30), _tecnico("Beto", 1)], REDES, MEDIODIA)
    assert _nombres(con_capacidad(propuesta, es_p1=False)) == ["Beto", "Ana"]


def test_conserva_el_orden_de_la_propuesta():
    propuesta = proponer(
        [_tecnico("Zoe", 1, 5), _tecnico("Ana", 1, 5), _tecnico("Mario", 5, 5)], REDES, MEDIODIA
    )
    assert _nombres(con_capacidad(propuesta, es_p1=False)) == ["Ana", "Zoe"]
