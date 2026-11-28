import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { useAccionAtencion } from './use-acciones-atencion'

const REQUEST_ID = '11111111-1111-4111-8111-111111111111'

function setup<TVariables>(
  fn: (requestId: string, variables: TVariables) => Promise<unknown>,
) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useAccionAtencion(REQUEST_ID, fn), {
    wrapper,
  })
  return { ...hook, invalidateSpy }
}

describe('useAccionAtencion', () => {
  it('llama a la acción con el id y refresca detalle y listado', async () => {
    const fn = vi.fn().mockResolvedValue({ id: REQUEST_ID })
    const { result, invalidateSpy } = setup<string>(fn)

    act(() => result.current.mutate('Cable dañado'))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fn).toHaveBeenCalledWith(REQUEST_ID, 'Cable dañado')
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['solicitudes', REQUEST_ID],
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['solicitudes', 'lista'],
    })
  })

  it('no refresca nada si la acción falla', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('Estado inválido'))
    const { result, invalidateSpy } = setup<void>(fn)

    act(() => result.current.mutate())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
