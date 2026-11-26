import { useQuery } from '@tanstack/react-query'
import { getAsignacionVigente } from '@/api/asignaciones'

/**
 * Técnico asignado y desglose de su puntaje (S5-12). La clave cuelga de
 * `['solicitudes', requestId]`, así que al asignar o reasignar (que invalida
 * esa clave) se vuelve a consultar sola.
 */
export function useAsignacionVigente(requestId: string) {
    return useQuery({
        queryKey: ['solicitudes', requestId, 'asignacion'],
        queryFn: () => getAsignacionVigente(requestId),
    })
}
