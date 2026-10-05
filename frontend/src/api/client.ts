const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type ValidationError = {
  loc?: Array<string | number>
  msg?: string
}

function formatApiDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          const error = item as ValidationError
          const location = error.loc
            ?.filter((part) => part !== 'body')
            .join('.')
          return location && error.msg ? `${location}: ${error.msg}` : error.msg
        }
        return undefined
      })
      .filter((message): message is string => Boolean(message))
    if (messages.length > 0) return messages.join('; ')
  }
  return undefined
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
  })

  if (!response.ok) {
    let detail = `API request failed with status ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      detail = formatApiDetail(body.detail) ?? detail
    } catch {
      // Keep the status-based message when the server response is not JSON.
    }
    throw new Error(detail)
  }

  return response.json() as Promise<T>
}
