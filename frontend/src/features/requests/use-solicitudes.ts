import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { listRequests, type ListRequestsParams } from '@/api/solicitudes'

export const SOLICITUDES_LISTA_KEY = ['solicitudes', 'lista'] as const

/**
 * Listado de solicitudes con búsqueda, filtros y paginación.
 * Conserva la página anterior en pantalla mientras llega la siguiente.
 */
export function useSolicitudes(params: ListRequestsParams) {
  return useQuery({
    queryKey: [...SOLICITUDES_LISTA_KEY, params],
    queryFn: () => listRequests(params),
    placeholderData: keepPreviousData,
  })
}
