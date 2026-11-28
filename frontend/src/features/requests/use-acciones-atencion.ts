import { useMutation, useQueryClient } from '@tanstack/react-query'
import { SOLICITUDES_LISTA_KEY } from '@/features/requests/use-solicitudes'

/**
 * Ejecuta una acción de atención sobre la solicitud (iniciar, diagnosticar,
 * resolver, reanudar o confirmar el cierre). Al terminar bien refresca el
 * detalle de la solicitud (con su bitácora) y el listado de solicitudes.
 *
 * `fn` recibe el id de la solicitud y las variables que se pasen a `mutate`.
 */
export function useAccionAtencion<TResult, TVariables = void>(
  requestId: string,
  fn: (requestId: string, variables: TVariables) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  return useMutation<TResult, Error, TVariables>({
    mutationFn: (variables) => fn(requestId, variables),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['solicitudes', requestId] }),
        queryClient.invalidateQueries({ queryKey: SOLICITUDES_LISTA_KEY }),
      ]),
  })
}
