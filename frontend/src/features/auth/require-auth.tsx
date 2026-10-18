import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './auth-context'

type RequireAuthProps = {
  requiredRoles?: string[]
}

export function RequireAuth({ requiredRoles }: RequireAuthProps) {
  const { user, isLoading, isAuthenticated } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f5f7f8]">
        <div className="flex flex-col items-center gap-3">
          <div className="size-8 animate-spin rounded-full border-2 border-[#0f766e] border-t-transparent" />
          <p className="text-sm text-[#718096]">Cargando sesión…</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (requiredRoles && requiredRoles.length > 0) {
    const hasRole = user!.roles.some((role) => requiredRoles.includes(role))
    if (!hasRole) {
      return <Navigate to="/" replace />
    }
  }

  return <Outlet />
}
