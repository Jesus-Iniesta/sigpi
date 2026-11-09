import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getAvisos,
  getAvisosSinLeer,
  marcarAvisoLeido,
  marcarTodosLosAvisosLeidos,
} from '@/api/notificaciones'

/** Cada cuántos milisegundos se consulta al servidor (el aviso debe verse en menos de un minuto). */
export const INTERVALO_CONSULTA_MS = 30_000

const AVISOS_KEY = ['notificaciones'] as const
const CONTADOR_KEY = [...AVISOS_KEY, 'contador'] as const
const LISTA_KEY = [...AVISOS_KEY, 'lista'] as const

/** Contador de avisos sin leer; se refresca solo mientras la pantalla está abierta. */
export function useAvisosSinLeer() {
  return useQuery({
    queryKey: CONTADOR_KEY,
    queryFn: getAvisosSinLeer,
    refetchInterval: INTERVALO_CONSULTA_MS,
  })
}

/** Lista de avisos recientes; solo se consulta mientras la campana está abierta. */
export function useAvisos(activo: boolean) {
  return useQuery({
    queryKey: LISTA_KEY,
    queryFn: () => getAvisos({ limit: 20 }),
    enabled: activo,
    refetchInterval: activo ? INTERVALO_CONSULTA_MS : false,
  })
}

/** Marcar un aviso como leído refresca la lista y el contador. */
export function useMarcarAvisoLeido() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => marcarAvisoLeido(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AVISOS_KEY }),
  })
}

export function useMarcarTodosLeidos() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => marcarTodosLosAvisosLeidos(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AVISOS_KEY }),
  })
}
