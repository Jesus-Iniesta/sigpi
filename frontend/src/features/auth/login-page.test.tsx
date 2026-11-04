import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from './auth-provider'
import { LoginPage } from './login-page'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const unauthenticated = {
  detail: 'Debes iniciar sesión para continuar.',
  code: 'unauthenticated',
  request_id: 'req-me',
}

function invalidCredentials(attempts: number) {
  return {
    detail: 'Correo o contraseña incorrectos.',
    code: 'invalid_credentials',
    request_id: `req-${attempts}`,
    extra: {
      failed_attempts: attempts,
      offer_password_recovery: attempts >= 3,
    },
  }
}

/** Simula el backend: /auth/me sin sesión y /auth/login según `loginResponses`. */
function mockBackend(loginResponses: Array<[number, unknown]>) {
  let attempt = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.endsWith('/auth/me')) return jsonResponse(401, unauthenticated)
      const [status, body] =
        loginResponses[Math.min(attempt, loginResponses.length - 1)]
      attempt += 1
      return jsonResponse(status, body)
    }),
  )
}

function renderLogin() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<p>Inicio</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Ingresar' }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoginPage', () => {
  it('tras tres contraseñas incorrectas ofrece recuperar la contraseña', async () => {
    mockBackend([
      [401, invalidCredentials(1)],
      [401, invalidCredentials(2)],
      [401, invalidCredentials(3)],
    ])
    renderLogin()
    const user = userEvent.setup()

    await user.type(
      screen.getByLabelText('Correo institucional'),
      'ana@uaemex.mx',
    )
    await user.type(screen.getByLabelText('Contraseña'), 'incorrecta')

    await submit(user)
    expect(
      await screen.findByText('Correo o contraseña incorrectos.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/Olvidaste tu contraseña/),
    ).not.toBeInTheDocument()

    await submit(user)
    await screen.findByText('Correo o contraseña incorrectos.')
    expect(
      screen.queryByText(/Olvidaste tu contraseña/),
    ).not.toBeInTheDocument()

    await submit(user)
    expect(
      await screen.findByText(/Olvidaste tu contraseña/),
    ).toBeInTheDocument()
  })

  it('con cuenta desactivada muestra el aviso para contactar al administrador', async () => {
    mockBackend([
      [
        403,
        {
          detail: 'La cuenta está desactivada.',
          code: 'inactive_account',
          request_id: 'req-403',
        },
      ],
    ])
    renderLogin()
    const user = userEvent.setup()

    await user.type(
      screen.getByLabelText('Correo institucional'),
      'ana@uaemex.mx',
    )
    await user.type(screen.getByLabelText('Contraseña'), 'ClaveSegura#2026')
    await submit(user)

    expect(
      await screen.findByText(
        'Tu cuenta está desactivada; contacta al administrador.',
      ),
    ).toBeInTheDocument()
  })
})
