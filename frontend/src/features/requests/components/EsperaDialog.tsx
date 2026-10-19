import { useState } from 'react'
import { AlertCircle, Clock, X } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import type { WaitReason } from '@/api/types'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

type EsperaDialogProps = {
  open: boolean
  onClose: () => void
  folio: string
  onConfirm: (reason: WaitReason, detail: string | null) => Promise<void>
}

type FormErrors = {
  detail?: string
}

type ReasonOption = WaitReason | 'other'

const WAIT_REASONS: { value: ReasonOption; label: string }[] = [
  { value: 'external_input', label: 'Esperando insumo externo' },
  { value: 'user_information', label: 'Esperando información del solicitante' },
  { value: 'other', label: 'Otro (especificar)' },
]

function validate(reason: ReasonOption, detail: string | null): FormErrors {
  const errors: FormErrors = {}
  if (reason === 'other' && (!detail || !detail.trim())) {
    errors.detail = 'Por favor describe el motivo de espera.'
  }
  return errors
}

function toBackendReason(reason: ReasonOption): WaitReason {
  return reason === 'other' ? 'user_information' : reason
}

export function EsperaDialog({
  open,
  onClose,
  folio,
  onConfirm,
}: EsperaDialogProps) {
  const [reason, setReason] = useState<ReasonOption>('external_input')
  const [detail, setDetail] = useState<string | null>(null)
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)

  const showDetail = reason === 'other'

  const confirmMutation = useMutation({
    mutationFn: () => onConfirm(toBackendReason(reason), detail),
    onSuccess: () => {
      onClose()
    },
    onError: (error: Error) => {
      setApiError(error.message)
    },
  })

  const handleConfirm = () => {
    setApiError(null)
    const validationErrors = validate(reason, detail)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    confirmMutation.mutate()
  }

  const isUnauthenticated =
    apiError !== null && /sesión|autorizado|401/i.test(apiError)

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-[#edf2f1] px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-[#17212b]">
              Motivo de espera
            </h2>
            <p className="mt-0.5 text-sm text-[#718096]">Folio: {folio}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-[#87959c] hover:bg-[#e7efee] hover:text-[#17212b]"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            handleConfirm()
          }}
          className="space-y-4 px-6 py-5"
          noValidate
        >
          <div>
            <label
              htmlFor="espera-reason"
              className="block text-sm font-medium text-[#334155]"
            >
              Motivo
            </label>
            <select
              id="espera-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value as ReasonOption)}
              className="mt-1.5 w-full rounded-lg border border-[#d7e0df] bg-white px-3 py-2.5 text-sm text-[#17212b] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
            >
              {WAIT_REASONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          {showDetail && (
            <div>
              <label
                htmlFor="espera-detail"
                className="block text-sm font-medium text-[#334155]"
              >
                Describe el motivo
              </label>
              <textarea
                id="espera-detail"
                value={detail ?? ''}
                onChange={(e) => setDetail(e.target.value)}
                rows={3}
                placeholder="Ej. Pendiente de repuesto del proveedor…"
                className={cn(
                  'mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:ring-2 focus:outline-none',
                  errors.detail
                    ? 'border-red-400 focus:ring-red-200'
                    : 'border-[#d7e0df] focus:border-[#0f766e] focus:ring-[#0f766e]/20',
                )}
              />
              {errors.detail && (
                <p className="mt-1 text-xs text-red-600">{errors.detail}</p>
              )}
            </div>
          )}

          {isUnauthenticated && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>Tu sesión ha expirado. Inicia sesión nuevamente.</span>
            </div>
          )}

          {apiError && !isUnauthenticated && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{apiError}</span>
            </div>
          )}

          {confirmMutation.isSuccess && (
            <div
              role="status"
              className="flex items-start gap-2 rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-700"
            >
              <Clock size={16} className="mt-0.5 shrink-0" />
              <span>Solicitud puesta en espera.</span>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" disabled={confirmMutation.isPending}>
              {confirmMutation.isPending ? 'Guardando…' : 'Guardar espera'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
