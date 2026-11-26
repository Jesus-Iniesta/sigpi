import { useMutation, useQuery } from '@tanstack/react-query'
import {
  exportarIndicadoresCsv,
  getResumenIndicadores,
  type RangoIndicadores,
} from '@/api/indicadores'

/** Resumen del rango; no consulta mientras el rango sea `null` (inválido). */
export function useResumenIndicadores(rango: RangoIndicadores | null) {
  return useQuery({
    queryKey: ['indicadores', 'resumen', rango?.desde, rango?.hasta],
    queryFn: () => getResumenIndicadores(rango as RangoIndicadores),
    enabled: rango !== null,
  })
}

export function useExportarIndicadores() {
  return useMutation({ mutationFn: exportarIndicadoresCsv })
}
