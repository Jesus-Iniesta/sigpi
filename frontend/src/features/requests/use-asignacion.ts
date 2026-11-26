import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  asignarTecnico,
  getPropuestaAsignacion,
  type AsignacionResult,
} from '@/api/asignaciones'
import { SOLICITUDES_LISTA_KEY } from '@/features/requests/use-solicitudes'

/**
 * Propuesta de técnicos para una solicitud (HU-03.1). No se carga sola: la pide
 * la persona con «Proponer técnico» (`enabled`).
 */
export function usePropuestaAsignacion(requestId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['asignaciones', requestId, 'propuesta'],
    queryFn: () => getPropuestaAsignacion(requestId),
    enabled,
  })
}

/**
 * Asigna la solicitud a un técnico (HU-03.3). Al terminar refresca el detalle de
 * la solicitud (con su bitácora) y el listado de solicitudes.
 */
export function useAsignarTecnico(requestId: string) {
  const queryClient = useQueryClient()
  return useMutation<AsignacionResult, Error, string>({
    mutationFn: (technicianId) => asignarTecnico(requestId, technicianId),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['solicitudes', requestId] }),
        queryClient.invalidateQueries({ queryKey: SOLICITUDES_LISTA_KEY }),
      ]),
  })
}
