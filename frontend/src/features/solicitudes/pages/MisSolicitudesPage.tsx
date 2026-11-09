import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getMisSolicitudes } from '@/api/mis-solicitudes'
import {
  PRIORITY_STYLES,
  formatDateTime,
  statusLabel,
} from '@/features/requests/request-labels'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'
import { cn } from '@/shared/lib/utils'

/** Lista de solicitudes del solicitante y buscador por folio (HU-04.3). */
export function MisSolicitudesPage() {
  const navigate = useNavigate()
  const [folio, setFolio] = useState('')
  const solicitudes = useQuery({
    queryKey: ['mis-solicitudes'],
    queryFn: getMisSolicitudes,
  })

  const buscar = (evento: FormEvent<HTMLFormElement>) => {
    evento.preventDefault()
    const buscado = folio.trim()
    if (buscado) navigate(`/mis-solicitudes/${encodeURIComponent(buscado)}`)
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Mis solicitudes</h1>
        <p className="mt-1 text-sm text-[#718096]">
          Consulta el estatus de lo que has reportado.
        </p>
      </header>

      <form
        role="search"
        onSubmit={buscar}
        className="flex flex-col gap-3 rounded-xl border border-[#dce6e4] bg-white p-5 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <label
            htmlFor="buscar-folio"
            className="block text-sm font-medium text-[#334155]"
          >
            Buscar por folio
          </label>
          <input
            id="buscar-folio"
            value={folio}
            onChange={(evento) => setFolio(evento.target.value)}
            placeholder="Ej. SIG-0007"
            className="mt-1.5 w-full rounded-lg border border-[#d7e0df] bg-white px-3 py-2.5 text-sm text-[#17212b] placeholder:text-[#94a3b8] focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20 focus:outline-none"
          />
        </div>
        <Button type="submit" disabled={!folio.trim()}>
          <Search size={16} />
          Buscar
        </Button>
      </form>

      <section
        aria-labelledby="mis-solicitudes-lista"
        className="rounded-xl border border-[#dce6e4] bg-white"
      >
        <h2
          id="mis-solicitudes-lista"
          className="border-b border-[#edf2f1] px-6 py-4 text-lg font-bold"
        >
          Solicitudes registradas
        </h2>
        <div className="p-6">
          {solicitudes.isPending && (
            <p role="status" className="text-sm text-[#718096]">
              Cargando solicitudes…
            </p>
          )}
          {solicitudes.isError && (
            <ErrorAlert
              error={solicitudes.error}
              fallback="No se pudieron cargar tus solicitudes."
            />
          )}
          {solicitudes.isSuccess && solicitudes.data.length === 0 && (
            <p className="text-sm text-[#718096]">
              Todavía no has registrado solicitudes.
            </p>
          )}
          {solicitudes.isSuccess && solicitudes.data.length > 0 && (
            <ul className="divide-y divide-[#edf2f1]">
              {solicitudes.data.map((solicitud) => (
                <li key={solicitud.folio}>
                  <Link
                    to={`/mis-solicitudes/${encodeURIComponent(solicitud.folio)}`}
                    className="flex flex-col gap-2 py-3 hover:bg-[#f5f7f8] sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span>
                      <span className="block font-mono text-xs text-[#87959c]">
                        {solicitud.folio}
                      </span>
                      <span className="block text-sm font-semibold text-[#24343d]">
                        {solicitud.title}
                      </span>
                      <span className="block text-xs text-[#87959c]">
                        {formatDateTime(solicitud.created_at)}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      {solicitud.priority && (
                        <span
                          className={cn(
                            'inline-flex rounded-md px-2 py-1 text-xs font-bold',
                            PRIORITY_STYLES[solicitud.priority],
                          )}
                        >
                          {solicitud.priority}
                        </span>
                      )}
                      <span className="inline-flex rounded-md bg-[#d9eee9] px-2 py-1 text-xs font-bold text-[#0f766e]">
                        {statusLabel(solicitud.status)}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}
