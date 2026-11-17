import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import type { RequestStatus } from '@/api/seguimiento'
import { putRequestOnHold, type RequestSummary } from '@/api/solicitudes'
import type { Priority, WaitReason } from '@/api/types'
import { useAuth } from '@/features/auth/auth-context'
import { EsperaDialog } from '@/features/requests/components/EsperaDialog'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'
import {
  PRIORITY_STYLES,
  STATUS_LABELS,
  formatDateTime,
} from './request-labels'
import { SolicitudForm } from './solicitud-form'
import { SOLICITUDES_LISTA_KEY, useSolicitudes } from './use-solicitudes'

const PAGE_SIZE = 10
const DEBOUNCE_MS = 300

// Roles que pueden abrir el detalle de atención (/solicitudes/:id).
const STAFF_ROLES = ['administrator', 'service_manager', 'support_agent']
// Estatus desde los que una solicitud puede pasar a «En espera».
const CAN_WAIT: RequestStatus[] = ['assigned', 'in_progress']

const STATUSES = Object.keys(STATUS_LABELS) as RequestStatus[]
const PRIORITIES: Priority[] = ['P1', 'P2', 'P3', 'P4']

const fieldClass =
  'h-10 rounded-lg border border-[#d7e0df] bg-[#fafcfc] px-3 text-sm outline-none focus:border-[#0f766e]'

