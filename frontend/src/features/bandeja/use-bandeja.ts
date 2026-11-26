import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getBandeja, type BandejaParams } from '@/api/bandeja'

export const BANDEJA_KEY = ['bandeja'] as const

/** Se vuelve a consultar sola cada minuto para mantener al día el tiempo consumido. */
export const BANDEJA_REFRESCO_MS = 60_000

/** Bandeja de solicitudes asignadas con filtros (HU-04.6). */
export function useBandeja(params: BandejaParams) {
  return useQuery({
    queryKey: [...BANDEJA_KEY, params],
    queryFn: () => getBandeja(params),
    placeholderData: keepPreviousData,
    refetchInterval: BANDEJA_REFRESCO_MS,
  })
}
