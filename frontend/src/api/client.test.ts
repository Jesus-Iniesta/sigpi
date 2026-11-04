import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, setUnauthorizedHandler } from './client'
import { getErrorMessage } from '@/shared/lib/error-messages'

function mockFetchResponse(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function captureError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError)
    return error as ApiError
  }
  throw new Error('Se esperaba que la petición fallara')
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('apiFetch', () => {
  it('un 422 de validación produce ApiError con fieldErrors en español', async () => {
    mockFetchResponse(422, {
      detail: [
        {
          type: 'missing',
          loc: ['body', 'title'],
          msg: 'Field required',
          input: {},
        },
        {
          type: 'string_too_short',
          loc: ['body', 'physical_location'],
          msg: 'String should have at least 3 characters',
          input: 'A',
          ctx: { min_length: 3 },
        },
        {
          type: 'less_than_equal',
          loc: ['body', 'urgency'],
          msg: 'Input should be less than or equal to 3',
          input: 5,
          ctx: { le: 3 },
        },
      ],
      code: 'validation_error',
      request_id: 'req-422',
    })

    const error = await captureError(
      apiFetch('/solicitudes', { method: 'POST' }),
    )

    expect(error.status).toBe(422)
    expect(error.code).toBe('validation_error')
    expect(error.requestId).toBe('req-422')
    expect(error.fieldErrors).toEqual({
      title: 'Este campo es obligatorio',
      physical_location: 'Debe tener al menos 3 caracteres',
      urgency: 'Debe ser menor o igual que 3',
    })
    expect(getErrorMessage(error)).toBe('Revisa los campos marcados.')
  })

  it('un 500 produce un mensaje con el código de seguimiento', async () => {
    mockFetchResponse(500, {
      detail: 'Ocurrió un error interno. Intenta de nuevo más tarde.',
      code: 'internal_error',
      request_id: 'abc123',
    })

    const error = await captureError(apiFetch('/solicitudes'))

    expect(error.status).toBe(500)
    expect(error.requestId).toBe('abc123')
    expect(getErrorMessage(error)).toBe(
      'Ocurrió un error interno. Intenta de nuevo más tarde. Código de seguimiento: abc123',
    )
  })

  it('conserva el mensaje del servidor y el campo extra en errores de negocio', async () => {
    mockFetchResponse(401, {
      detail: 'Correo o contraseña incorrectos.',
      code: 'invalid_credentials',
      request_id: 'req-401',
      extra: { failed_attempts: 3, offer_password_recovery: true },
    })

    const error = await captureError(
      apiFetch('/auth/login', { method: 'POST' }),
    )

    expect(error.message).toBe('Correo o contraseña incorrectos.')
    expect(error.extra).toEqual({
      failed_attempts: 3,
      offer_password_recovery: true,
    })
    expect(error.fieldErrors).toEqual({})
    expect(getErrorMessage(error)).toBe('Correo o contraseña incorrectos.')
  })

  it('usa el mapa en español para códigos técnicos', async () => {
    mockFetchResponse(403, {
      detail: 'Forbidden',
      code: 'forbidden',
      request_id: 'req-403',
    })

    const error = await captureError(apiFetch('/usuarios'))

    expect(getErrorMessage(error)).toBe(
      'No tienes permiso para realizar esta acción.',
    )
  })

  it('avisa del 401 fuera de /auth/login, pero no en el login', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    const body = {
      detail: 'Debes iniciar sesión para continuar.',
      code: 'unauthenticated',
      request_id: 'req-1',
    }

    mockFetchResponse(401, body)
    await captureError(apiFetch('/auth/login', { method: 'POST' }))
    expect(handler).not.toHaveBeenCalled()

    mockFetchResponse(401, body)
    await captureError(apiFetch('/solicitudes'))
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('si la respuesta no es JSON conserva un mensaje basado en el estatus', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>', { status: 502 })),
    )

    const error = await captureError(apiFetch('/solicitudes'))

    expect(error.status).toBe(502)
    expect(error.code).toBeNull()
    expect(getErrorMessage(error)).toBe(
      'No fue posible completar la operación. Intenta de nuevo.',
    )
  })
})
