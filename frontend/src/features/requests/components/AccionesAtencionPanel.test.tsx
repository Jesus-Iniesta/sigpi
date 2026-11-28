import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RequestDetail } from '@/api/seguimiento'
import { AccionesAtencionPanel } from './AccionesAtencionPanel'

const authState = vi.hoisted(() => ({ roles: ['support_agent'] as string[] }))
vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: { id: 'usuario-1', full_name: 'Persona', roles: authState.roles },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const REQUEST = {
  id: '11111111-1111-4111-8111-111111111111',
  status: 'assigned',
} as RequestDetail

beforeEach(() => {
  authState.roles = ['support_agent']
})

describe('AccionesAtencionPanel', () => {
  it('se muestra a un técnico como sección «Atención»', () => {
    render(<AccionesAtencionPanel request={REQUEST} />)

    expect(screen.getByRole('region', { name: 'Atención' })).toBeInTheDocument()
  })

  it.each(['administrator', 'service_manager'])('se muestra a %s', (role) => {
    authState.roles = [role]
    render(<AccionesAtencionPanel request={REQUEST} />)

    expect(screen.getByRole('region', { name: 'Atención' })).toBeInTheDocument()
  })

  it('no se muestra a un solicitante', () => {
    authState.roles = ['requester']
    render(<AccionesAtencionPanel request={REQUEST} />)

    expect(
      screen.queryByRole('region', { name: 'Atención' }),
    ).not.toBeInTheDocument()
  })
})
