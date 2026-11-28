"""Prueba de aceptación del flujo completo de una solicitud (S5-25, Kanban S5-22).

Recorre la solicitud de punta a punta solo por la API HTTP. Sirve de guion para la sesión
de aceptación con el DTIC-FI (HU-01.1, HU-02.1, HU-03.1, HU-04.1 y HU-04.2).

Escenario A. Camino feliz (el clasificador está seguro, 90 %)
  1. La persona solicitante registra su solicitud y recibe un folio.
  2. El sistema la clasifica sola (categoría, urgencia, impacto y prioridad) y, por ser
     crítica, la asigna al técnico que tiene la especialidad.
  3. El técnico la ve en su bandeja.
  4. El técnico inicia la atención: queda «En proceso» y se anota la primera respuesta.
  5. El técnico registra su diagnóstico.
  6. El técnico la pone «En espera» (falta un insumo externo) y la reanuda una hora
     después: esa hora no cuenta contra el acuerdo de servicio.
  7. El técnico la resuelve: el tiempo de resolución no incluye la espera.
  8. La persona solicitante confirma que la solución funcionó y la solicitud se cierra.
  9. La bitácora muestra, en orden y con su autor, el alta, la clasificación, la
     asignación, el inicio, el diagnóstico, la espera, la reanudación, la resolución y el
     cierre. (Hoy el alta por el portal no deja entrada propia: se ve como el estado
     previo, «Registrada», de la clasificación; ver issue #110.)
 10. La persona solicitante recibió los avisos de alta, resolución y cierre.

Escenario B. Revisión manual (el clasificador duda, 60 %)
  1. La solicitud queda «Por revisar» y aparece en la cola de revisión.
  2. La Jefa del Departamento corrige la clasificación, con justificación, y la solicitud
     sale de la cola.
  3. La Jefa la asigna a un técnico, que la atiende y la resuelve; el técnico la cierra
     en nombre de la persona solicitante.

Escenario C. Permisos
  La persona solicitante no puede iniciar, resolver ni asignar su propia solicitud.
"""

from datetime import datetime

TEXTO = {
    "title": "No hay internet en el laboratorio",
    "description": "El wifi del edificio A no tiene conexión desde la mañana",
    "physical_location": "Edificio A, laboratorio 2",
}


