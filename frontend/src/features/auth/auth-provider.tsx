import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { setUnauthorizedHandler } from '@/api/client'
import type { User } from '@/api/types'
import { AuthContext } from './auth-context'
import * as authApi from './api'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.getCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const resolvedUser = user ?? data ?? null
  const hadSessionRef = useRef(false)
  useEffect(() => {
    hadSessionRef.current = resolvedUser !== null
  }, [resolvedUser])

  // Sesión vencida: cualquier 401 fuera de /auth/login limpia la sesión y lleva a /login.
  useEffect(() => {
    return setUnauthorizedHandler(() => {
      // Si nunca hubo sesión (p. ej. el primer /auth/me), RequireAuth ya redirige.
      if (!hadSessionRef.current) return
      hadSessionRef.current = false
      // El aviso vive en el contexto: el estado de navegación se perdería si
      // RequireAuth redirige primero.
      setSessionExpired(true)
      setUser(null)
      queryClient.setQueryData(['auth', 'me'], null)
      navigate('/login', { replace: true })
    })
  }, [navigate, queryClient])

  const login = async (email: string, password: string) => {
    const result = await authApi.login({ email, password })
    setSessionExpired(false)
    setUser(result.user)
    queryClient.setQueryData(['auth', 'me'], result.user)
  }

  const logout = async () => {
    await authApi.logout()
    setUser(null)
    queryClient.setQueryData(['auth', 'me'], null)
    queryClient.clear()
  }

  return (
    <AuthContext.Provider
      value={{
        user: resolvedUser,
        isLoading,
        isAuthenticated: resolvedUser !== null,
        sessionExpired,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
