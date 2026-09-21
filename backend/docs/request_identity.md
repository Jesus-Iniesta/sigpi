
REQUEST IDENTITY 
Descripción: La entidad solicitud (request) debe contener las siguientes características. 

NOTA: Están escritas como sería su declaración en SQL. Ello sirve para aclarar los campos necesarios 

--AQUÍ TENEMOS EL PRIMER MODELO, 
el modelo principal que contiene la información básica y es el núcleo del sistema. 
    quién la pidió (requester_id), a qué categoría pertenece, qué activo está involucrado, el nivel de servicio, folio, título, descripción, ubicación física, canal de entrada, estado, prioridad, urgencia, impacto, fechas clave (creación, resolución, cierre).


CREATE TABLE service_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), --ESTO SE HACE CON PYTHON
    requester_id UUID NOT NULL REFERENCES users(id),
    category_id UUID REFERENCES categories(id),
    asset_id UUID REFERENCES assets(id),
    service_level_version_id UUID REFERENCES service_level_versions(id),
    related_request_id UUID REFERENCES service_requests(id),
    folio VARCHAR(40) UNIQUE,
    title VARCHAR(180) NOT NULL,
    description TEXT NOT NULL,
    physical_location VARCHAR(240) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(30) DEFAULT 'REGISTERED',
    priority VARCHAR(2),
    urgency INTEGER,
    impact INTEGER,
    classification_confidence FLOAT,
    first_response_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

--AQUÍ ESTÁ EL HISTORIAL DE CAMBIO
Sirve como bitácora para auditar el ciclo de vida de la solicitud.
    Guarda quién hizo la acción (author_id), qué estado tenía antes y después, qué acción se realizó y notas adicionales.


CREATE TABLE request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES service_requests(id),
    author_id UUID NOT NULL REFERENCES users(id),
    previous_status VARCHAR(30),
    new_status VARCHAR(30),
    action VARCHAR(120) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);


--ESTA OTRA FORMA DE LA ASIGNACIÓN DE LA SOLICITUD A UN TÉCNICO
    Incluye quién fue asignado (technician_id), si fue automático o manual, cuándo se asignó y cuándo se desasignó.
    También guarda un puntaje y desglose de cómo se decidió la asignación.

CREATE TABLE request_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES service_requests(id),
    technician_id UUID NOT NULL REFERENCES users(id),
    score FLOAT,
    score_breakdown TEXT,
    is_automatic BOOLEAN DEFAULT TRUE,
    assigned_at TIMESTAMPTZ DEFAULT now(),
    unassigned_at TIMESTAMPTZ
);

--POR ÚLTIMO, EL ESCALAMIENTO DE LA SOLICITUD CUANDO REQUIERE DE ATENCIÓN DE MAYOR NIVEL,
    Contiene quién la pidió, quién la aprobó, el tipo de escalación, su estado, evidencia y justificación.
    Guarda las fechas de creación y resolución de la escalación.

CREATE TABLE request_escalations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES service_requests(id),
    requested_by_id UUID NOT NULL REFERENCES users(id),
    approved_by_id UUID REFERENCES users(id),
    escalation_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'REQUESTED',
    evidence TEXT NOT NULL,
    justification TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);


Entregado por: Laura