"""Clasificador de solicitudes de soporte (S4-12, HU-02.1).

Propone categoría, urgencia e impacto a partir del texto de una solicitud. Está escrito
en Python puro, sin bibliotecas de aprendizaje automático, para que funcione igual en
Docker, en CI y con Python 3.14.

Hay tres implementaciones del protocolo `Clasificador`:

* `ClasificadorReglas` (`reglas-v1`): palabras clave por categoría y señales de urgencia
  e impacto. No necesita datos de entrenamiento.
* `ClasificadorBayes` (`nb-v1`): Naive Bayes multinomial entrenado con
  `ml/data/dataset_v1.csv` al construirse.
* `ClasificadorCompuesto`: usa el modelo y, si el CSV no existe o falla, cae a reglas.
"""

import csv
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger, log_event
from app.models.enums import ClassificationSource

logger = get_logger("clasificacion")

VERSION_REGLAS = "reglas-v1"
VERSION_BAYES = "nb-v1"

CATEGORIAS: tuple[str, ...] = ("Hardware", "Software", "Redes", "Cuentas y accesos")
NIVELES: tuple[int, ...] = (1, 2, 3)

# Raíz del repositorio: backend/app/integrations/clasificador_client.py -> parents[3].
RAIZ_REPO = Path(__file__).resolve().parents[3]

# Palabras vacías del español (ya sin acentos), que no ayudan a distinguir categorías.
_TEXTO_PALABRAS_VACIAS = """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque cada
    como con contra cual cuales cuando de del desde donde dos e el ella ellas ellos en
    entre era eran es esa esas ese eso esos esta estan estas este esto estos fue fueron
    ha han hasta hay la las le les lo los mas me mi mis mucho muy nos nuestra nuestro
    o otra otras otro otros para pero poco por porque que quien se sea ser si sin sobre
    son su sus tambien te tiene tienen todo tu tus un una unas uno unos y ya yo
"""
PALABRAS_VACIAS: frozenset[str] = frozenset(_TEXTO_PALABRAS_VACIAS.split())


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos («Contraseña» -> «contrasena»)."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def tokenizar(texto: str) -> list[str]:
    """Palabras normalizadas de al menos dos letras, sin palabras vacías."""
    return [
        t
        for t in re.findall(r"[a-z0-9]+", normalizar(texto))
        if len(t) > 1 and t not in PALABRAS_VACIAS
    ]


@dataclass(frozen=True)
class Prediccion:
    categoria: str
    urgencia: int
    impacto: int
    confianza: float  # entre 0 y 1
    fuente: ClassificationSource
    version: str


@dataclass(frozen=True)
class Ejemplo:
    texto: str
    categoria: str
    urgencia: int
    impacto: int


class Clasificador(Protocol):
    version: str
    fuente: ClassificationSource
    # Exactitud de la categoría con validación cruzada; `None` si no se midió.
    exactitud: float | None
    artefacto: str | None
    entrenado_en: datetime

    def predecir(self, texto: str) -> Prediccion: ...


# --- reglas ----------------------------------------------------------------

# Frases normalizadas. Una frase coincide si aparece al inicio de una palabra del texto,
# así «impresor» cubre «impresora» e «impresoras».
_PALABRAS_CATEGORIA: dict[str, tuple[str, ...]] = {
    "Hardware": (
        "computadora",
        "equipo",
        "monitor",
        "pantalla",
        "teclado",
        "mouse",
        "raton",
        "impresor",
        "proyector",
        "bocina",
        "cable hdmi",
        "hdmi",
        "no enciende",
        "no prende",
        "se apag",
        "bateria",
        "cargador",
        "disco duro",
        "memoria ram",
        "ventilador",
        "zumbido",
        "quemado",
        "toner",
        "escaner",
        "camara",
        "microfono",
        "cpu",
        "laptop",
        "no da imagen",
        "pizarron",
        "nobreak",
        "regulador",
    ),
    "Software": (
        "programa",
        "aplicacion",
        "sistema operativo",
        "windows",
        "office",
        "word",
        "excel",
        "powerpoint",
        "instal",
        "actualiz",
        "licencia",
        "antivirus",
        "software",
        "version",
        "navegador",
        "se cierra",
        "se traba",
        "error al abrir",
        "plataforma",
        "moodle",
        "matlab",
        "autocad",
        "compatible",
        "macro",
        "pdf",
        "virus",
    ),
    "Redes": (
        "internet",
        "red",
        "wifi",
        "wi fi",
        "inalambric",
        "conexion",
        "conectividad",
        "router",
        "modem",
        "switch",
        "access point",
        "ip",
        "dns",
        "nodo",
        "ethernet",
        "velocidad",
        "lento para cargar",
        "senal",
        "vpn",
        "puerto de red",
        "sin conexion",
    ),
    "Cuentas y accesos": (
        "contrasena",
        "cuenta",
        "usuario",
        "acceso",
        "permiso",
        "iniciar sesion",
        "inicio de sesion",
        "sesion",
        "bloquead",
        "correo institucional",
        "credencial",
        "autentic",
        "rol",
        "alta",
        "baja de",
        "restablecer",
        "recuperar",
        "directorio",
        "no me deja entrar",
        "perfil",
    ),
}

