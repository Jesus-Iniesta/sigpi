"""Pruebas del puntaje de asignación por carga y especialidad (S5-13, HU-03.1).

Cubre las reglas puras de `app.domain.asignacion`, sin base de datos ni servidor:

- **Carga:** cada solicitud activa resta un punto de los 10 posibles y nunca baja de 0;
  entre dos expertos gana el menos cargado.
- **Especialidad:** pesa más que turno y carga juntos; solo suma una vez aunque el técnico
  atienda varias categorías; sin categoría nadie la recibe.
- **Turno:** inicio inclusivo, fin exclusivo, y turnos que cruzan la medianoche.
- **Desempates:** mismo puntaje → menor carga → nombre.
- **Desglose:** los tres conceptos, su texto y la suma que da el puntaje.
"""

import uuid

import pytest

from app.domain.asignacion import (
    PUNTOS_CARGA_MAX,
    PUNTOS_ESPECIALIDAD,
    PUNTOS_TURNO,
    TecnicoCandidato,
    proponer,
    puntos_carga,
    puntuar,
    turno_vigente,
)

REDES = uuid.uuid4()
SOFTWARE = uuid.uuid4()
MEDIODIA = 12 * 60
MATUTINO = {"turno": "Matutino", "turno_inicio": 7 * 60, "turno_fin": 15 * 60}
VESPERTINO = {"turno": "Vespertino", "turno_inicio": 15 * 60, "turno_fin": 23 * 60}


def _tecnico(nombre: str, **datos) -> TecnicoCandidato:
    return TecnicoCandidato(
        id=uuid.uuid4(), nombre=nombre, activo=datos.pop("activo", True), **datos
    )


def _experto(nombre: str, carga: int = 0, **datos) -> TecnicoCandidato:
    return _tecnico(nombre, categorias=frozenset({REDES}), carga=carga, **datos)


def _nombres(propuesta) -> list[str]:
    return [p.nombre for p in propuesta]


def _puntos(propuesta, concepto: str) -> int:
    return next(c.puntos for c in propuesta.desglose if c.concepto == concepto)


# ------------------------------------------------------------------------- carga


@pytest.mark.parametrize(
    ("carga", "esperados"),
    [(0, 10), (1, 9), (5, 5), (9, 1), (10, 0)],
)
def test_cada_solicitud_activa_resta_un_punto_de_carga(carga, esperados) -> None:
    assert puntos_carga(carga) == esperados


@pytest.mark.parametrize("carga", [11, 15, 50, 1000])
def test_la_carga_excesiva_no_resta_puntos(carga) -> None:
    assert puntos_carga(carga) == 0


def test_una_carga_negativa_no_da_mas_del_maximo() -> None:
    assert puntos_carga(-3) == PUNTOS_CARGA_MAX


def test_entre_expertos_gana_el_menos_cargado() -> None:
    libre = _experto("Ana", carga=0)
    medio = _experto("Beto", carga=2)
    saturado = _experto("Carla", carga=7)

    propuesta = proponer([saturado, libre, medio], REDES, MEDIODIA)

    assert _nombres(propuesta) == ["Ana", "Beto", "Carla"]
    assert [p.score for p in propuesta] == [
        PUNTOS_ESPECIALIDAD + 10,
        PUNTOS_ESPECIALIDAD + 8,
        PUNTOS_ESPECIALIDAD + 3,
    ]
    assert [p.carga for p in propuesta] == [0, 2, 7]


def test_carga_saturada_empata_en_puntaje_y_gana_la_menos_cargada() -> None:
    carga_10 = _experto("Zoe", carga=10)
    carga_12 = _experto("Ana", carga=12)

    propuesta = proponer([carga_12, carga_10], REDES, MEDIODIA)

    assert propuesta[0].score == propuesta[1].score == PUNTOS_ESPECIALIDAD
    assert _nombres(propuesta) == ["Zoe", "Ana"]


def test_con_todo_igual_el_orden_es_por_nombre() -> None:
    propuesta = proponer([_experto("Zoe"), _experto("Ana"), _experto("Mario")], REDES, MEDIODIA)

    assert _nombres(propuesta) == ["Ana", "Mario", "Zoe"]


# ------------------------------------------------------------------ especialidad


def test_la_especialidad_pesa_mas_que_el_turno_y_la_carga_juntos() -> None:
    assert PUNTOS_ESPECIALIDAD > PUNTOS_TURNO + PUNTOS_CARGA_MAX

    experto_saturado = _experto("Beto", carga=30, **VESPERTINO)  # fuera de turno
    sin_especialidad_ideal = _tecnico("Ana", categorias=frozenset({SOFTWARE}), carga=0, **MATUTINO)

    propuesta = proponer([sin_especialidad_ideal, experto_saturado], REDES, MEDIODIA)

    assert _nombres(propuesta) == ["Beto", "Ana"]
    assert propuesta[0].score == PUNTOS_ESPECIALIDAD
    assert propuesta[1].score == PUNTOS_TURNO + PUNTOS_CARGA_MAX


def test_atender_varias_categorias_suma_la_especialidad_una_sola_vez() -> None:
    polivalente = _tecnico("Ana", categorias=frozenset({REDES, SOFTWARE}))

    assert _puntos(puntuar(polivalente, REDES, MEDIODIA), "Especialidad") == PUNTOS_ESPECIALIDAD
    assert _puntos(puntuar(polivalente, SOFTWARE, MEDIODIA), "Especialidad") == PUNTOS_ESPECIALIDAD


