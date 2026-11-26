import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getEstadoClasificador,
  guardarUmbral,
  reentrenarClasificador,
} from '@/api/clasificador'

const estadoKey = ['clasificador', 'estado'] as const

export function useEstadoClasificador() {
  return useQuery({ queryKey: estadoKey, queryFn: getEstadoClasificador })
}

export function useGuardarUmbral() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: guardarUmbral,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: estadoKey }),
  })
}

export function useReentrenarClasificador() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: reentrenarClasificador,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: estadoKey }),
  })
}
