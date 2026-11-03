import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import {
  Activity,
  AlertCircle,
  Eye,
  EyeOff,
  Info,
  KeyRound,
  Lock,
  Mail,
} from 'lucide-react'
import { useAuth } from './auth-context'
import { Button } from '@/shared/ui/button'
import { ERROR_CODE_MESSAGES, isApiError } from '@/shared/lib/error-messages'
import { ErrorAlert } from '@/shared/ui/error-alert'
import { cn } from '@/shared/lib/utils'

const SESSION_EXPIRED_MESSAGE = 'Tu sesión expiró'

function loginErrorMessage(error: unknown): string | null {
  if (isApiError(error) && error.code === 'inactive_account') {
    return ERROR_CODE_MESSAGES.inactive_account
  }
  return null
}

export function LoginPage() {
  const { login, isAuthenticated, isLoading, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const offerPasswordRecovery =
    isApiError(error) &&
    error.code === 'invalid_credentials' &&
    error.extra.offer_password_recovery === true
  const customMessage = loginErrorMessage(error)

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-[#123b3a]">
      <div className="hidden flex-1 items-center justify-center lg:flex">
        <div className="max-w-md px-8 text-center">
          <div className="mx-auto grid size-16 place-items-center rounded-2xl bg-[#e6b85c]">
            <Activity size={32} strokeWidth={2.5} className="text-[#123b3a]" />
          </div>
          <h1 className="mt-6 text-4xl font-bold tracking-tight text-white">
            SIGPI
          </h1>
          <p className="mt-3 text-lg text-white/60">
            Sistema de Gestión de Peticiones Institucional
          </p>
          <p className="mt-6 text-sm leading-relaxed text-white/40">
            Accede con tu correo institucional para gestionar solicitudes,
            clasificar incidencias y administrar el catálogo de servicios.
          </p>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center bg-white lg:max-w-md lg:rounded-l-3xl">
        <div className="w-full max-w-sm px-8">
          <div className="mb-8 lg:hidden">
            <div className="grid size-12 place-items-center rounded-xl bg-[#e6b85c]">
              <Activity
                size={24}
                strokeWidth={2.5}
                className="text-[#123b3a]"
              />
            </div>
            <h1 className="mt-4 text-2xl font-bold text-[#17212b]">SIGPI</h1>
          </div>

          <h2 className="text-2xl font-bold tracking-tight text-[#17212b]">
            Iniciar sesión
          </h2>
          <p className="mt-1 text-sm text-[#718096]">
            Ingresa tus credenciales institucionales
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5" noValidate>
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-[#334155]"
              >
                Correo institucional
              </label>
              <div className="relative mt-1.5">
                <Mail
                  size={16}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[#94a3b8]"
                />
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="usuario@uaemex.mx"
                  className="w-full rounded-lg border border-[#d7e0df] bg-white py-2.5 pr-3 pl-9 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-[#334155]"
              >
                Contraseña
              </label>
              <div className="relative mt-1.5">
                <Lock
                  size={16}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[#94a3b8]"
                />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-lg border border-[#d7e0df] bg-white py-2.5 pr-10 pl-9 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute top-1/2 right-3 -translate-y-1/2 text-[#94a3b8] hover:text-[#52616b]"
                  aria-label={
                    showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'
                  }
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {sessionExpired && error === null && (
              <div
                role="status"
                className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800"
              >
                <Info size={16} className="mt-0.5 shrink-0" />
                <span>{SESSION_EXPIRED_MESSAGE}</span>
              </div>
            )}

            {error !== null &&
              (customMessage ? (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700"
                >
                  <AlertCircle size={16} className="mt-0.5 shrink-0" />
                  <span>{customMessage}</span>
                </div>
              ) : (
                <ErrorAlert error={error} fallback="Error al iniciar sesión." />
              ))}

            {offerPasswordRecovery && (
              <div
                role="status"
                className="flex items-start gap-2 rounded-lg bg-[#eef6f5] px-3 py-2.5 text-sm text-[#0f4f4a]"
              >
                <KeyRound size={16} className="mt-0.5 shrink-0" />
                <span>
                  Has superado el número de intentos permitidos. ¿Olvidaste tu
                  contraseña? Solicita su recuperación al administrador del
                  sistema.
                </span>
              </div>
            )}

            <Button
              type="submit"
              disabled={isSubmitting || !email || !password}
              className={cn('w-full py-2.5', isSubmitting && 'opacity-70')}
            >
              {isSubmitting ? 'Ingresando…' : 'Ingresar'}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-[#94a3b8]">
            Sistema de gestión de peticiones · UAEM
          </p>
        </div>
      </div>
    </div>
  )
}
