// Roles con el permiso requests.assign (backend/app/core/permissions.py).
export const ASSIGN_ROLES = [
    'administrator',
    'service_manager',
    'support_agent',
]

/** `true` si alguno de los roles puede proponer y asignar técnicos. */
export function puedeAsignar(roles: string[] | undefined): boolean {
    return roles?.some((role) => ASSIGN_ROLES.includes(role)) ?? false
}
