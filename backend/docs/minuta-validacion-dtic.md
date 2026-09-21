# Minuta de reunión — Validación de historias y prioridades (S1-13)

**Estado:** Realizada
**Fecha:** 7 de septiembre de 2026
**Modalidad:** Presencial
**Asistentes:** 
- Mtro. Silvia Edith Albarran Trujillo
- Haide Sánchez Gutiérrez (Product Owner / Equipo de desarrollo)
- Laura Valeria Rodríguez Morales (Equipo de desarrollo)
- Jesús Iniesta Valverde (Equipo de desarrollo)
- Emmanuel Bernal Espejel (Scrum Master / Equipo de desarrollo)

**Objetivo:** Validar el alcance, las prioridades y las restricciones documentadas
en el Product Backlog v1, como mitigación del riesgo RR-01 (disponibilidad
limitada del personal del Departamento para las sesiones de levantamiento
y validación de requisitos)

## Guía de temas a tratar
1. Revisión de las historias de usuario priorizadas como "Debe" para la primera
   entrega (registro de solicitudes, clasificación, asignación, SLA, notificaciones).
2. Confirmación de que la matriz de prioridades (urgencia-impacto) y los acuerdos
   de nivel de servicio propuestos (P1–P4) reflejan la operación real del
   Departamento, o si requieren ajuste.
3. Restricciones operativas que el Jefe del Departamento señale y que no
   estén documentadas todavía (horarios, personal disponible, herramientas
   actuales, etc.).
4. Confirmación de los actores y roles identificados (Usuario solicitante,
   Técnico Nivel 1, Técnico Nivel 2, Jefe del Departamento).

## Acuerdos
1. **Validación del Alcance (Historias "Debe"):** Se aprueban las 18 historias de usuario clasificadas con prioridad "Debe" para la primera entrega funcional del sistema (Sprint 1 a Sprint 5).
2. **Matriz de Prioridades y SLA:**
   - Se ratifica la matriz de priorización basada en Urgencia e Impacto (regla RN-05).
   - Se aprueban los tiempos comprometidos de atención para los cuatro niveles (P1 a P4):
     - **P1 - Crítica:** 15 min primera respuesta / 4 h resolución.
     - **P2 - Alta:** 1 h primera respuesta / 8 h resolución.
     - **P3 - Media:** 4 h primera respuesta / 24 h resolución.
     - **P4 - Baja:** 8 h primera respuesta / 72 h resolución.
3. **Carga Máxima de Técnicos:** Se aprueba fijar un límite operativo de 5 tickets activos simultáneos por técnico de soporte (Nivel 1 y Nivel 2). En incidentes de prioridad P1-Crítica, el motor podrá omitir temporalmente este límite para asignar la atención inmediata.
4. **Criterios de Supervisión de IA:** Se valida que cualquier predicción del clasificador con una confianza menor a 0.75 no se asigne de forma directa, sino que pase a la cola de revisión de la Mesa de Servicio para validación humana (regla RN-06).
5. **Horarios de Cómputo del SLA:** El reloj del SLA solo computará dentro del horario hábil de la Facultad de Ingeniería (lunes a viernes de 7:00 a 21:00 h).

## Observaciones o correcciones al Product Backlog
- **Sincronización con Directorio Institucional:** El Jefe del Departamento enfatizó que la autenticación debe realizarse exclusivamente a través del directorio institucional (Microsoft 365) para garantizar la vigencia de las cuentas de alumnos y profesores.
- **Mantenimiento Preventivo:** Se acordó que las rutinas preventivas en salas de cómputo y laboratorios se programarán fuera de horarios de clase regular o durante periodos intersemestrales, enviando alertas previas al responsable de la sala.

## Pendientes para el siguiente sprint
- Implementar el mecanismo de suspensión y reanudación del reloj del SLA cuando el ticket pase al estado *En espera* por insumo externo o falta de información del usuario (HU-04.2).
- Preparar los conjuntos de prueba y reglas iniciales para el clasificador automático de incidentes.

## Próxima sesión de validación
**Fecha propuesta:** 21 de septiembre de 2026 (Cierre de Sprint 2 - Elaboración).
