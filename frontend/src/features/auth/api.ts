import { apiFetch } from '@/api/client'
import type { User } from '@/api/types'

export type LoginPayload = {
  email: string
  password: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
  user: User
}

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function logout(): Promise<void> {
  await apiFetch<void>('/auth/logout', { method: 'POST' })
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/auth/me')
}
