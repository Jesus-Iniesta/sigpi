import { apiFetch, apiRequest } from '@/api/client'

/*
 * Contrato de los indicadores del servicio (S5-05).
 * Tipos escritos a mano: `openapi.ts` aún no incluye estos endpoints.
 */

export type ConteoDia = {
  /** YYYY-MM-DD */
  fecha: string
  total: number
}

export type ResumenIndicadores = {
  desde: string
  hasta: string
  total: number
  por_estatus: Record<string, number>
  por_prioridad: Record<string, number>
  por_categoria: Record<string, number>
  resueltas_con_sla: number
  resueltas_en_tiempo: number
  /** Porcentaje de 0 a 100. */
  cumplimiento_sla: number
  tiempo_medio_primera_respuesta_min: number
  tiempo_medio_resolucion_min: number
  abiertas_vencidas: number
  por_dia: ConteoDia[]
}

/** Rango de fechas en formato YYYY-MM-DD (ambos extremos incluidos). */
export type RangoIndicadores = {
  desde: string
  hasta: string
}

export const CSV_NOMBRE_POR_DEFECTO = 'indicadores.csv'

function rangoQuery({ desde, hasta }: RangoIndicadores): string {
  return new URLSearchParams({ desde, hasta }).toString()
}

export function getResumenIndicadores(
  rango: RangoIndicadores,
): Promise<ResumenIndicadores> {
  return apiFetch<ResumenIndicadores>(
    `/indicadores/resumen?${rangoQuery(rango)}`,
  )
}

/** Lee el nombre del archivo de `Content-Disposition`; si no llega, `indicadores.csv`. */
export function nombreDeArchivo(disposition: string | null): string {
  if (!disposition) return CSV_NOMBRE_POR_DEFECTO
  const extendido = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(disposition)
  if (extendido) {
    try {
      const nombre = decodeURIComponent(extendido[1].trim().replace(/"/g, ''))
      if (nombre) return nombre
    } catch {
      // Codificación inválida: se intenta con `filename`.
    }
  }
  const simple = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(disposition)
  const nombre = (simple?.[2] ?? simple?.[1] ?? '').trim()
  return nombre || CSV_NOMBRE_POR_DEFECTO
}

/**
 * Descarga el CSV del rango con la sesión del usuario (no basta un enlace directo).
 * Devuelve el nombre con que se guardó el archivo. Si el servidor responde con error,
 * lanza `ApiError` igual que `apiFetch`.
 */
export async function exportarIndicadoresCsv(
  rango: RangoIndicadores,
): Promise<string> {
  const response = await apiRequest(
    `/indicadores/exportar.csv?${rangoQuery(rango)}`,
  )
  const blob = await response.blob()
  const nombre = nombreDeArchivo(response.headers.get('Content-Disposition'))

  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  // Se revoca después del clic para no cancelar la descarga en algunos navegadores.
  setTimeout(() => URL.revokeObjectURL(url), 0)
  return nombre
}
