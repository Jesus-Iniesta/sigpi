import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { exportarIndicadoresCsv, nombreDeArchivo } from '@/api/indicadores'

describe('exportarIndicadoresCsv (S5-11)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let descargado: string | null

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    URL.createObjectURL = vi.fn(() => 'blob:csv') as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn()
    descargado = null
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      descargado = this.download
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('pide el CSV con la sesión y lo guarda con el nombre del servidor', async () => {
    fetchMock.mockResolvedValue(
      new Response('folio,titulo\n', {
        status: 200,
        headers: {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition':
            'attachment; filename="indicadores_2026-11-01_2026-11-26.csv"',
        },
      }),
    )

    const nombre = await exportarIndicadoresCsv({
      desde: '2026-11-01',
      hasta: '2026-11-26',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain(
      '/indicadores/exportar.csv?desde=2026-11-01&hasta=2026-11-26',
    )
    expect(init).toMatchObject({ credentials: 'include' })
    expect(nombre).toBe('indicadores_2026-11-01_2026-11-26.csv')
    expect(descargado).toBe('indicadores_2026-11-01_2026-11-26.csv')
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('lanza ApiError si el servidor responde con error', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Rango inválido.' }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(
      exportarIndicadoresCsv({ desde: '2026-11-01', hasta: '2026-11-26' }),
    ).rejects.toBeInstanceOf(ApiError)
    expect(descargado).toBeNull()
  })

  it('usa un nombre por omisión si no llega Content-Disposition', () => {
    expect(nombreDeArchivo(null)).toBe('indicadores.csv')
    expect(
      nombreDeArchivo("attachment; filename*=UTF-8''r%C3%A9porte.csv"),
    ).toBe('réporte.csv')
  })
})
