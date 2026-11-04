import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppLayout } from './app-layout'

vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'admin-1',
      full_name: 'Administración de prueba',
      email: 'admin@example.test',
      roles: ['administrator'],
    },
    logout: vi.fn(),
  }),
}))

describe('AppLayout: menú lateral (COR-05)', () => {
  it('muestra «Tickets» en lugar de «SLA» y conserva la ruta /sla', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<p>Inicio</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Tickets' })).toHaveAttribute(
      'href',
      '/sla',
    )
    expect(container.textContent).not.toMatch(/\bSLA\b/)
  })
})
