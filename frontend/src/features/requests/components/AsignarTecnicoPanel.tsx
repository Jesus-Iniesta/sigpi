import { CheckCircle2, UserCheck } from 'lucide-react'
import { useState } from 'react'
import type { CandidatoAsignacion } from '@/api/asignaciones'
import type { RequestStatus } from '@/api/seguimiento'
import { useAuth } from '@/features/auth/auth-context'
import { puedeAsignar } from '@/features/requests/assign-roles'
import { PuntajeDesglose } from '@/features/requests/components/PuntajeDesglose'
import {
  useAsignarTecnico,
  usePropuestaAsignacion,
} from '@/features/requests/use-asignacion'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'

// Una solicitud resuelta o cerrada ya no se asigna.
const FINAL_STATUSES: RequestStatus[] = [
  'resolved',
  'closed',
  'closed_unverified',
]

type AsignarTecnicoPanelProps = {
  requestId: string
  status: RequestStatus
}

/**
 * Propone técnicos para la solicitud y permite asignarla (HU-03.1, HU-03.3).
 * Solo se muestra a quien tiene `requests.assign` y si la solicitud sigue abierta.
 */
export function AsignarTecnicoPanel({
  requestId,
  status,
}: AsignarTecnicoPanelProps) {
  const { user } = useAuth()
  const canAssign = puedeAsignar(user?.roles)

  if (!canAssign || FINAL_STATUSES.includes(status)) return null
  return <PanelContent requestId={requestId} />
}

function PanelContent({ requestId }: { requestId: string }) {
  const [requested, setRequested] = useState(false)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [assigned, setAssigned] = useState<CandidatoAsignacion | null>(null)
  const propuesta = usePropuestaAsignacion(requestId, requested)
  const asignar = useAsignarTecnico(requestId)

  function handlePropose() {
    setAssigned(null)
    setConfirmingId(null)
    asignar.reset()
    if (requested) void propuesta.refetch()
    else setRequested(true)
  }

  function handleConfirm(candidato: CandidatoAsignacion) {
    asignar.mutate(candidato.technician_id, {
      onSuccess: () => {
        setAssigned(candidato)
        setConfirmingId(null)
      },
    })
  }

  return (
    <section
      aria-labelledby="detalle-asignacion"
      className="rounded-xl border border-[#dce6e4] bg-white p-6"
    >
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <h2 id="detalle-asignacion" className="text-lg font-bold">
          Asignar técnico
        </h2>
        <Button
          variant="secondary"
          onClick={handlePropose}
          disabled={propuesta.isFetching}
        >
          <UserCheck size={16} />
          Proponer técnico
        </Button>
      </div>

      <div className="mt-4 space-y-4">
        {assigned && (
          <div
            role="status"
            className="flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800"
          >
            <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
            <span>
              Solicitud asignada a <strong>{assigned.full_name}</strong>.
            </span>
          </div>
        )}

        {!requested && !assigned && (
          <p className="text-sm text-[#718096]">
            Pulsa «Proponer técnico» para ver los candidatos con su puntaje.
          </p>
        )}

        {requested && propuesta.isFetching && (
          <p role="status" className="text-sm text-[#718096]">
            Buscando candidatos…
          </p>
        )}

        {propuesta.isError && (
          <ErrorAlert
            error={propuesta.error}
            fallback="No se pudo obtener la propuesta de técnicos."
          />
        )}

        {asignar.isError && (
          <ErrorAlert
            error={asignar.error}
            fallback="No se pudo asignar la solicitud."
          />
        )}

        {propuesta.isSuccess &&
          !propuesta.isFetching &&
          !assigned &&
          propuesta.data.length === 0 && (
            <p className="text-sm text-[#718096]">
              No hay técnicos disponibles para esta categoría.
            </p>
          )}

        {propuesta.isSuccess &&
          !propuesta.isFetching &&
          !assigned &&
          propuesta.data.length > 0 && (
            <ol aria-label="Candidatos" className="space-y-3">
              {propuesta.data.map((candidato, index) => (
                <CandidatoItem
                  key={candidato.technician_id}
                  candidato={candidato}
                  suggested={index === 0}
                  confirming={confirmingId === candidato.technician_id}
                  busy={asignar.isPending}
                  onAssign={() => setConfirmingId(candidato.technician_id)}
                  onCancel={() => setConfirmingId(null)}
                  onConfirm={() => handleConfirm(candidato)}
                />
              ))}
            </ol>
          )}
      </div>
    </section>
  )
}

type CandidatoItemProps = {
  candidato: CandidatoAsignacion
  suggested: boolean
  confirming: boolean
  busy: boolean
  onAssign: () => void
  onCancel: () => void
  onConfirm: () => void
}

function CandidatoItem({
  candidato,
  suggested,
  confirming,
  busy,
  onAssign,
  onCancel,
  onConfirm,
}: CandidatoItemProps) {
  return (
    <li
      aria-label={candidato.full_name}
      className="rounded-lg border border-[#e3ebea] p-4"
    >
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold text-[#24343d]">
            {candidato.full_name}
            {suggested && (
              <span className="inline-flex rounded-md bg-[#d9eee9] px-2 py-0.5 text-xs font-bold text-[#0f766e]">
                Sugerido
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-[#52616b]">
            Puntaje: <strong>{candidato.score}</strong> · Carga actual:{' '}
            {candidato.active_load}{' '}
            {candidato.active_load === 1 ? 'solicitud' : 'solicitudes'}
          </p>
        </div>
        {confirming ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#52616b]">
              ¿Asignar a {candidato.full_name}?
            </span>
            <Button onClick={onConfirm} disabled={busy}>
              Confirmar
            </Button>
            <Button variant="ghost" onClick={onCancel} disabled={busy}>
              Cancelar
            </Button>
          </div>
        ) : (
          <Button onClick={onAssign} disabled={busy}>
            Asignar
          </Button>
        )}
      </div>
      <PuntajeDesglose className="mt-3" componentes={candidato.components} />
    </li>
  )
}
