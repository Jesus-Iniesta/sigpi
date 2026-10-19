import { useMutation } from '@tanstack/react-query'
import {
  createRequest,
  type CreateRequestInput,
  type Request,
} from '@/api/solicitudes'

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
    error: mutation.error?.message ?? null,
  }
}
