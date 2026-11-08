# Conjunto de datos del clasificador (S4-11)

Ejemplos de solicitudes de soporte, redactados por el equipo con el vocabulario del DTIC y
etiquetados con **categoría**, **urgencia** e **impacto** (HU-02.1). Alimentan el clasificador
de reglas y modelo (S4-12) y su entrenamiento posterior. Como no existe un registro histórico
de incidencias (riesgo RT-01), los ejemplos son redactados por el equipo y balanceados por
categoría.

## Contenido

| Ruta | Qué es |
|---|---|
| `ml/etl/ejemplos_equipo.py` | Los ejemplos escritos a mano (fuente de verdad). |
| `ml/etl/build_dataset.py` | Valida los ejemplos y genera el CSV. |
| `ml/data/dataset_v1.csv` | Conjunto de datos generado: **120 ejemplos, 30 por categoría**. |

Columnas del CSV: `id`, `text`, `category`, `urgency`, `impact`, `source`.

## Cómo regenerarlo

Desde la raíz del repositorio (solo usa la biblioteca estándar de Python):

```bash
python -m ml.etl.build_dataset
```

No edites el CSV a mano: cambia `ejemplos_equipo.py` y vuelve a generarlo. Una prueba
(`backend/tests/test_dataset_clasificador.py`) falla si el CSV no coincide con los ejemplos.

## Criterio de etiquetado

La **prioridad** (P1 a P4) no se etiqueta: se calcula con la matriz urgencia-impacto (RN-05,
`backend/app/domain/priority.py`). El clasificador solo propone categoría, urgencia e impacto.

**Urgencia** — qué tan pronto hay que atenderla:

| Nivel | Cuándo |
|---|---|
| 3 | No se puede trabajar o dar clase ahora, o hay un plazo de horas (examen, cierre de actas, evento). |
| 2 | El trabajo sigue, pero degradado o con una solución provisional; el plazo es de días. |
| 1 | Molestia o mejora sin plazo; puede esperar. |

**Impacto** — a cuántas personas o servicios afecta:

| Nivel | Cuándo |
|---|---|
| 3 | Muchas personas o un servicio general: un edificio, toda la facultad, una plataforma. |
| 2 | Un grupo u oficina: un laboratorio, un aula, un área de trabajo. |
| 1 | Una sola persona. |

## Cómo agregar ejemplos

1. Añade una línea `categoría | urgencia | impacto | texto` en `ejemplos_equipo.py`.
2. Mantén las categorías balanceadas: el script avisa si una tiene más ejemplos que otra.
3. Redacta como lo haría quien registra la solicitud (mínimo 30 caracteres, sin repetir
   textos) y regenera el CSV.