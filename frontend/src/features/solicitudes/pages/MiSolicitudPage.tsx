import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  confirmarMiSolicitud,
  getMiSolicitud,
  type MiSolicitudDetalle,
} from '@/api/mis-solicitudes'
import {
  PRIORITY_STYLES,
  formatDateTime,
  statusLabel,
} from '@/features/requests/request-labels'
import { isApiError } from '@/shared/lib/error-messages'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'

/**
 * Un 404 no distingue entre folio inexistente y folio ajeno (el backend lo oculta a
 * propósito), así que se muestra un único mensaje. Es un `Error` simple para que
 * `<ErrorAlert>` lo pinte tal cual (COR-07).
 */
const FOLIO_NO_ENCONTRADO = new Error(
  'No encontramos esa solicitud. Revisa que el folio sea correcto.',
)

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

type ConfirmarDialogProps = {
  folio: string
  pendiente: boolean
  error: unknown
  onCancelar: () => void
  onConfirmar: () => void
}

function ConfirmarDialog({
  folio,
  pendiente,
  error,
  onCancelar,
  onConfirmar,
}: ConfirmarDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirmar-titulo"
        className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 id="confirmar-titulo" className="text-lg font-bold text-[#17212b]">
          ¿Confirmas la solución?
        </h2>
        <p className="text-sm text-[#52616b]">
          Al confirmar, la solicitud {folio} se cerrará. Hazlo solo si el
          problema quedó resuelto.
        </p>
        {error !== null && (
          <ErrorAlert
            error={error}
            fallback="No se pudo confirmar la solución."
          />
        )}
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={onCancelar}>
            Cancelar
          </Button>
          <Button type="button" disabled={pendiente} onClick={onConfirmar}>
            {pendiente ? 'Confirmando…' : 'Sí, confirmar'}
          </Button>
        </div>
      </div>
    </div>
  )
}

function Detalle({ solicitud }: { solicitud: MiSolicitudDetalle }) {
  const queryClient = useQueryClient()
  const [dialogoAbierto, setDialogoAbierto] = useState(false)
  const confirmar = useMutation({
    mutationFn: () => confirmarMiSolicitud(solicitud.folio),
    onSuccess: (actualizada) => {
      queryClient.setQueryData(
        ['mis-solicitudes', solicitud.folio],
        actualizada,
      )
      void queryClient.invalidateQueries({
        queryKey: ['mis-solicitudes'],
        exact: true,
      })
      setDialogoAbierto(false)
    },
  })

  return (
    <>
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <p className="font-mono text-sm text-[#87959c]">{solicitud.folio}</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            {solicitud.title}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {solicitud.priority && (
            <span
              className={cn(
                'inline-flex rounded-md px-2 py-1 text-xs font-bold',
                PRIORITY_STYLES[solicitud.priority],
              )}
            >
              {solicitud.priority}
            </span>
          )}
          <span
            data-testid="estatus"
            className="inline-flex rounded-md bg-[#d9eee9] px-2 py-1 text-xs font-bold text-[#0f766e]"
          >
            {statusLabel(solicitud.status)}
          </span>
        </div>
      </header>

      {solicitud.status === 'resolved' && (
        <div className="flex flex-col gap-3 rounded-xl border border-[#cfe7e1] bg-[#f0f9f7] p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-[#24343d]">
            El técnico marcó tu solicitud como resuelta. ¿Funcionó la solución?
          </p>
          <Button
            type="button"
            onClick={() => {
              confirmar.reset()
              setDialogoAbierto(true)
            }}
          >
            <CheckCircle2 size={16} />
            Confirmar solución
          </Button>
        </div>
      )}

      <section
        aria-labelledby="mi-solicitud-datos"
        className="rounded-xl border border-[#dce6e4] bg-white p-6"
      >
        <h2 id="mi-solicitud-datos" className="text-lg font-bold">
          Estatus de la solicitud
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Estatus" value={statusLabel(solicitud.status)} />
          <Field
            label="Prioridad"
            value={solicitud.priority ?? 'Sin asignar'}
          />
          <Field
            label="Categoría"
            value={solicitud.category ?? 'Sin asignar'}
          />
          <Field
            label="Técnico"
            value={solicitud.technician ?? 'Sin asignar'}
          />
          <Field
            label="Fecha compromiso"
            value={formatDateTime(solicitud.due_at)}
          />
          <Field
            label="Registrada"
            value={formatDateTime(solicitud.created_at)}
          />
        </dl>
      </section>

      <section
        aria-labelledby="mi-solicitud-linea"
        className="rounded-xl border border-[#dce6e4] bg-white p-6"
      >
        <h2 id="mi-solicitud-linea" className="text-lg font-bold">
          Línea de tiempo
        </h2>
        {solicitud.log.length === 0 ? (
          <p className="mt-4 text-sm text-[#718096]">
            Todavía no hay movimientos en tu solicitud.
          </p>
        ) : (
          <ol className="mt-4 ml-1.5">
            {solicitud.log.map((entrada, indice) => (
              <li
                key={`${entrada.created_at}-${indice}`}
                className="relative border-l-2 border-[#d7e0df] pb-6 pl-5 last:pb-0"
              >
                <span className="absolute top-1.5 -left-[7px] size-3 rounded-full border-2 border-white bg-[#0f766e]" />
                <p className="text-sm font-semibold text-[#24343d]">
                  {entrada.action}
                </p>
                <p className="mt-0.5 text-xs text-[#87959c]">
                  {formatDateTime(entrada.created_at)}
                  {entrada.new_status &&
                    ` · ${statusLabel(entrada.new_status)}`}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>

      {dialogoAbierto && (
        <ConfirmarDialog
          folio={solicitud.folio}
          pendiente={confirmar.isPending}
          error={confirmar.error}
          onCancelar={() => setDialogoAbierto(false)}
          onConfirmar={() => confirmar.mutate()}
        />
      )}
    </>
  )
}

/** Estatus de una solicitud propia consultada por folio (HU-04.3). */
export function MiSolicitudPage() {
  const { folio = '' } = useParams()
  const solicitud = useQuery({
    queryKey: ['mis-solicitudes', folio],
    queryFn: () => getMiSolicitud(folio),
    retry: (intentos, error) =>
      !(isApiError(error) && error.status === 404) && intentos < 3,
  })

  return (
    <div className="space-y-8">
      <Link
        to="/mis-solicitudes"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-[#0f766e] hover:underline"
      >
        <ArrowLeft size={16} />
        Volver a mis solicitudes
      </Link>

      {solicitud.isPending && (
        <p role="status" className="text-sm text-[#718096]">
          Cargando solicitud…
        </p>
      )}
      {solicitud.isError &&
        (isApiError(solicitud.error) && solicitud.error.status === 404 ? (
          <ErrorAlert error={FOLIO_NO_ENCONTRADO} />
        ) : (
          <ErrorAlert
            error={solicitud.error}
            fallback="No se pudo cargar la solicitud."
          />
        ))}
      {solicitud.isSuccess && <Detalle solicitud={solicitud.data} />}
    </div>
  )
}
