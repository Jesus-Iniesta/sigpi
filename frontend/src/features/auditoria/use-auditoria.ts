import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getAuditoria, type FiltrosAuditoria } from '@/api/auditoria'

/** Registros de auditoría que cumplen los filtros. */
export function useAuditoria(filtros: FiltrosAuditoria) {
  return useQuery({
    queryKey: ['auditoria', filtros],
    queryFn: () => getAuditoria(filtros),
    placeholderData: keepPreviousData,
  })
}