# Señales de urgencia. Se revisan primero las de urgencia baja porque «no es urgente»
# contiene «urgente».
_URGENCIA_BAJA: tuple[str, ...] = (
    "no es urgente",
    "sin prisa",
    "no tengo prisa",
    "cuando puedan",
    "curiosidad",
    "preferencia",
    "sugerencia",
    "mejora",
    "ojala",
    "proximo semestre",
    "si se puede",
)
_URGENCIA_ALTA: tuple[str, ...] = (
    "no enciende",
    "no prende",
    "examen",
    "evaluacion",
    "hoy",
    "urgente",
    "ahora",
    "de inmediato",
    "no puedo trabajar",
    "no puedo dar clase",
    "cierre de actas",
    "se apag",
    "quemado",
    "caid",
    "ningun",
    "no funciona",
    "ultimo dia",
    "ya para",
    "en este momento",
)
_IMPACTO_ALTO: tuple[str, ...] = (
    "toda la facultad",
    "todo el edificio",
    "todos los usuarios",
    "todos los alumnos",
    "toda la red",
    "todo el campus",
    "todas las aulas",
    "todos los laboratorios",
    "toda la comunidad",
    "general",
    "institucional",
    "plataforma",
    "todos los profesores",
)
_IMPACTO_MEDIO: tuple[str, ...] = (
    "todo el laboratorio",
    "laboratorio",
    "aula",
    "salon",
    "oficina",
    "grupo",
    "area",
    "departamento",
    "coordinacion",
    "cubiculos",
    "docentes",
    "profesores",
    "alumnos",
    "biblioteca",
    "sala",
)