def _fecha(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


def _alta(cliente) -> dict:
    respuesta = cliente.como("solicitante").post(
        "/solicitudes", json={"requester_id": str(cliente.ids["solicitante"]), **TEXTO}
    )
    assert respuesta.status_code == 201, respuesta.text
    solicitud = respuesta.json()
    assert solicitud["folio"].startswith("SIG-")
    return solicitud


def _detalle(cliente, request_id: str) -> dict:
    respuesta = cliente.como("tecnico").get(f"/solicitudes/{request_id}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _post(cliente, persona: str, ruta: str, cuerpo: dict | None = None, esperado: int = 200):
    respuesta = cliente.como(persona).post(ruta, json=cuerpo)
    assert respuesta.status_code == esperado, respuesta.text
    return respuesta.json()


# ------------------------------------------------------- Escenario A: camino feliz


def test_escenario_a_camino_feliz_de_punta_a_punta(cliente):
    ids = cliente.ids
    reloj = cliente.reloj

    # 1. Alta con folio.
    solicitud = _alta(cliente)
    request_id, folio = solicitud["id"], solicitud["folio"]

    # 2. Clasificada (categoría, urgencia, impacto y prioridad) y asignada automáticamente
    #    al técnico con la especialidad de Redes.
    assert solicitud["category_id"] == str(ids["Redes"])
    assert (solicitud["urgency"], solicitud["impact"], solicitud["priority"]) == (3, 3, "P1")
    assert solicitud["classification_confidence"] == 0.90
    assert solicitud["status"] == "assigned"
    asignacion = cliente.como("jefe").get(f"/asignaciones/{request_id}")
    assert asignacion.status_code == 200, asignacion.text
    assert asignacion.json()["technician_id"] == str(ids["tecnico"])
    assert asignacion.json()["is_automatic"] is True

    # 3. El técnico la ve en su bandeja; el otro técnico no.
    bandeja = cliente.como("tecnico").get("/bandeja")
    assert bandeja.status_code == 200, bandeja.text
    assert [(e["folio"], e["estatus"]) for e in bandeja.json()] == [(folio, "assigned")]
    ajena = cliente.como("otro_tecnico").get("/bandeja")
    assert ajena.status_code == 200, ajena.text
    assert ajena.json() == []

    # 4. Iniciar: «En proceso» y primera respuesta anotada.
    reloj.avanzar(10)
    iniciada = _post(cliente, "tecnico", f"/solicitudes/{request_id}/iniciar")
    assert iniciada["status"] == "in_progress"
    assert iniciada["first_response_at"] is not None

    # 5. Diagnóstico.
    reloj.avanzar(5)
    diagnosticada = _post(
        cliente,
        "tecnico",
        f"/solicitudes/{request_id}/diagnostico",
        {"diagnosis": "El punto de acceso del edificio A está apagado."},
    )
    assert diagnosticada["status"] == "in_progress"
    assert diagnosticada["diagnosis"] == "El punto de acceso del edificio A está apagado."

    # 6. Espera de 60 minutos que no cuenta contra el acuerdo.
    reloj.avanzar(5)
    en_espera = _post(
        cliente,
        "tecnico",
        f"/solicitudes/{request_id}/espera",
        {"reason": "external_input", "detail": "Falta la fuente de poder del AP."},
    )
    assert en_espera["status"] == "waiting"
    reloj.avanzar(60)
    reanudada = _post(cliente, "tecnico", f"/solicitudes/{request_id}/reanudar")
    assert reanudada["status"] == "in_progress"

    # 7. Resolver: 10 + 5 + 5 + 20 = 40 minutos efectivos; la hora en espera no cuenta.
    reloj.avanzar(20)
    resuelta = _post(
        cliente,
        "tecnico",
        f"/solicitudes/{request_id}/resolver",
        {"solution": "Se cambió la fuente de poder y se reinició el AP."},
    )
    assert resuelta["status"] == "resolved"
    assert resuelta["resolution_minutes"] == 40
    transcurridos = _fecha(resuelta["resolved_at"]) - _fecha(resuelta["created_at"])
    assert round(transcurridos.total_seconds() / 60) == 100

    # 8. La persona solicitante confirma y la solicitud se cierra.
    cerrada = _post(cliente, "solicitante", f"/mis-solicitudes/{folio}/confirmar")
    assert cerrada["status"] == "closed"
    assert _detalle(cliente, request_id)["status"] == "closed"

    # 9. Bitácora en orden, cada entrada con su autor.
    bitacora = cliente.como("tecnico").get(f"/solicitudes/{request_id}/bitacora")
    assert bitacora.status_code == 200, bitacora.text
    #    El alta por el portal aún no escribe su propia entrada (el registro asistido sí):
    #    queda registrada como el estado previo («registered») de la clasificación (#110).
    solicitante, tecnico = str(ids["solicitante"]), str(ids["tecnico"])
    entradas = [
        (e["action"], e["author_id"], e["previous_status"], e["new_status"])
        for e in bitacora.json()
    ]
    assert entradas == [
        ("Clasificación automática", solicitante, "registered", "classified"),
        ("Asignación automática", solicitante, "classified", "assigned"),
        ("Atención iniciada", tecnico, "assigned", "in_progress"),
        ("Diagnóstico registrado", tecnico, "in_progress", "in_progress"),
        ("Reloj del SLA suspendido", tecnico, "in_progress", "waiting"),
        ("Reloj del SLA reanudado", tecnico, "waiting", "in_progress"),
        ("Solicitud resuelta", tecnico, "in_progress", "resolved"),
        ("Solicitud confirmada", solicitante, "resolved", "closed"),
    ]

    # 10. Avisos de alta, resolución y cierre en la bandeja de la persona solicitante.
    avisos = cliente.como("solicitante").get("/notificaciones")
    assert avisos.status_code == 200, avisos.text
    asuntos = [a["subject"] for a in avisos.json()]
    for asunto in (f"{folio} registrada", f"{folio} resuelta", f"{folio} cerrada"):
        assert any(asunto in a for a in asuntos), f"falta el aviso «{asunto}» en {asuntos}"


# ---------------------------------------------------- Escenario B: revisión manual


def test_escenario_b_revision_manual_y_cierre_por_el_tecnico(cliente):
    ids = cliente.ids
    cliente.usar(0.60)

    # 1. Por revisar, sin técnico, y en la cola de revisión.
    solicitud = _alta(cliente)
    request_id = solicitud["id"]
    assert solicitud["status"] == "pending_review"
    assert solicitud["priority"] is None
    sin_tecnico = cliente.como("jefe").get(f"/asignaciones/{request_id}")
    assert sin_tecnico.status_code == 200, sin_tecnico.text
    assert sin_tecnico.json() is None
    cola = cliente.como("jefe").get("/revision/cola")
    assert cola.status_code == 200, cola.text
    pendientes = [r for r in cola.json() if r["request_id"] == request_id]
    assert len(pendientes) == 1
    assert pendientes[0]["confidence"] == 0.60

    # 2. La Jefa corrige con justificación; la solicitud sale de la cola.
    corregida = _post(
        cliente,
        "jefe",
        f"/revision/{pendientes[0]['result_id']}/correccion",
        {
            "category_id": str(ids["Redes"]),
            "urgency": 2,
            "impact": 2,
            "justification": "Afecta solo a un laboratorio; no es una caída general.",
        },
    )
    assert corregida == {"request_id": request_id, "status": "classified", "priority": "P2"}
    cola = cliente.como("jefe").get("/revision/cola")
    assert cola.status_code == 200, cola.text
    assert all(r["request_id"] != request_id for r in cola.json())

    # 3. La Jefa asigna; el técnico atiende, resuelve y cierra en nombre del solicitante.
    asignada = _post(
        cliente, "jefe", f"/asignaciones/{request_id}", {"technician_id": str(ids["tecnico"])}
    )
    assert asignada["technician_id"] == str(ids["tecnico"])
    assert asignada["is_automatic"] is False
    assert asignada["request_status"] == "assigned"

    iniciada = _post(cliente, "tecnico", f"/solicitudes/{request_id}/iniciar")
    assert iniciada["status"] == "in_progress"
    resuelta = _post(
        cliente,
        "tecnico",
        f"/solicitudes/{request_id}/resolver",
        {"solution": "Se reconfiguró el AP del laboratorio.", "diagnosis": "AP sin DHCP."},
    )
    assert resuelta["status"] == "resolved"
    cerrada = _post(
        cliente,
        "tecnico",
        f"/solicitudes/{request_id}/confirmar",
        {"notes": "El solicitante confirmó por teléfono."},
    )
    assert cerrada["status"] == "closed"
    assert cerrada["closed_at"] is not None

    bitacora = cliente.como("tecnico").get(f"/solicitudes/{request_id}/bitacora")
    assert bitacora.status_code == 200, bitacora.text
    jefe, tecnico = str(ids["jefe"]), str(ids["tecnico"])
    assert [(e["action"], e["author_id"], e["new_status"]) for e in bitacora.json()] == [
        ("Clasificación automática", str(ids["solicitante"]), "pending_review"),
        ("Clasificación corregida", jefe, "classified"),
        ("Técnico asignado", jefe, "assigned"),
        ("Atención iniciada", tecnico, "in_progress"),
        ("Solicitud resuelta", tecnico, "resolved"),
        ("Solicitud confirmada", tecnico, "closed"),
    ]


# ----------------------------------------------------------- Escenario C: permisos


def test_escenario_c_el_solicitante_no_atiende_ni_asigna_su_solicitud(cliente):
    cliente.usar(0.60)  # sin asignación automática: la solicitud queda sin técnico
    solicitud = _alta(cliente)
    request_id = solicitud["id"]
    solicitante = cliente.como("solicitante")

    iniciar = solicitante.post(f"/solicitudes/{request_id}/iniciar")
    assert iniciar.status_code == 403, iniciar.text
    resolver = solicitante.post(
        f"/solicitudes/{request_id}/resolver", json={"solution": "Ya funciona."}
    )
    assert resolver.status_code == 403, resolver.text
    asignar = solicitante.post(
        f"/asignaciones/{request_id}", json={"technician_id": str(cliente.ids["tecnico"])}
    )
    assert asignar.status_code == 403, asignar.text

    # Nada cambió: sigue «Por revisar» y sin técnico.
    assert _detalle(cliente, request_id)["status"] == "pending_review"
    vigente = cliente.como("jefe").get(f"/asignaciones/{request_id}")
    assert vigente.status_code == 200, vigente.text
    assert vigente.json() is None
