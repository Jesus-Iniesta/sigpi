import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { BandejaElemento } from '@/api/bandeja'
import type { RequestStatus } from '@/api/seguimiento'
import type { Priority } from '@/api/types'
import { useAuth } from '@/features/auth/auth-context'
import {
  PRIORITY_STYLES,
  STATUS_LABELS,
  formatDateTime,
} from '@/features/requests/request-labels'
import { ErrorAlert } from '@/shared/ui/error-alert'
import { useBandeja } from '../use-bandeja'

// Roles con el permiso requests.assign: pueden ver la bandeja de todo el equipo.
const TEAM_ROLES = ['administrator', 'service_manager']
// La bandeja solo trae solicitudes abiertas con asignación vigente.
const STATUSES: RequestStatus[] = [
  'assigned',
  'in_progress',
  'waiting',
  'escalated',
]
const PRIORITIES: Priority[] = ['P1', 'P2', 'P3', 'P4']

const fieldClass =
  'h-10 rounded-lg border border-[#d7e0df] bg-[#fafcfc] px-3 text-sm outline-none focus:border-[#0f766e]'

function TiempoConsumido({ elemento }: { elemento: BandejaElemento }) {
  const { porcentaje_consumido: porcentaje, en_riesgo: enRiesgo } = elemento
  if (porcentaje === null) {
    return <span className="text-[#87959c]">Sin SLA</span>
  }
  const ancho = Math.min(Math.max(porcentaje, 0), 100)
  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-label={`Tiempo consumido de ${elemento.folio}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(ancho)}
        className="h-2 w-24 overflow-hidden rounded-full bg-[#edf2f1]"
      >
        <div
          className={enRiesgo ? 'h-full bg-[#b54735]' : 'h-full bg-[#0f766e]'}
          style={{ width: `${ancho}%` }}
        />
      </div>
      <span className="text-xs text-[#52616b] tabular-nums">
        {Math.round(porcentaje)} %
      </span>
    </div>
  )
}

export function BandejaPage() {
  const { user } = useAuth()
  const [estatus, setEstatus] = useState<RequestStatus | ''>('')
  const [prioridad, setPrioridad] = useState<Priority | ''>('')
  const [todas, setTodas] = useState(false)

  const puedeVerEquipo =
    user?.roles.some((role) => TEAM_ROLES.includes(role)) ?? false

  const bandeja = useBandeja({
    estatus,
    prioridad,
    todas: puedeVerEquipo && todas,
  })
  const items = bandeja.data ?? []

  return (
    <div className="space-y-8">
      <section>
        <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
          Atención
        </p>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Mi bandeja
        </h1>
        <p className="mt-2 text-[#718096]">
          Solicitudes asignadas, de la más urgente a la menos urgente.
        </p>
      </section>
      <section className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
        <div className="flex flex-col gap-3 border-b border-[#edf2f1] p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-3">
            <select
              aria-label="Filtrar por estatus"
              value={estatus}
              onChange={(event) =>
                setEstatus(event.target.value as RequestStatus | '')
              }
              className={fieldClass}
            >
              <option value="">Todos los estatus</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </select>
            <select
              aria-label="Filtrar por prioridad"
              value={prioridad}
              onChange={(event) =>
                setPrioridad(event.target.value as Priority | '')
              }
              className={fieldClass}
            >
              <option value="">Todas las prioridades</option>
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          {puedeVerEquipo && (
            <label className="flex items-center gap-2 text-sm text-[#52616b]">
              <input
                type="checkbox"
                role="switch"
                checked={todas}
                onChange={(event) => setTodas(event.target.checked)}
                className="size-4 accent-[#0f766e]"
              />
              Ver todo el equipo
            </label>
          )}
        </div>

        {bandeja.isError && (
          <div className="p-4">
            <ErrorAlert
              error={bandeja.error}
              fallback="No fue posible cargar la bandeja."
            />
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-175 text-left text-sm">
            <thead className="bg-[#f8faf9] text-xs tracking-wide text-[#87959c] uppercase">
              <tr>
                <th className="px-5 py-3 font-semibold">Solicitud</th>
                <th className="px-5 py-3 font-semibold">Prioridad</th>
                <th className="px-5 py-3 font-semibold">Estado</th>
                <th className="px-5 py-3 font-semibold">Categoría</th>
                <th className="px-5 py-3 font-semibold">Compromiso</th>
                <th className="px-5 py-3 font-semibold">Tiempo consumido</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#edf2f1]">
              {bandeja.isPending && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-5 py-8 text-center text-[#718096]"
                  >
                    Cargando bandeja…
                  </td>
                </tr>
              )}
              {bandeja.isSuccess && items.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-5 py-8 text-center text-[#718096]"
                  >
                    No tienes solicitudes asignadas
                  </td>
                </tr>
              )}
              {items.map((elemento) => (
                <tr
                  key={elemento.request_id}
                  data-en-riesgo={elemento.en_riesgo || undefined}
                  className={
                    elemento.en_riesgo
                      ? 'bg-[#fdf3f1] hover:bg-[#fbeae6]'
                      : 'hover:bg-[#fbfdfc]'
                  }
                >
                  <td className="px-5 py-4">
                    <Link
                      to={`/solicitudes/${elemento.request_id}`}
                      className="font-mono text-xs font-semibold text-[#0f766e] hover:underline"
                    >
                      {elemento.folio}
                    </Link>
                    <p className="mt-1 font-semibold text-[#24343d]">
                      {elemento.titulo}
                    </p>
                    {elemento.en_riesgo && (
                      <span className="mt-1 inline-flex rounded-md bg-[#fce4df] px-2 py-0.5 text-xs font-bold text-[#b54735]">
                        En riesgo
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    {elemento.prioridad ? (
                      <span
                        className={`inline-flex rounded-md px-2 py-1 text-xs font-bold ${PRIORITY_STYLES[elemento.prioridad]}`}
                      >
                        {elemento.prioridad}
                      </span>
                    ) : (
                      <span className="text-[#87959c]">—</span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-[#52616b]">
                    {STATUS_LABELS[elemento.estatus]}
                  </td>
                  <td className="px-5 py-4 text-[#52616b]">
                    {elemento.categoria ?? 'Sin categoría'}
                  </td>
                  <td className="px-5 py-4 text-[#52616b]">
                    {formatDateTime(elemento.fecha_compromiso)}
                  </td>
                  <td className="px-5 py-4">
                    <TiempoConsumido elemento={elemento} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