def _texto_buscable(texto: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", normalizar(texto))) + " "


def _coincide(buscable: str, frase: str) -> bool:
    return f" {normalizar(frase)}" in buscable


def _contar(buscable: str, frases: Iterable[str]) -> int:
    return sum(1 for frase in frases if _coincide(buscable, frase))


def urgencia_por_reglas(texto: str) -> int:
    buscable = _texto_buscable(texto)
    if _contar(buscable, _URGENCIA_BAJA):
        return 1
    if _contar(buscable, _URGENCIA_ALTA):
        return 3
    return 2


def impacto_por_reglas(texto: str) -> int:
    buscable = _texto_buscable(texto)
    if _contar(buscable, _IMPACTO_ALTO):
        return 3
    if _contar(buscable, _IMPACTO_MEDIO):
        return 2
    return 1


class ClasificadorReglas:
    """Palabras clave por categoría y señales de urgencia e impacto (`reglas-v1`)."""

    version = VERSION_REGLAS
    fuente = ClassificationSource.RULES
    exactitud: float | None = None
    artefacto: str | None = None

    def __init__(self) -> None:
        self.entrenado_en = datetime.now(UTC)

    def predecir(self, texto: str) -> Prediccion:
        buscable = _texto_buscable(texto)
        aciertos = {c: _contar(buscable, _PALABRAS_CATEGORIA[c]) for c in CATEGORIAS}
        # Con empate gana la primera categoría de `CATEGORIAS`.
        categoria = max(CATEGORIAS, key=lambda c: aciertos[c])
        total = sum(aciertos.values())
        # Suavizado de Laplace: sin coincidencias la confianza es 1/4.
        confianza = (aciertos[categoria] + 1) / (total + len(CATEGORIAS))
        return Prediccion(
            categoria=categoria,
            urgencia=urgencia_por_reglas(texto),
            impacto=impacto_por_reglas(texto),
            confianza=confianza,
            fuente=self.fuente,
            version=self.version,
        )


# --- Naive Bayes multinomial -------------------------------------------------


class _NaiveBayes:
    """Naive Bayes multinomial con suavizado de Laplace sobre bolsas de palabras."""

    def __init__(self, documentos: Sequence[list[str]], etiquetas: Sequence[object]) -> None:
        if not documentos or len(documentos) != len(etiquetas):
            raise ValueError("Se necesita al menos un ejemplo etiquetado para entrenar.")
        self.clases = sorted(set(etiquetas), key=str)
        por_clase = Counter(etiquetas)
        self._log_prior = {c: math.log(por_clase[c] / len(etiquetas)) for c in self.clases}
        conteos: dict[object, Counter[str]] = {c: Counter() for c in self.clases}
        for tokens, etiqueta in zip(documentos, etiquetas, strict=True):
            conteos[etiqueta].update(tokens)
        self._vocabulario = {t for c in conteos.values() for t in c}
        tamano = len(self._vocabulario)
        self._log_verosimilitud: dict[object, dict[str, float]] = {}
        self._log_desconocida: dict[object, float] = {}
        for c in self.clases:
            denominador = sum(conteos[c].values()) + tamano
            self._log_verosimilitud[c] = {
                t: math.log((n + 1) / denominador) for t, n in conteos[c].items()
            }
            self._log_desconocida[c] = math.log(1 / denominador)

    def posteriores(self, tokens: Iterable[str]) -> dict[object, float]:
        conocidas = [t for t in tokens if t in self._vocabulario]
        puntajes = {}
        for c in self.clases:
            tabla = self._log_verosimilitud[c]
            puntajes[c] = self._log_prior[c] + sum(
                tabla.get(t, self._log_desconocida[c]) for t in conocidas
            )
        maximo = max(puntajes.values())
        exp = {c: math.exp(p - maximo) for c, p in puntajes.items()}
        total = sum(exp.values())
        return {c: v / total for c, v in exp.items()}

    def predecir(self, tokens: Iterable[str]) -> tuple[object, float]:
        posteriores = self.posteriores(tokens)
        clase = max(self.clases, key=lambda c: posteriores[c])
        return clase, posteriores[clase]


def cargar_ejemplos(ruta: Path) -> list[Ejemplo]:
    """Lee el CSV etiquetado (columnas `text`, `category`, `urgency`, `impact`)."""
    with ruta.open(encoding="utf-8", newline="") as archivo:
        ejemplos = [
            Ejemplo(
                texto=fila["text"],
                categoria=fila["category"],
                urgencia=int(fila["urgency"]),
                impacto=int(fila["impact"]),
            )
            for fila in csv.DictReader(archivo)
        ]
    if not ejemplos:
        raise ValueError(f"El conjunto de datos {ruta} está vacío.")
    return ejemplos


class ClasificadorBayes:
    """Naive Bayes multinomial entrenado con el conjunto de datos (`nb-v1`).

    Entrena un modelo para cada etiqueta del CSV (categoría, urgencia e impacto) con la
    misma bolsa de palabras. La confianza es la probabilidad posterior de la categoría
    elegida.
    """

    version = VERSION_BAYES
    fuente = ClassificationSource.MODEL

    def __init__(
        self,
        ejemplos: Sequence[Ejemplo],
        *,
        artefacto: str | None = None,
        medir_exactitud: bool = True,
    ) -> None:
        documentos = [tokenizar(e.texto) for e in ejemplos]
        self._categoria = _NaiveBayes(documentos, [e.categoria for e in ejemplos])
        self._urgencia = _NaiveBayes(documentos, [e.urgencia for e in ejemplos])
        self._impacto = _NaiveBayes(documentos, [e.impacto for e in ejemplos])
        self.artefacto = artefacto
        self.entrenado_en = datetime.now(UTC)
        self.exactitud: float | None = (
            validacion_cruzada(ejemplos)["categoria"] if medir_exactitud else None
        )

    @classmethod
    def desde_csv(cls, ruta: Path, *, artefacto: str | None = None) -> "ClasificadorBayes":
        return cls(cargar_ejemplos(ruta), artefacto=artefacto)

    def predecir(self, texto: str) -> Prediccion:
        tokens = tokenizar(texto)
        categoria, confianza = self._categoria.predecir(tokens)
        urgencia, _ = self._urgencia.predecir(tokens)
        impacto, _ = self._impacto.predecir(tokens)
        return Prediccion(
            categoria=str(categoria),
            urgencia=int(str(urgencia)),
            impacto=int(str(impacto)),
            confianza=confianza,
            fuente=self.fuente,
            version=self.version,
        )


def particiones(ejemplos: Sequence[Ejemplo], k: int = 5) -> list[list[int]]:
    """Índices de `k` partes estratificadas por categoría y deterministas.

    Dentro de cada categoría, el i-ésimo ejemplo va a la parte `i % k`, así cada parte
    conserva la proporción de categorías y el resultado no depende del azar.
    """
    partes: list[list[int]] = [[] for _ in range(k)]
    vistos: Counter[str] = Counter()
    for indice, ejemplo in enumerate(ejemplos):
        partes[vistos[ejemplo.categoria] % k].append(indice)
        vistos[ejemplo.categoria] += 1
    return partes


def validacion_cruzada(ejemplos: Sequence[Ejemplo], k: int = 5) -> dict[str, float]:
    """Exactitud media del modelo con validación cruzada de `k` partes.

    Devuelve la exactitud de categoría, urgencia e impacto. `ModelVersion.accuracy`
    guarda la de categoría.
    """
    aciertos = Counter[str]()
    total = 0
    for prueba in particiones(ejemplos, k):
        fuera = set(prueba)
        entrenamiento = [e for i, e in enumerate(ejemplos) if i not in fuera]
        modelo = ClasificadorBayes(entrenamiento, medir_exactitud=False)
        for i in prueba:
            ejemplo = ejemplos[i]
            prediccion = modelo.predecir(ejemplo.texto)
            aciertos["categoria"] += prediccion.categoria == ejemplo.categoria
            aciertos["urgencia"] += prediccion.urgencia == ejemplo.urgencia
            aciertos["impacto"] += prediccion.impacto == ejemplo.impacto
            total += 1
    return {campo: aciertos[campo] / total for campo in ("categoria", "urgencia", "impacto")}


# --- compuesto -------------------------------------------------------------


class ClasificadorCompuesto:
    """Usa el modelo y, si el CSV no existe o falla, cae a reglas."""

    def __init__(self, ruta_dataset: Path) -> None:
        self._reglas = ClasificadorReglas()
        self._modelo: ClasificadorBayes | None = None
        try:
            self._modelo = ClasificadorBayes.desde_csv(
                ruta_dataset, artefacto=settings.classifier_dataset_path
            )
        except (OSError, ValueError, KeyError, csv.Error) as exc:
            log_event(
                logger,
                "clasificador.modelo_no_disponible",
                ruta=str(ruta_dataset),
                error=type(exc).__name__,
            )

    @property
    def _activo(self) -> Clasificador:
        return self._modelo if self._modelo is not None else self._reglas

    @property
    def version(self) -> str:
        return self._activo.version

    @property
    def fuente(self) -> ClassificationSource:
        return self._activo.fuente

    @property
    def exactitud(self) -> float | None:
        return self._activo.exactitud

    @property
    def artefacto(self) -> str | None:
        return self._activo.artefacto

    @property
    def entrenado_en(self) -> datetime:
        return self._activo.entrenado_en

    def predecir(self, texto: str) -> Prediccion:
        if self._modelo is not None:
            try:
                return self._modelo.predecir(texto)
            except Exception as exc:  # noqa: BLE001 - cualquier falla del modelo cae a reglas
                log_event(logger, "clasificador.prediccion_fallida", error=type(exc).__name__)
        return self._reglas.predecir(texto)


def ruta_dataset() -> Path:
    """Ruta absoluta del CSV configurado en `classifier_dataset_path`."""
    ruta = Path(settings.classifier_dataset_path)
    return ruta if ruta.is_absolute() else RAIZ_REPO / ruta


@lru_cache(maxsize=1)
def obtener_clasificador() -> ClasificadorCompuesto:
    """Clasificador compartido: se entrena una sola vez por proceso."""
    return ClasificadorCompuesto(ruta_dataset())
