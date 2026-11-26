import type { RangoIndicadores } from '@/api/indicadores'

/** Fecha local en formato YYYY-MM-DD. */
export function fechaLocal(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

/** Últimos `dias` días, hoy incluido (como el valor por omisión del servidor). */
export function rangoUltimosDias(
  dias: number,
  hoy = new Date(),
): RangoIndicadores {
  const inicio = new Date(hoy)
  inicio.setDate(inicio.getDate() - (dias - 1))
  return { desde: fechaLocal(inicio), hasta: fechaLocal(hoy) }
}
