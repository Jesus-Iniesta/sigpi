import type { AsignacionVigente } from '@/api/asignaciones'
import { useAuth } from '@/features/auth/auth-context'
import { puedeAsignar } from '@/features/requests/assign-roles'
import { PuntajeDesglose } from '@/features/requests/components/PuntajeDesglose'
import { formatDateTime } from '@/features/requests/request-labels'
import { useAsignacionVigente } from '@/features/requests/use-asignacion-vigente'
import { ErrorAlert } from '@/shared/ui/error-alert'

/** «Asignación manual · 25 nov 2026, 10:00». */
function resumenAsignacion(asignacion: AsignacionVigente): string {
    const origen = asignacion.is_automatic
        ? 'Asignación automática'
        : 'Asignación manual'
    return `${origen} · ${formatDateTime(asignacion.assigned_at)}`
}

type TecnicoAsignadoDesgloseProps = {
    requestId: string
}

/**
 * Muestra quién tiene asignada la solicitud y por qué se le eligió: el desglose
 * de su puntaje (S5-12, HU-03.1). Solo se ofrece a quien tiene
 * `requests.assign`, igual que el endpoint que lo alimenta.
 */
export function TecnicoAsignadoDesglose({
    requestId,
}: TecnicoAsignadoDesgloseProps) {
    const { user } = useAuth()
    if (!puedeAsignar(user?.roles)) return null
    return <Contenido requestId={requestId} />
}

function Contenido({ requestId }: { requestId: string }) {
    const asignacion = useAsignacionVigente(requestId)
    const data = asignacion.data
    const sinPuntaje =
        data !== null &&
        data !== undefined &&
        data.components.length === 0 &&
        !data.score_breakdown

    return (
        <section
            aria-labelledby="detalle-tecnico-asignado"
            className="rounded-xl border border-[#dce6e4] bg-white p-6"
        >
            <h2 id="detalle-tecnico-asignado" className="text-lg font-bold">
                Técnico asignado
            </h2>

            <div className="mt-4">
                {asignacion.isPending && (
                    <p role="status" className="text-sm text-[#718096]">
                        Cargando técnico asignado…
                    </p>
                )}

                {asignacion.isError && (
                    <ErrorAlert
                        error={asignacion.error}
                        fallback="No se pudo cargar el técnico asignado."
                    />
                )}

                {asignacion.isSuccess && data === null && (
                    <p className="text-sm text-[#718096]">
                        Esta solicitud todavía no tiene técnico asignado.
                    </p>
                )}

                {data && (
                    <div>
                        <p className="text-sm font-semibold text-[#24343d]">
                            {data.full_name}
                        </p>
                        <p className="mt-1 text-xs text-[#87959c]">
                            {resumenAsignacion(data)}
                        </p>
                        <PuntajeDesglose
                            className="mt-3"
                            componentes={data.components}
                            total={data.score}
                            textoRespaldo={data.score_breakdown}
                        />
                        {sinPuntaje && (
                            <p className="mt-3 text-xs text-[#718096]">
                                Esta asignación no tiene puntaje registrado.
                            </p>
                        )}
                    </div>
                )}
            </div>
        </section>
    )
}
