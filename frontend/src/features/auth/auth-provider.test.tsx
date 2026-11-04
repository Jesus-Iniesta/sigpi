import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from '@/api/client'
import { AuthProvider } from './auth-provider'
import { LoginPage } from './login-page'
import { RequireAuth } from './require-auth'

const currentUser = {
  id: 'user-1',
  institutional_id: 'uaem2026001',
  full_name: 'Ana Martínez Soto',
  email: 'amartinez@uaemex.mx',
  user_type: 'student',
  support_level: null,
  is_active: true,
  max_load: null,
  roles: ['administrator'],
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:00:00Z',
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Pantalla protegida cualquiera que consulta la API. */
function ProtectedPage() {
  const query = useQuery({
    queryKey: ['solicitudes'],
    queryFn: () => apiFetch('/solicitudes'),
    retry: false,
  })
  return (
    <p>{query.isPending ? 'Cargando solicitudes' : 'Pantalla protegida'}</p>
  )
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/solicitudes']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route path="/solicitudes" element={<ProtectedPage />} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AuthProvider: sesión vencida', () => {
  it('un 401 en una pantalla protegida limpia la sesión y redirige a /login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/auth/me')) return jsonResponse(200, currentUser)
        return jsonResponse(401, {
          detail: 'Token inválido o expirado.',
          code: 'unauthenticated',
          request_id: 'req-401',
        })
      }),
    )

    renderApp()

    expect(
      await screen.findByRole('heading', { name: 'Iniciar sesión' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Tu sesión expiró')).toBeInTheDocument()
    expect(screen.queryByText('Pantalla protegida')).not.toBeInTheDocument()
  })

  it('sin sesión previa redirige a /login sin decir que la sesión expiró', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, {
          detail: 'Debes iniciar sesión para continuar.',
          code: 'unauthenticated',
          request_id: 'req-me',
        }),
      ),
    )

    renderApp()

    expect(
      await screen.findByRole('heading', { name: 'Iniciar sesión' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Tu sesión expiró')).not.toBeInTheDocument()
  })
})
