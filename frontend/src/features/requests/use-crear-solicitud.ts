import { useMutation } from '@tanstack/react-query'
import {
  createRequest,
  type CreateRequestInput,
  type Request,
} from '@/api/solicitudes'
import { getErrorMessage, getFieldErrors } from '@/shared/lib/error-messages'

/**
 * Registra una solicitud de soporte (HU-01.1).
 * Expone la solicitud creada para mostrar el acuse con su folio.
 */
export function useCrearSolicitud() {
  const mutation = useMutation<Request, Error, CreateRequestInput>({
    mutationFn: createRequest,
  })

  return {
    crear: mutation.mutate,
    solicitud: mutation.data ?? null,
    isPending: mutation.isPending,
    error: mutation.error ? getErrorMessage(mutation.error) : null,
    /** Errores de validación del servidor por campo (COR-07). */
    fieldErrors: getFieldErrors(mutation.error),
    errorStatus:
      mutation.error && 'status' in mutation.error
        ? (mutation.error.status as number)
        : null,
  }
}
