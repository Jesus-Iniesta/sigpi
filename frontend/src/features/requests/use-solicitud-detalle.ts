import { useQuery } from '@tanstack/react-query'
import { getRequestDetail, getRequestLog } from '@/api/seguimiento'

/**
 * Carga el detalle de una solicitud y su bitácora (HU-04.1).
 * Son dos consultas independientes: si la bitácora falla (por ejemplo, por
 * permisos), el detalle se sigue mostrando.
 */
export function useSolicitudDetalle(requestId: string) {
  const detalle = useQuery({
    queryKey: ['solicitudes', requestId],
    queryFn: () => getRequestDetail(requestId),
  })
  const bitacora = useQuery({
    queryKey: ['solicitudes', requestId, 'bitacora'],
    queryFn: () => getRequestLog(requestId),
  })
  return { detalle, bitacora }
}
