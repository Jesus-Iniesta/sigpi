import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { User } from '@/api/types'
import { AuthContext } from './auth-context'
import * as authApi from './api'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.getCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const resolvedUser = user ?? data ?? null

  const login = async (email: string, password: string) => {
    const result = await authApi.login({ email, password })
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
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
