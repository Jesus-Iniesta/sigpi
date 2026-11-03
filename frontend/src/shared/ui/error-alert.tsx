import { AlertCircle } from 'lucide-react'
import {
  getBaseErrorMessage,
  getTrackingCode,
} from '@/shared/lib/error-messages'
import { cn } from '@/shared/lib/utils'

type ErrorAlertProps = {
  error: unknown
  /** Texto si el error no trae un mensaje que mostrar. */
  fallback?: string
  className?: string
}

/** Muestra el mensaje de un error y, si existe, su código de seguimiento. */
export function ErrorAlert({ error, fallback, className }: ErrorAlertProps) {
  if (error === null || error === undefined) return null
  const trackingCode = getTrackingCode(error)

  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700',
        className,
      )}
    >
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <div>
        <p>{getBaseErrorMessage(error, fallback)}</p>
        {trackingCode && (
          <p className="mt-1 text-xs text-red-600">
            Código de seguimiento:{' '}
            <span className="font-mono select-all">{trackingCode}</span>
          </p>
        )}
      </div>
    </div>
  )
}
