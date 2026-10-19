import { AlertCircle, ArrowLeft, ShieldQuestion } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import type { RequestDetail, RequestLogEntry } from '@/api/seguimiento'
import { useAuth } from '@/features/auth/auth-context'
import {
  CHANNEL_LABELS,
  PRIORITY_STYLES,
  formatDateTime,
  formatMinutes,
  levelLabel,
  statusLabel,
} from '@/features/requests/request-labels'
import { useSolicitudDetalle } from '@/features/requests/use-solicitud-detalle'
import { cn } from '@/shared/lib/utils'

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-[#24343d]">{value}</dd>
    </div>
  )
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700"
    >
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function requesterLabel(request: RequestDetail): string {
  if (request.requester_institutional_id) {
    return request.requester_institutional_id
  }
  return request.requester_id ? 'Cuenta registrada' : 'Sin identificar'
}

function authorLabel(authorId: string, currentUserId: string | undefined) {
  if (authorId === currentUserId) return 'Tú'
  return `Usuario ${authorId.slice(0, 8)}`
}

function BitacoraEntry({
  entry,
  currentUserId,
}: {
  entry: RequestLogEntry
  currentUserId: string | undefined
}) {
  const changedStatus =
    entry.new_status !== null && entry.new_status !== entry.previous_status

  return (
    <li className="relative border-l-2 border-[#d7e0df] pb-6 pl-5 last:pb-0">
      <span className="absolute top-1.5 -left-[7px] size-3 rounded-full border-2 border-white bg-[#0f766e]" />
      <p className="text-sm font-semibold text-[#24343d]">{entry.action}</p>
      <p className="mt-0.5 text-xs text-[#87959c]">
        {formatDateTime(entry.created_at)} ·{' '}
        {authorLabel(entry.author_id, currentUserId)}
      </p>
      {changedStatus && (
        <p className="mt-1 text-xs text-[#52616b]">
          Estado:{' '}
          {entry.previous_status ? statusLabel(entry.previous_status) : 'Nueva'}
          {' → '}
          {statusLabel(entry.new_status)}
        </p>
      )}
      {entry.notes && (
        <p className="mt-2 text-sm whitespace-pre-line text-[#52616b]">
          {entry.notes}
        </p>
      )}
    </li>
  )
}

export function SolicitudDetallePage() {
  const { id = '' } = useParams()
  const { user } = useAuth()
  const { detalle, bitacora } = useSolicitudDetalle(id)

  const backLink = (
    <Link
      to="/solicitudes"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-[#0f766e] hover:underline"
    >
      <ArrowLeft size={16} />
      Volver a solicitudes
    </Link>
  )

  if (detalle.isPending) {
    return (
      <div className="space-y-4">
        {backLink}
        <p role="status" className="text-sm text-[#718096]">
          Cargando solicitud…
        </p>
      </div>
    )
  }

  if (detalle.isError) {
    return (
      <div className="space-y-4">
        {backLink}
        <ErrorMessage
          message={`No se pudo cargar la solicitud. ${detalle.error.message}`}
        />
      </div>
    )
  }

  const request = detalle.data

  return (
    <div className="space-y-8">
      {backLink}

      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <p className="font-mono text-sm text-[#87959c]">{request.folio}</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            {request.title}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {request.priority && (
            <span
              className={cn(
                'inline-flex rounded-md px-2 py-1 text-xs font-bold',
                PRIORITY_STYLES[request.priority],
              )}
            >
              {request.priority}
            </span>
          )}
          <span className="inline-flex rounded-md bg-[#d9eee9] px-2 py-1 text-xs font-bold text-[#0f766e]">
            {statusLabel(request.status)}
          </span>
        </div>
      </header>

      {request.status === 'pending_verification' && (
        <div
          role="note"
          className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800"
        >
          <ShieldQuestion size={16} className="mt-0.5 shrink-0" />
          <span>
            El solicitante aún no se ha localizado: la solicitud quedó por
            verificar. Revisa la bitácora para ver el motivo.
          </span>
        </div>
      )}

      <section
        aria-labelledby="detalle-datos"
        className="rounded-xl border border-[#dce6e4] bg-white p-6"
      >
        <h2 id="detalle-datos" className="text-lg font-bold">
          Datos de la solicitud
        </h2>
        <p className="mt-3 text-sm whitespace-pre-line text-[#52616b]">
          {request.description}
        </p>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Solicitante" value={requesterLabel(request)} />
          <Field label="Canal" value={CHANNEL_LABELS[request.channel]} />
          <Field label="Ubicación" value={request.physical_location} />
          <Field label="Urgencia" value={levelLabel(request.urgency)} />
          <Field label="Impacto" value={levelLabel(request.impact)} />
          <Field
            label="Registrada"
            value={formatDateTime(request.created_at)}
          />
          <Field
            label="Primera respuesta"
            value={formatDateTime(request.first_response_at)}
          />
          <Field label="Resuelta" value={formatDateTime(request.resolved_at)} />
          <Field label="Cerrada" value={formatDateTime(request.closed_at)} />
          <Field
            label="Tiempo efectivo de resolución"
            value={formatMinutes(request.resolution_minutes)}
          />
        </dl>
      </section>

      <section
        aria-labelledby="detalle-atencion"
        className="rounded-xl border border-[#dce6e4] bg-white p-6"
      >
        <h2 id="detalle-atencion" className="text-lg font-bold">
          Diagnóstico y solución
        </h2>
        <dl className="mt-4 space-y-4">
          <div>
            <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
              Diagnóstico
            </dt>
            <dd className="mt-1 text-sm whitespace-pre-line text-[#24343d]">
              {request.diagnosis ?? 'Aún no se registra un diagnóstico.'}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold tracking-wide text-[#87959c] uppercase">
              Solución
            </dt>
            <dd className="mt-1 text-sm whitespace-pre-line text-[#24343d]">
              {request.solution ?? 'Aún no se registra una solución.'}
            </dd>
          </div>
        </dl>
      </section>

      <section
        aria-labelledby="detalle-bitacora"
        className="rounded-xl border border-[#dce6e4] bg-white p-6"
      >
        <h2 id="detalle-bitacora" className="text-lg font-bold">
          Bitácora
        </h2>
        <div className="mt-4">
          {bitacora.isPending && (
            <p role="status" className="text-sm text-[#718096]">
              Cargando bitácora…
            </p>
          )}
          {bitacora.isError && (
            <ErrorMessage
              message={`No se pudo cargar la bitácora. ${bitacora.error.message}`}
            />
          )}
          {bitacora.isSuccess && bitacora.data.length === 0 && (
            <p className="text-sm text-[#718096]">
              Esta solicitud todavía no tiene entradas en la bitácora.
            </p>
          )}
          {bitacora.isSuccess && bitacora.data.length > 0 && (
            <ol className="ml-1.5">
              {bitacora.data.map((entry) => (
                <BitacoraEntry
                  key={entry.id}
                  entry={entry}
                  currentUserId={user?.id}
                />
              ))}
            </ol>
          )}
        </div>
      </section>
    </div>
  )
}
