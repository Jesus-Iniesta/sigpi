import type { ApiError } from '@/api/client'

/** Un error de validación tal como lo entrega FastAPI/Pydantic en `detail`. */
export type ValidationErrorItem = {
  loc?: Array<string | number>
  msg?: string
  type?: string
  ctx?: Record<string, unknown>
}

export const GENERIC_ERROR_MESSAGE =
  'No fue posible completar la operación. Intenta de nuevo.'

/** Códigos genéricos que el backend asigna según el estatus HTTP. */
const GENERIC_CODE_MESSAGES: Record<string, string> = {
  unauthenticated: 'Debes iniciar sesión para continuar.',
  forbidden: 'No tienes permiso para realizar esta acción.',
  not_found: 'El recurso solicitado no existe.',
  conflict: 'La operación entra en conflicto con el estado actual del recurso.',
  internal_error: 'Ocurrió un error interno. Intenta de nuevo más tarde.',
  validation_error: 'Revisa los campos marcados.',
  bad_request: 'La solicitud no es válida.',
  method_not_allowed: 'La operación no está permitida.',
  unprocessable_entity: 'No fue posible procesar los datos enviados.',
  http_error: GENERIC_ERROR_MESSAGE,
}

/** Códigos de negocio: el backend ya redacta su mensaje en español. */
const BUSINESS_CODE_MESSAGES: Record<string, string> = {
  business_rule_violation: 'La operación incumple una regla de negocio.',
  invalid_credentials: 'Correo o contraseña incorrectos.',
  inactive_account: 'Tu cuenta está desactivada; contacta al administrador.',
  non_institutional_email: 'Usa tu correo institucional (@uaemex.mx).',
  catalog_option_not_allowed:
    'La opción elegida no está permitida en el catálogo.',
  sla_name_not_allowed: 'El nombre del acuerdo de servicio no está permitido.',
  sla_without_current_version:
    'El acuerdo de servicio no tiene una versión vigente.',
}

/** Mapa `code → mensaje en español`. */
export const ERROR_CODE_MESSAGES: Record<string, string> = {
  ...GENERIC_CODE_MESSAGES,
  ...BUSINESS_CODE_MESSAGES,
}

type ValidationTemplate = string | ((ctx: Record<string, unknown>) => string)

/** Mapa del `type` de Pydantic a español. */
export const VALIDATION_TYPE_MESSAGES: Record<string, ValidationTemplate> = {
  missing: 'Este campo es obligatorio',
  string_too_short: (ctx) =>
    ctx.min_length !== undefined
      ? `Debe tener al menos ${String(ctx.min_length)} caracteres`
      : 'El texto es demasiado corto',
  string_too_long: (ctx) =>
    ctx.max_length !== undefined
      ? `Debe tener como máximo ${String(ctx.max_length)} caracteres`
      : 'El texto es demasiado largo',
  greater_than: (ctx) =>
    ctx.gt !== undefined
      ? `Debe ser mayor que ${String(ctx.gt)}`
      : 'El valor es demasiado pequeño',
  less_than_equal: (ctx) =>
    ctx.le !== undefined
      ? `Debe ser menor o igual que ${String(ctx.le)}`
      : 'El valor es demasiado grande',
  value_error: 'El valor no es válido',
  uuid_parsing: 'El identificador no es válido',
  enum: 'Selecciona una opción válida',
}

const DEFAULT_VALIDATION_MESSAGE = 'El valor no es válido'

/** Traduce un error de validación de Pydantic a un texto en español. */
export function translateValidationError(item: ValidationErrorItem): string {
  const template = item.type ? VALIDATION_TYPE_MESSAGES[item.type] : undefined
  if (template === undefined) return DEFAULT_VALIDATION_MESSAGE
  return typeof template === 'string' ? template : template(item.ctx ?? {})
}

/** Se identifica por nombre para no importar `client.ts` en tiempo de ejecución. */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof Error && error.name === 'ApiError'
}

/** Código de seguimiento (`request_id`) que conviene mostrar, solo en errores internos. */
export function getTrackingCode(error: unknown): string | null {
  if (!isApiError(error) || !error.requestId) return null
  return error.code === 'internal_error' || error.status >= 500
    ? error.requestId
    : null
}

/**
 * Códigos cuyo `detail` nunca se muestra tal cual: es una lista técnica en inglés
 * (`validation_error`), es genérico a propósito (`internal_error`) o lo genera el
 * framework. Para ellos siempre se usa el mapa por código.
 *
 * El resto (`not_found`, `conflict`, `unprocessable_entity`, `bad_request` y los de
 * negocio) los lanzan los servicios con un mensaje ya redactado en español.
 */
const TECHNICAL_CODES = new Set([
  'validation_error',
  'internal_error',
  'unauthenticated',
  'forbidden',
  'method_not_allowed',
  'http_error',
])

function isBusinessCode(code: string): boolean {
  return !TECHNICAL_CODES.has(code)
}

/** Mensaje para la persona usuaria, sin el código de seguimiento. */
export function getBaseErrorMessage(
  error: unknown,
  fallback: string = GENERIC_ERROR_MESSAGE,
): string {
  if (isApiError(error)) {
    // 1. Código de negocio: el backend ya redacta el mensaje en español.
    if (error.code && isBusinessCode(error.code) && error.message) {
      return error.message
    }
    // 2. Mapa por código.
    if (error.code && ERROR_CODE_MESSAGES[error.code]) {
      return ERROR_CODE_MESSAGES[error.code]
    }
    // 3. Texto genérico.
    return fallback
  }
  if (error instanceof TypeError) {
    return 'No fue posible conectar con el servidor. Revisa tu conexión.'
  }
  // Errores que no vienen del servidor (p. ej. validaciones locales).
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/**
 * Devuelve el mensaje en español que se muestra para un error.
 *
 * Prioridad: mensaje del servidor si el código es de negocio → mapa por código →
 * texto genérico. En `internal_error` agrega el código de seguimiento.
 */
export function getErrorMessage(
  error: unknown,
  fallback: string = GENERIC_ERROR_MESSAGE,
): string {
  const message = getBaseErrorMessage(error, fallback)
  const trackingCode = getTrackingCode(error)
  return trackingCode
    ? `${message} Código de seguimiento: ${trackingCode}`
    : message
}

/** Errores por campo del servidor (vacío si el error no es de validación). */
export function getFieldErrors(error: unknown): Record<string, string> {
  return isApiError(error) ? error.fieldErrors : {}
}
