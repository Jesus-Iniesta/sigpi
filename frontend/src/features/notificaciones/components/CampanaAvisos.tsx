import { Bell, CheckCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Aviso } from '@/api/notificaciones'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'
import { cn } from '@/shared/lib/utils'
import {
  useAvisos,
  useAvisosSinLeer,
  useMarcarAvisoLeido,
  useMarcarTodosLeidos,
} from '../use-avisos'

const TOPE_CONTADOR = 99

function formatearFecha(fecha: string): string {
  return new Date(fecha).toLocaleString('es-MX', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

type AvisoItemProps = {
  aviso: Aviso
  onMarcarLeido: (id: string) => void
  deshabilitado: boolean
}

function AvisoItem({ aviso, onMarcarLeido, deshabilitado }: AvisoItemProps) {
  const importante = aviso.importance === 'high'
  return (
    <li
      className={cn(
        'border-b border-[#eef2f1] px-4 py-3 last:border-b-0',
        !aviso.is_read && 'bg-[#f0f9f7]',
        importante && !aviso.is_read && 'bg-[#fff8e8]',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <p
          className={cn(
            'text-sm text-[#17212b]',
            !aviso.is_read && 'font-semibold',
          )}
        >
          {importante && (
            <span className="mr-2 rounded bg-[#e6b85c] px-1.5 py-0.5 text-[10px] font-bold text-[#123b3a] uppercase">
              Importante
            </span>
          )}
          {aviso.subject}
        </p>
        {!aviso.is_read && (
          <Button
            type="button"
            variant="ghost"
            className="min-h-8 shrink-0 px-2 text-xs"
            disabled={deshabilitado}
            onClick={() => onMarcarLeido(aviso.id)}
            aria-label={`Marcar como leído: ${aviso.subject}`}
          >
            Marcar como leído
          </Button>
        )}
      </div>
      <p className="mt-1 text-sm text-[#52616b]">{aviso.body}</p>
      <p className="mt-1 text-xs text-[#718096]">
        {aviso.request_folio && <span>{aviso.request_folio} · </span>}
        {formatearFecha(aviso.created_at)}
      </p>
    </li>
  )
}

/** Campana de avisos del encabezado: contador de no leídos y lista (HU-07.1). */
export function CampanaAvisos() {
  const [abierta, setAbierta] = useState(false)
  const contenedor = useRef<HTMLDivElement>(null)
  const sinLeer = useAvisosSinLeer()
  const avisos = useAvisos(abierta)
  const marcarLeido = useMarcarAvisoLeido()
  const marcarTodos = useMarcarTodosLeidos()

  const total = sinLeer.data ?? 0
  const textoContador = total > TOPE_CONTADOR ? `${TOPE_CONTADOR}+` : total

  useEffect(() => {
    if (!abierta) return
    const alPulsar = (evento: MouseEvent) => {
      if (!contenedor.current?.contains(evento.target as Node)) {
        setAbierta(false)
      }
    }
    const alTeclear = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') setAbierta(false)
    }
    document.addEventListener('mousedown', alPulsar)
    document.addEventListener('keydown', alTeclear)
    return () => {
      document.removeEventListener('mousedown', alPulsar)
      document.removeEventListener('keydown', alTeclear)
    }
  }, [abierta])

  return (
    <div ref={contenedor} className="relative">
      <button
        type="button"
        onClick={() => setAbierta((valor) => !valor)}
        aria-expanded={abierta}
        aria-label={total > 0 ? `Avisos, ${total} sin leer` : 'Avisos'}
        className="relative rounded-full p-2 text-[#52616b] transition-colors hover:bg-[#e7efee] hover:text-[#17212b]"
      >
        <Bell size={20} />
        {total > 0 && (
          <span
            aria-hidden="true"
            className="absolute -top-0.5 -right-0.5 grid min-w-5 place-items-center rounded-full bg-[#b42318] px-1 text-[11px] leading-5 font-bold text-white"
          >
            {textoContador}
          </span>
        )}
      </button>

      {abierta && (
        <section
          aria-label="Lista de avisos"
          className="absolute right-0 z-20 mt-2 w-[min(24rem,calc(100vw-2.5rem))] overflow-hidden rounded-xl border border-[#dce6e4] bg-white shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-[#eef2f1] px-4 py-3">
            <h2 className="text-sm font-semibold text-[#17212b]">Avisos</h2>
            <Button
              type="button"
              variant="ghost"
              className="min-h-8 px-2 text-xs"
              disabled={total === 0 || marcarTodos.isPending}
              onClick={() => marcarTodos.mutate()}
            >
              <CheckCheck size={14} />
              Marcar todos como leídos
            </Button>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {avisos.isPending && (
              <p className="px-4 py-6 text-center text-sm text-[#718096]">
                Cargando avisos…
              </p>
            )}
            {avisos.isError && (
              <div className="p-3">
                <ErrorAlert
                  error={avisos.error}
                  fallback="No se pudieron cargar los avisos."
                />
              </div>
            )}
            {avisos.isSuccess && avisos.data.length === 0 && (
              <p className="px-4 py-6 text-center text-sm text-[#718096]">
                No tienes avisos.
              </p>
            )}
            {avisos.isSuccess && avisos.data.length > 0 && (
              <ul>
                {avisos.data.map((aviso) => (
                  <AvisoItem
                    key={aviso.id}
                    aviso={aviso}
                    onMarcarLeido={(id) => marcarLeido.mutate(id)}
                    deshabilitado={marcarLeido.isPending}
                  />
                ))}
              </ul>
            )}
            {(marcarLeido.isError || marcarTodos.isError) && (
              <div className="p-3">
                <ErrorAlert
                  error={marcarLeido.error ?? marcarTodos.error}
                  fallback="No se pudo actualizar el aviso."
                />
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