def test_otra_categoria_no_da_puntos_de_especialidad() -> None:
    especialista_en_software = _tecnico("Ana", categorias=frozenset({SOFTWARE}))

    resultado = puntuar(especialista_en_software, REDES, MEDIODIA)

    assert _puntos(resultado, "Especialidad") == 0
    assert resultado.desglose[0].detalle == "sin especialidad de la categoría"


def test_sin_categoria_nadie_recibe_puntos_de_especialidad() -> None:
    propuesta = proponer([_experto("Ana"), _experto("Beto", carga=3)], None, MEDIODIA)

    assert all(_puntos(p, "Especialidad") == 0 for p in propuesta)
    assert _nombres(propuesta) == ["Ana", "Beto"]  # decide la carga


def test_un_tecnico_sin_especialidades_no_la_recibe() -> None:
    assert _puntos(puntuar(_tecnico("Ana"), REDES, MEDIODIA), "Especialidad") == 0


# ------------------------------------------------------------------------- turno


def test_el_turno_vigente_suma_puntos_y_fuera_de_turno_no() -> None:
    en_turno = puntuar(_experto("Ana", **MATUTINO), REDES, MEDIODIA)
    fuera = puntuar(_experto("Beto", **VESPERTINO), REDES, MEDIODIA)
    sin_turno = puntuar(_experto("Carla"), REDES, MEDIODIA)

    assert _puntos(en_turno, "Turno") == PUNTOS_TURNO
    assert _puntos(fuera, "Turno") == 0
    assert _puntos(sin_turno, "Turno") == 0
    assert en_turno.desglose[1].detalle == "Matutino: en turno"
    assert fuera.desglose[1].detalle == "Vespertino: fuera de turno"
    assert sin_turno.desglose[1].detalle == "sin turno: fuera de turno"


@pytest.mark.parametrize(
    ("minuto", "vigente"),
    [
        (7 * 60 - 1, False),  # un minuto antes de iniciar
        (7 * 60, True),  # el inicio es inclusivo
        (15 * 60 - 1, True),
        (15 * 60, False),  # el fin es exclusivo
        (MEDIODIA + 24 * 60, True),  # el minuto se toma dentro del día
    ],
)
def test_limites_del_turno_matutino(minuto, vigente) -> None:
    assert turno_vigente(7 * 60, 15 * 60, minuto) is vigente


@pytest.mark.parametrize(
    ("minuto", "vigente"),
    [
        (21 * 60 + 59, False),
        (22 * 60, True),
        (23 * 60 + 30, True),
        (0, True),
        (5 * 60 + 59, True),
        (6 * 60, False),
        (MEDIODIA, False),
    ],
)
def test_turno_nocturno_que_cruza_la_medianoche(minuto, vigente) -> None:
    assert turno_vigente(22 * 60, 6 * 60, minuto) is vigente


def test_sin_horario_el_turno_nunca_esta_vigente() -> None:
    assert turno_vigente(None, None, MEDIODIA) is False
    assert turno_vigente(7 * 60, None, MEDIODIA) is False
    assert turno_vigente(None, 15 * 60, MEDIODIA) is False


# ------------------------------------------------------------------------ desglose


def test_el_puntaje_es_la_suma_de_sus_tres_componentes() -> None:
    resultado = puntuar(_experto("Ana", carga=4, **MATUTINO), REDES, MEDIODIA)

    assert [c.concepto for c in resultado.desglose] == ["Especialidad", "Turno", "Carga"]
    assert [c.puntos for c in resultado.desglose] == [PUNTOS_ESPECIALIDAD, PUNTOS_TURNO, 6]
    assert resultado.score == sum(c.puntos for c in resultado.desglose) == 126
    assert resultado.carga == 4


@pytest.mark.parametrize(
    ("carga", "texto"),
    [(0, "0 solicitudes activas"), (1, "1 solicitud activa"), (3, "3 solicitudes activas")],
)
def test_el_detalle_de_carga_usa_singular_y_plural(carga, texto) -> None:
    resultado = puntuar(_experto("Ana", carga=carga), REDES, MEDIODIA)

    assert resultado.desglose[2].detalle == texto


def test_el_texto_del_desglose_lista_concepto_puntos_y_detalle() -> None:
    resultado = puntuar(_experto("Ana", carga=2, **MATUTINO), REDES, MEDIODIA)

    assert resultado.score_breakdown == (
        "Especialidad +100 (atiende la categoría)"
        " · Turno +20 (Matutino: en turno)"
        " · Carga +8 (2 solicitudes activas)"
    )


def test_escenario_completo_con_carga_especialidad_y_turno() -> None:
    ana = _experto("Ana", carga=2, **MATUTINO)  # 100 + 20 + 8
    beto = _experto("Beto", carga=0, **VESPERTINO)  # 100 + 0 + 10
    carla = _tecnico("Carla", categorias=frozenset({SOFTWARE}), **MATUTINO)  # 0 + 20 + 10
    dani = _tecnico("Dani", carga=4)  # 0 + 0 + 6

    propuesta = proponer([dani, carla, beto, ana], REDES, MEDIODIA)

    assert _nombres(propuesta) == ["Ana", "Beto", "Carla", "Dani"]
    assert [p.score for p in propuesta] == [128, 110, 30, 6]


# ---------------------------------------------------------------------- candidatos


def test_los_inactivos_no_son_candidatos_aunque_sean_los_mejores() -> None:
    inactivo = _experto("Ana", activo=False)
    activo = _tecnico("Beto", carga=9)

    assert _nombres(proponer([inactivo, activo], REDES, MEDIODIA)) == ["Beto"]


def test_sin_tecnicos_la_propuesta_esta_vacia() -> None:
    assert proponer([], REDES, MEDIODIA) == []
    assert proponer([_experto("Ana", activo=False)], REDES, MEDIODIA) == []
