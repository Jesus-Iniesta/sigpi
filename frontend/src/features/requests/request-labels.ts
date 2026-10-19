import type { Priority } from '@/api/types'
import type { RequestChannel, RequestStatus } from '@/api/seguimiento'

export const STATUS_LABELS: Record<RequestStatus, string> = {
  registered: 'Registrada',
  pending_verification: 'Por verificar',
  classified: 'Clasificada',
  pending_review: 'En revisión',
  assigned: 'Asignada',
  in_progress: 'En proceso',
  waiting: 'En espera',
  escalated: 'Escalada',
  resolved: 'Resuelta',
  closed: 'Cerrada',
  closed_unverified: 'Cerrada sin verificar',
}

export const CHANNEL_LABELS: Record<RequestChannel, string> = {
  portal: 'Portal',
  phone: 'Teléfono',
  in_person: 'Presencial',
}

export const PRIORITY_STYLES: Record<Priority, string> = {
  P1: 'bg-[#fce4df] text-[#b54735]',
  P2: 'bg-[#f8edcf] text-[#a56c14]',
  P3: 'bg-[#dceef0] text-[#28717a]',
  P4: 'bg-[#e8edf0] text-[#60717a]',
}

const LEVEL_LABELS: Record<number, string> = {
  1: 'Baja',
  2: 'Media',
  3: 'Alta',
}

export function levelLabel(value: number | null): string {
  return value === null ? 'Sin definir' : (LEVEL_LABELS[value] ?? String(value))
}

export function statusLabel(status: RequestStatus | null): string {
  return status === null ? '—' : STATUS_LABELS[status]
}

/** Fecha y hora en formato local (es-MX); «—» cuando aún no ocurre. */
export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('es-MX', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

/** 150 → «2 h 30 min»; 45 → «45 min». */
export function formatMinutes(minutes: number | null): string {
  if (minutes === null) return '—'
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest} min`
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}
