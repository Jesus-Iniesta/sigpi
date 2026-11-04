import {
  translateValidationError,
  type ValidationErrorItem,
} from '@/shared/lib/error-messages'

const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type ErrorBody = {
  detail?: unknown
  code?: unknown
  request_id?: unknown
  extra?: unknown
}

/**
 * Error que lanza `apiFetch` cuando el servidor responde con un estatus de error.
 *
 * Conserva el cuerpo uniforme del backend (`detail`, `code`, `request_id`, `extra`) para que
 * cada pantalla decida qué mostrar sin depender del texto.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly requestId: string | null
  readonly extra: Record<string, unknown>
  /** Errores de validación por campo (llave: última parte de `loc`, sin `body`). */
  readonly fieldErrors: Record<string, string>
  /** Lista original de errores de validación de Pydantic, si la hubo. */
  readonly validationErrors: ValidationErrorItem[]

  constructor(
    status: number,
    message: string,
    options: {
      code?: string | null
      requestId?: string | null
      extra?: Record<string, unknown>
      validationErrors?: ValidationErrorItem[]
      fieldErrors?: Record<string, string>
    } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = options.code ?? null
    this.requestId = options.requestId ?? null
    this.extra = options.extra ?? {}
    this.validationErrors = options.validationErrors ?? []
    this.fieldErrors = options.fieldErrors ?? {}
  }
}

type UnauthorizedHandler = (error: ApiError) => void

let unauthorizedHandler: UnauthorizedHandler | null = null

/**
 * Registra quién atiende un `401` fuera de `/auth/login` (sesión vencida).
 * Devuelve una función para quitar el registro.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler
  return () => {
    if (unauthorizedHandler === handler) unauthorizedHandler = null
  }
}

function isValidationItem(item: unknown): item is ValidationErrorItem {
  return Boolean(item) && typeof item === 'object'
}

function formatApiDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (isValidationItem(item)) {
          const location = item.loc?.filter((part) => part !== 'body').join('.')
          return location && item.msg ? `${location}: ${item.msg}` : item.msg
        }
        return undefined
      })
      .filter((message): message is string => Boolean(message))
    if (messages.length > 0) return messages.join('; ')
  }
  return undefined
}

function buildFieldErrors(
  items: ValidationErrorItem[],
): Record<string, string> {
  const fieldErrors: Record<string, string> = {}
  for (const item of items) {
    const parts = (item.loc ?? []).filter((part) => part !== 'body')
    const key = parts.at(-1)
    if (key === undefined) continue
    const name = String(key)
    // Si un campo trae varios errores, se muestra el primero.
    if (!(name in fieldErrors))
      fieldErrors[name] = translateValidationError(item)
  }
  return fieldErrors
}

async function buildApiError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {}
  try {
    body = (await response.json()) as ErrorBody
  } catch {
    // El servidor no respondió JSON: se conserva el mensaje basado en el estatus.
  }

  const code = typeof body.code === 'string' ? body.code : null
  const validationErrors =
    code === 'validation_error' && Array.isArray(body.detail)
      ? body.detail.filter(isValidationItem)
      : []

  return new ApiError(
    response.status,
    formatApiDetail(body.detail) ??
      `API request failed with status ${response.status}`,
    {
      code,
      requestId: typeof body.request_id === 'string' ? body.request_id : null,
      extra:
        body.extra && typeof body.extra === 'object'
          ? (body.extra as Record<string, unknown>)
          : {},
      validationErrors,
      fieldErrors: buildFieldErrors(validationErrors),
    },
  )
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers)

  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    const error = await buildApiError(response)
    if (error.status === 401 && !path.startsWith('/auth/login')) {
      unauthorizedHandler?.(error)
    }
    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}
