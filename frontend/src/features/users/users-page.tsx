import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, Plus, Search, ShieldCheck, UserRound } from 'lucide-react'
import {
  createUser,
  deactivateUser,
  getUsers,
  type User,
  type UserRole,
  updateUser,
} from '@/api/usuarios'
import { Button } from '@/shared/ui/button'

const roles: { value: UserRole; label: string }[] = [
  { value: 'administrator', label: 'Administrador' },
  { value: 'service_manager', label: 'Gestor de servicios' },
  { value: 'support_agent', label: 'Agente de soporte' },
  { value: 'classifier', label: 'Clasificador' },
  { value: 'knowledge_manager', label: 'Gestor de conocimiento' },
  { value: 'auditor', label: 'Auditor' },
  { value: 'requester', label: 'Solicitante' },
]

const roleLabels = Object.fromEntries(roles.map((role) => [role.value, role.label])) as Record<
  UserRole,
  string
>

type UserForm = {
  institutional_id: string
  role: UserRole
  max_load: string
}

const emptyForm: UserForm = {
  institutional_id: '',
  role: 'requester',
  max_load: '',
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function UserFormFields({
  form,
  disabled,
  editing,
  onChange,
}: {
  form: UserForm
  disabled: boolean
  editing: boolean
  onChange: (field: keyof UserForm, value: string) => void
}) {
  return (
    <div className="space-y-4">
      {!editing && (
        <label className="block text-sm font-medium text-[#334155]">
          Cuenta institucional
          <input
            required
            value={form.institutional_id}
            onChange={(event) => onChange('institutional_id', event.target.value)}
            placeholder="Ej. uaem2026001"
            className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 outline-none focus:border-[#0f766e]"
            disabled={disabled}
          />
          <span className="mt-1 block text-xs font-normal text-[#87959c]">
            Se validará contra el directorio institucional.
          </span>
        </label>
      )}
      <label className="block text-sm font-medium text-[#334155]">
        Rol
        <select
          value={form.role}
          onChange={(event) => onChange('role', event.target.value)}
          className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 outline-none focus:border-[#0f766e]"
          disabled={disabled}
        >
          {roles.map((role) => (
            <option key={role.value} value={role.value}>
              {role.label}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm font-medium text-[#334155]">
        Carga máxima de solicitudes
        <input
          type="number"
          min="0"
          value={form.max_load}
          onChange={(event) => onChange('max_load', event.target.value)}
          placeholder="Sin límite"
          className="mt-1.5 h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 outline-none focus:border-[#0f766e]"
          disabled={disabled}
        />
      </label>
    </div>
  )
}

export function UsersPage() {
  const queryClient = useQueryClient()
  const usersQuery = useQuery({ queryKey: ['users'], queryFn: getUsers })
  const [search, setSearch] = useState('')
  const [form, setForm] = useState<UserForm>(emptyForm)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [formError, setFormError] = useState('')
  const [actionError, setActionError] = useState('')

  const refreshUsers = () =>
    queryClient.invalidateQueries({ queryKey: ['users'] })

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      void refreshUsers()
      setIsFormOpen(false)
      setForm(emptyForm)
    },
    onError: (error) =>
      setFormError(getErrorMessage(error, 'No fue posible registrar la cuenta.')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ userId, input }: { userId: string; input: Parameters<typeof updateUser>[1] }) =>
      updateUser(userId, input),
    onSuccess: () => {
      void refreshUsers()
      setIsFormOpen(false)
      setEditingUser(null)
    },
    onError: (error) =>
      setFormError(getErrorMessage(error, 'No fue posible actualizar el usuario.')),
  })

  const deactivateMutation = useMutation({
    mutationFn: deactivateUser,
    onSuccess: () => {
      setActionError('')
      void refreshUsers()
    },
    onError: (error) =>
      setActionError(getErrorMessage(error, 'No fue posible desactivar la cuenta.')),
  })

  const filteredUsers = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()
    if (!normalizedSearch) return usersQuery.data ?? []
    return (usersQuery.data ?? []).filter((user) =>
      [user.full_name, user.email, user.institutional_id].some((value) =>
        value.toLowerCase().includes(normalizedSearch),
      ),
    )
  }, [search, usersQuery.data])

  const openCreateForm = () => {
    setEditingUser(null)
    setForm(emptyForm)
    setFormError('')
    setIsFormOpen(true)
  }

  const openEditForm = (user: User) => {
    setEditingUser(user)
    setForm({
      institutional_id: user.institutional_id,
      role: user.roles[0] ?? 'requester',
      max_load: user.max_load?.toString() ?? '',
    })
    setFormError('')
    setIsFormOpen(true)
  }

  const closeForm = () => {
    if (createMutation.isPending || updateMutation.isPending) return
    setIsFormOpen(false)
    setEditingUser(null)
  }

  const submitForm = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormError('')
    const maxLoad = form.max_load ? Number(form.max_load) : null
    if (maxLoad !== null && (!Number.isInteger(maxLoad) || maxLoad < 0)) {
      setFormError('La carga máxima debe ser un número entero igual o mayor que cero.')
      return
    }

    if (editingUser) {
      updateMutation.mutate({
        userId: editingUser.id,
        input: { role: form.role, max_load: maxLoad },
      })
      return
    }

    createMutation.mutate({
      institutional_id: form.institutional_id.trim(),
      role: form.role,
      max_load: maxLoad,
    })
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Administración
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Usuarios</h1>
          <p className="mt-2 text-[#718096]">
            Administra las cuentas y los permisos de acceso a SIGPI.
          </p>
        </div>
        <Button onClick={openCreateForm}>
          <Plus size={17} />
          Nuevo usuario
        </Button>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {[
          { label: 'Cuentas activas', value: usersQuery.data?.length ?? 0, icon: UserRound },
          {
            label: 'Administradores',
            value: usersQuery.data?.filter((user) => user.roles.includes('administrator')).length ?? 0,
            icon: ShieldCheck,
          },
          { label: 'Resultados', value: filteredUsers.length, icon: Search },
        ].map(({ label, value, icon: Icon }) => (
          <article key={label} className="rounded-xl border border-[#dce6e4] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#718096]">{label}</p>
              <Icon size={18} className="text-[#0f766e]" />
            </div>
            <p className="mt-3 font-mono text-3xl font-bold">{value}</p>
          </article>
        ))}
      </section>

      <section className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
        <div className="flex flex-col gap-3 border-b border-[#edf2f1] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative max-w-sm flex-1">
            <Search size={16} className="absolute top-1/2 left-3 -translate-y-1/2 text-[#87959c]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] pr-3 pl-9 text-sm outline-none placeholder:text-[#a0adb2] focus:border-[#0f766e]"
              placeholder="Buscar por nombre, correo o cuenta..."
              aria-label="Buscar usuarios"
            />
          </div>
          <p className="text-sm text-[#87959c]">
            {filteredUsers.length} {filteredUsers.length === 1 ? 'usuario' : 'usuarios'}
          </p>
        </div>
        {actionError && <p className="border-b border-[#f3d4cf] bg-[#fff8f7] px-5 py-3 text-sm text-[#b54735]">{actionError}</p>}
        {usersQuery.isLoading && <p className="p-8 text-center text-sm text-[#718096]">Cargando usuarios...</p>}
        {usersQuery.isError && <p className="p-8 text-center text-sm text-[#b54735]">No fue posible cargar los usuarios.</p>}
        {!usersQuery.isLoading && !usersQuery.isError && filteredUsers.length === 0 && (
          <div className="p-10 text-center">
            <UserRound className="mx-auto text-[#b7c6c7]" size={28} />
            <p className="mt-3 font-medium">No hay usuarios que mostrar</p>
            <p className="mt-1 text-sm text-[#87959c]">
              {search ? 'Prueba con otra búsqueda.' : 'Registra la primera cuenta institucional.'}
            </p>
          </div>
        )}
        {filteredUsers.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-190 text-left text-sm">
              <thead className="bg-[#f8faf9] text-xs tracking-wide text-[#87959c] uppercase">
                <tr>
                  <th className="px-5 py-3 font-semibold">Usuario</th>
                  <th className="px-5 py-3 font-semibold">Rol</th>
                  <th className="px-5 py-3 font-semibold">Carga máxima</th>
                  <th className="px-5 py-3 font-semibold">Alta</th>
                  <th className="px-5 py-3 text-right font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#edf2f1]">
                {filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-[#fbfdfc]">
                    <td className="px-5 py-4">
                      <p className="font-semibold text-[#24343d]">{user.full_name}</p>
                      <p className="mt-1 text-xs text-[#87959c]">
                        {user.institutional_id} · {user.email}
                      </p>
                    </td>
                    <td className="px-5 py-4">
                      <span className="rounded-md bg-[#d9eee9] px-2 py-1 text-xs font-semibold text-[#0f766e]">
                        {user.roles.map((role) => roleLabels[role] ?? role).join(', ')}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-[#52616b]">{user.max_load ?? 'Sin límite'}</td>
                    <td className="px-5 py-4 text-[#87959c]">
                      {new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium' }).format(new Date(user.created_at))}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" onClick={() => openEditForm(user)}>Editar</Button>
                        <Button
                          variant="ghost"
                          aria-label={`Desactivar a ${user.full_name}`}
                          disabled={deactivateMutation.isPending}
                          onClick={() => {
                            if (window.confirm(`¿Desactivar la cuenta de ${user.full_name}?`)) {
                              deactivateMutation.mutate(user.id)
                            }
                          }}
                        >
                          <MoreHorizontal size={17} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {isFormOpen && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-[#123b3a]/35 p-5" role="presentation" onMouseDown={closeForm}>
          <form
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
            onSubmit={submitForm}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 className="text-xl font-bold">{editingUser ? 'Editar usuario' : 'Nuevo usuario'}</h2>
            <p className="mt-1 text-sm text-[#718096]">
              {editingUser ? editingUser.full_name : 'Registra una cuenta institucional en SIGPI.'}
            </p>
            <div className="mt-6">
              <UserFormFields
                form={form}
                disabled={isSaving}
                editing={Boolean(editingUser)}
                onChange={(field, value) => setForm((current) => ({ ...current, [field]: value }))}
              />
            </div>
            {formError && <p className="mt-4 text-sm text-[#b54735]">{formError}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <Button type="button" variant="secondary" onClick={closeForm} disabled={isSaving}>Cancelar</Button>
              <Button type="submit" disabled={isSaving}>{isSaving ? 'Guardando...' : 'Guardar'}</Button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
