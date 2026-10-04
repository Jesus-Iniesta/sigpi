const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Keep the status-based message when the server response is not JSON.
    }
    throw new Error(detail)
  }

  return response.json() as Promise<T>
}
