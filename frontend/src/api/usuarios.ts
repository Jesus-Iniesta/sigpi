import { apiFetch } from '@/api/client'

export type UserRole =
  | 'administrator'
  | 'service_manager'
  | 'support_agent'
  | 'classifier'
  | 'knowledge_manager'
  | 'auditor'
  | 'requester'

export type User = {
  id: string
  institutional_id: string
  full_name: string
  email: string
  user_type: string
  support_level: string | null
  is_active: boolean
  max_load: number | null
  roles: UserRole[]
  created_at: string
  updated_at: string
}

export type CreateUserInput = {
  institutional_id: string
  role: UserRole
  max_load?: number | null
}

export type UpdateUserInput = {
  role?: UserRole
  max_load?: number | null
}

export function getUsers(): Promise<User[]> {
  return apiFetch<User[]>('/usuarios')
}

export function createUser(input: CreateUserInput): Promise<User> {
  return apiFetch<User>('/usuarios', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateUser(
  userId: string,
  input: UpdateUserInput,
): Promise<User> {
  return apiFetch<User>(`/usuarios/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function deactivateUser(userId: string): Promise<User> {
  return apiFetch<User>(`/usuarios/${userId}`, { method: 'DELETE' })
}
