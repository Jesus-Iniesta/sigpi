import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  confirmarCierre,
  iniciarAtencion,
  registrarDiagnostico,
  resolverSolicitud,
} from './seguimiento'
import { reanudarSolicitud } from './solicitudes'

const REQUEST_ID = '11111111-1111-4111-8111-111111111111'
const RESPUESTA = { id: REQUEST_ID, status: 'in_progress' }

function mockFetch() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(RESPUESTA), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return {
    url,
    method: init.method,
    body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('acciones de atención', () => {
  it('iniciarAtencion hace POST a /iniciar sin cuerpo', async () => {
    const fetchMock = mockFetch()

    await expect(iniciarAtencion(REQUEST_ID)).resolves.toEqual(RESPUESTA)

    const call = lastCall(fetchMock)
    expect(call.url).toMatch(new RegExp(`/solicitudes/${REQUEST_ID}/iniciar$`))
    expect(call.method).toBe('POST')
    expect(call.body).toBeUndefined()
  })

  it('registrarDiagnostico envía el diagnóstico', async () => {
    const fetchMock = mockFetch()

    await registrarDiagnostico(REQUEST_ID, 'Cable dañado')

    const call = lastCall(fetchMock)
    expect(call.url).toMatch(
      new RegExp(`/solicitudes/${REQUEST_ID}/diagnostico$`),
    )
    expect(call.method).toBe('POST')
    expect(call.body).toEqual({ diagnosis: 'Cable dañado' })
  })

  it('resolverSolicitud envía la solución y el diagnóstico', async () => {
    const fetchMock = mockFetch()

    await resolverSolicitud(REQUEST_ID, 'Se cambió el cable', 'Cable dañado')

    const call = lastCall(fetchMock)
    expect(call.url).toMatch(new RegExp(`/solicitudes/${REQUEST_ID}/resolver$`))
    expect(call.method).toBe('POST')
    expect(call.body).toEqual({
      solution: 'Se cambió el cable',
      diagnosis: 'Cable dañado',
    })
  })

  it.each([undefined, null, '', '   '])(
    'resolverSolicitud omite el diagnóstico vacío (%j)',
    async (diagnosis) => {
      const fetchMock = mockFetch()

      await resolverSolicitud(REQUEST_ID, 'Se cambió el cable', diagnosis)

      expect(lastCall(fetchMock).body).toEqual({
        solution: 'Se cambió el cable',
      })
    },
  )

  it('confirmarCierre envía las notas', async () => {
    const fetchMock = mockFetch()

    await confirmarCierre(REQUEST_ID, 'Confirmado por teléfono')

    const call = lastCall(fetchMock)
    expect(call.url).toMatch(
      new RegExp(`/solicitudes/${REQUEST_ID}/confirmar$`),
    )
    expect(call.method).toBe('POST')
    expect(call.body).toEqual({ notes: 'Confirmado por teléfono' })
  })

  it.each([undefined, null, ''])(
    'confirmarCierre omite las notas vacías (%j)',
    async (notes) => {
      const fetchMock = mockFetch()

      await confirmarCierre(REQUEST_ID, notes)

      expect(lastCall(fetchMock).body).toEqual({})
    },
  )

  it('reanudarSolicitud hace POST a /reanudar sin cuerpo', async () => {
    const fetchMock = mockFetch()

    await reanudarSolicitud(REQUEST_ID)

    const call = lastCall(fetchMock)
    expect(call.url).toMatch(new RegExp(`/solicitudes/${REQUEST_ID}/reanudar$`))
    expect(call.method).toBe('POST')
    expect(call.body).toBeUndefined()
  })
})