export function RequestsPage() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const { user } = useAuth()

  // El botón «Nueva solicitud» del Resumen llega con { openForm: true }.
  const [isFormOpen, setIsFormOpen] = useState(
    Boolean((location.state as { openForm?: boolean } | null)?.openForm),
  )
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<RequestStatus | ''>('')
  const [priority, setPriority] = useState<Priority | ''>('')
  const [page, setPage] = useState(0)
  const [onHold, setOnHold] = useState<RequestSummary | null>(null)

  // La búsqueda se envía al servidor al dejar de escribir.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim())
      setPage(0)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [search])

  const isStaff =
    user?.roles.some((role) => STAFF_ROLES.includes(role)) ?? false
  const isRequester = user?.roles.includes('requester') ?? false

  const requests = useSolicitudes({
    q: query,
    status,
    priority,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  })
  const items = requests.data?.items ?? []
  const total = requests.data?.total ?? 0
  const offset = page * PAGE_SIZE
  const from = total === 0 ? 0 : offset + 1
  const to = offset + items.length

  // El detalle usa el id (UUID); el solicitante consulta con su folio.
  const detailPath = (request: RequestSummary): string | null => {
    if (isStaff) return `/solicitudes/${request.id}`
    if (isRequester) return `/mis-solicitudes/${request.folio}`
    return null
  }

  const confirmWait = async (
    request: RequestSummary,
    reason: WaitReason,
    detail: string | null,
  ) => {
    // Si falla, el error llega al diálogo, que lo muestra.
    await putRequestOnHold(request.id, reason, detail)
    await queryClient.invalidateQueries({ queryKey: SOLICITUDES_LISTA_KEY })
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Gestión operativa
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Solicitudes
          </h1>
          <p className="mt-2 text-[#718096]">
            {isStaff
              ? 'Consulta y prioriza las solicitudes institucionales.'
              : 'Consulta el avance de tus solicitudes.'}
          </p>
        </div>
        <Button onClick={() => setIsFormOpen(true)}>
          <Plus size={17} />
          Nueva solicitud
        </Button>
      </section>
      <section className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
        <div className="flex flex-col gap-3 border-b border-[#edf2f1] p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative max-w-sm flex-1">
            <Search
              size={16}
              className="absolute top-1/2 left-3 -translate-y-1/2 text-[#87959c]"
            />
            <input
              type="search"
              aria-label="Buscar solicitudes"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className={`${fieldClass} w-full pr-3 pl-9 placeholder:text-[#a0adb2]`}
              placeholder="Buscar por folio, título o solicitante..."
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <select
              aria-label="Filtrar por estatus"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as RequestStatus | '')
                setPage(0)
              }}
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
              value={priority}
              onChange={(event) => {
                setPriority(event.target.value as Priority | '')
                setPage(0)
              }}
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
        </div>

        {requests.isError && (
          <div className="p-4">
            <ErrorAlert
              error={requests.error}
              fallback="No fue posible cargar las solicitudes."
            />
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-175 text-left text-sm">
            <thead className="bg-[#f8faf9] text-xs tracking-wide text-[#87959c] uppercase">
              <tr>
                <th className="px-5 py-3 font-semibold">Solicitud</th>
                <th className="px-5 py-3 font-semibold">Categoría</th>
                <th className="px-5 py-3 font-semibold">Solicitante</th>
                <th className="px-5 py-3 font-semibold">Prioridad</th>
                <th className="px-5 py-3 font-semibold">Estado</th>
                <th className="px-5 py-3 font-semibold">Registrada</th>
                {isStaff && (
                  <th className="px-5 py-3 font-semibold">Acciones</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#edf2f1]">
              {requests.isPending && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-5 py-8 text-center text-[#718096]"
                  >
                    Cargando solicitudes…
                  </td>
                </tr>
              )}
              {requests.isSuccess && items.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-5 py-8 text-center text-[#718096]"
                  >
                    No hay solicitudes que coincidan.
                  </td>
                </tr>
              )}
              {items.map((request) => {
                const path = detailPath(request)
                return (
                  <tr key={request.id} className="hover:bg-[#fbfdfc]">
                    <td className="px-5 py-4">
                      {path ? (
                        <Link
                          to={path}
                          className="font-semibold text-[#24343d] hover:text-[#0f766e] hover:underline"
                        >
                          {request.title}
                        </Link>
                      ) : (
                        <p className="font-semibold text-[#24343d]">
                          {request.title}
                        </p>
                      )}
                      <p className="mt-1 font-mono text-xs text-[#87959c]">
                        {request.folio}
                      </p>
                    </td>
                    <td className="px-5 py-4 text-[#52616b]">
                      {request.category_name ?? 'Sin categoría'}
                    </td>
                    <td className="px-5 py-4 text-[#52616b]">
                      {request.requester_name ??
                        request.requester_institutional_id ??
                        '—'}
                    </td>
                    <td className="px-5 py-4">
                      {request.priority ? (
                        <span
                          className={`inline-flex rounded-md px-2 py-1 text-xs font-bold ${PRIORITY_STYLES[request.priority]}`}
                        >
                          {request.priority}
                        </span>
                      ) : (
                        <span className="text-[#87959c]">—</span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-[#52616b]">
                      {STATUS_LABELS[request.status]}
                    </td>
                    <td className="px-5 py-4 text-[#87959c]">
                      {formatDateTime(request.created_at)}
                    </td>
                    {isStaff && (
                      <td className="px-5 py-4">
                        {CAN_WAIT.includes(request.status) && (
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => setOnHold(request)}
                          >
                            Marcar en espera
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#edf2f1] px-5 py-3 text-sm text-[#718096]">
          <p>
            {total === 0
              ? 'Sin resultados'
              : `Mostrando ${from}–${to} de ${total}`}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={page === 0 || requests.isPlaceholderData}
              onClick={() => setPage((value) => value - 1)}
            >
              <ChevronLeft size={16} />
              Anterior
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={
                offset + PAGE_SIZE >= total || requests.isPlaceholderData
              }
              onClick={() => setPage((value) => value + 1)}
            >
              Siguiente
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      </section>

      {isFormOpen && <SolicitudForm onClose={() => setIsFormOpen(false)} />}

      {onHold && (
        <EsperaDialog
          open
          onClose={() => setOnHold(null)}
          folio={onHold.folio}
          onConfirm={(reason, detail) => confirmWait(onHold, reason, detail)}
        />
      )}
    </div>
  )
}
