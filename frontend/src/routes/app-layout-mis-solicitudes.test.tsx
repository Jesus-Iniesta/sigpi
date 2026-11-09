import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppLayout } from './app-layout'

const usuario = vi.hoisted(() => ({ roles: ['requester'] as string[] }))

vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'usuario-1',
      full_name: 'Persona de prueba',
      email: 'persona@example.test',
      roles: usuario.roles,
    },
    logout: vi.fn(),
  }),
}))

vi.mock('@/features/notificaciones/components/CampanaAvisos', () => ({
  CampanaAvisos: () => null,
}))

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<p>Inicio</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppLayout: «Mis solicitudes» (S4-02)', () => {
  it('aparece para el rol requester', () => {
    usuario.roles = ['requester']
    renderLayout()
    expect(
      screen.getByRole('link', { name: 'Mis solicitudes' }),
    ).toHaveAttribute('href', '/mis-solicitudes')
  })

  it('no aparece para otros roles', () => {
    usuario.roles = ['administrator', 'technician']
    renderLayout()
    expect(
      screen.queryByRole('link', { name: 'Mis solicitudes' }),
    ).not.toBeInTheDocument()
  })
})
