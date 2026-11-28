import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { auditoriaQuery, getAuditoria } from '@/api/auditoria'

describe('getAuditoria (S5-21)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(
      async () =>
        new Response('[]', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function urlPedida(): URL {
    return new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost')
  }

  it('sin filtros pide /auditoria sin parámetros', async () => {
    await expect(getAuditoria()).resolves.toEqual([])
    const url = urlPedida()
    expect(url.pathname).toMatch(/\/auditoria$/)
    expect(url.search).toBe('')
  })

  it('envía tipo de entidad e identificador cuando tienen valor', async () => {
    await getAuditoria({ entity_type: 'catalog_category', entity_id: 'abc 1' })
    const params = urlPedida().searchParams
    expect(params.get('entity_type')).toBe('catalog_category')
    expect(params.get('entity_id')).toBe('abc 1')
  })

  it('omite los parámetros vacíos o solo con espacios', async () => {
    await getAuditoria({ entity_type: 'user', entity_id: '   ' })
    const params = urlPedida().searchParams
    expect(params.get('entity_type')).toBe('user')
    expect(params.has('entity_id')).toBe(false)
  })

  it('auditoriaQuery devuelve cadena vacía si no hay filtros con valor', () => {
    expect(auditoriaQuery({ entity_type: '', entity_id: '' })).toBe('')
    expect(auditoriaQuery({ entity_id: '42' })).toBe('?entity_id=42')
  })
})
