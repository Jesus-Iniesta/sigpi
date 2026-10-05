import { apiFetch } from '@/api/client'
import type {
  CreateUserInput,
  UpdateUserInput,
  User,
  UserRole,
} from '@/api/types'

export type { CreateUserInput, UpdateUserInput, User, UserRole }

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
