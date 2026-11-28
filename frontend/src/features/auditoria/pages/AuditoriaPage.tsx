import { useState, type FormEvent } from 'react'
import { ChevronDown, ChevronRight, Search, X } from 'lucide-react'
import type { FiltrosAuditoria, RegistroAuditoria } from '@/api/auditoria'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'
import { useAuditoria } from '../use-auditoria'

const cardClass = 'rounded-xl border border-[#dce6e4] bg-white shadow-sm'
const inputClass =
  'mt-1.5 block h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 outline-none focus:border-[#0f766e]'

const formatoFecha = new Intl.DateTimeFormat('es-MX', {
  dateStyle: 'medium',
  timeStyle: 'medium',
})

function formatFecha(value: string): string {
  return formatoFecha.format(new Date(value))
}

function formatValores(valores: Record<string, unknown> | null): string {
  return valores === null ? 'Sin valores' : JSON.stringify(valores, null, 2)
}

function ValoresBloque({
  titulo,
  valores,
}: {
  titulo: string
  valores: Record<string, unknown> | null
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-bold tracking-wide text-[#52616b] uppercase">
        {titulo}
      </p>
      <pre
        aria-label={titulo}
        className="mt-1.5 overflow-x-auto rounded-lg bg-[#f5f7f8] p-3 font-mono text-xs text-[#17212b]"
      >
        {formatValores(valores)}
      </pre>
    </div>
  )
}

function FilaRegistro({ registro }: { registro: RegistroAuditoria }) {
  const [abierta, setAbierta] = useState(false)
  const detalleId = `auditoria-detalle-${registro.id}`
  const Icono = abierta ? ChevronDown : ChevronRight

  return (
    <>
      <tr className="border-t border-[#e7efee] align-top">
        <td className="px-2 py-3">
          <button
            type="button"
            onClick={() => setAbierta((valor) => !valor)}
            aria-expanded={abierta}
            aria-controls={detalleId}
            aria-label={
              abierta ? 'Ocultar valores del cambio' : 'Ver valores del cambio'
            }
            className="rounded-md p-1 text-[#52616b] hover:bg-[#e7efee]"
          >
            <Icono size={16} />
          </button>
        </td>
        <td className="px-3 py-3 whitespace-nowrap">
          {formatFecha(registro.created_at)}
        </td>
        <td className="px-3 py-3 font-medium">{registro.action}</td>
        <td className="px-3 py-3">{registro.entity_type}</td>
        <td className="px-3 py-3 font-mono text-xs break-all">
          {registro.entity_id}
        </td>
        <td className="px-3 py-3 font-mono text-xs break-all">
          {registro.actor_id ?? (
            <span className="font-sans text-sm">Sistema</span>
          )}
        </td>
        <td className="px-3 py-3 font-mono text-xs">
          {registro.ip_address ?? '—'}
        </td>
      </tr>
      {abierta && (
        <tr id={detalleId} className="bg-[#fafcfc]">
          <td colSpan={7} className="px-4 py-4">
            <div className="grid gap-4 md:grid-cols-2">
              <ValoresBloque
                titulo="Valores anteriores"
                valores={registro.old_values}
              />
              <ValoresBloque
                titulo="Valores nuevos"
                valores={registro.new_values}
              />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export function AuditoriaPage() {
  const [tipo, setTipo] = useState('')
  const [identificador, setIdentificador] = useState('')
  const [filtros, setFiltros] = useState<FiltrosAuditoria>({})
  const auditoria = useAuditoria(filtros)

  const tiposConocidos = Array.from(
    new Set((auditoria.data ?? []).map((registro) => registro.entity_type)),
  ).sort()
  const hayFiltros = Boolean(
    tipo || identificador || filtros.entity_type || filtros.entity_id,
  )

  const aplicar = (event: FormEvent) => {
    event.preventDefault()
    setFiltros({ entity_type: tipo.trim(), entity_id: identificador.trim() })
  }

  const limpiar = () => {
    setTipo('')
    setIdentificador('')
    setFiltros({})
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
          Control
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Auditoría</h1>
        <p className="mt-2 max-w-2xl text-[#718096]">
          Registro de solo lectura de los cambios administrativos
        </p>
      </header>

      <form
        className={`${cardClass} flex flex-wrap items-end gap-4 p-5`}
        aria-label="Filtros de auditoría"
        noValidate
        onSubmit={aplicar}
      >
        <label className="min-w-48 flex-1 text-sm font-medium text-[#334155]">
          Tipo de entidad
          <input
            type="text"
            list="auditoria-tipos"
            value={tipo}
            onChange={(event) => setTipo(event.target.value)}
            className={inputClass}
          />
          <datalist id="auditoria-tipos">
            {tiposConocidos.map((valor) => (
              <option key={valor} value={valor} />
            ))}
          </datalist>
        </label>
        <label className="min-w-48 flex-1 text-sm font-medium text-[#334155]">
          Identificador
          <input
            type="text"
            value={identificador}
            onChange={(event) => setIdentificador(event.target.value)}
            className={inputClass}
          />
        </label>
        <div className="flex gap-2">
          <Button type="submit" disabled={auditoria.isFetching}>
            <Search size={16} />
            Buscar
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={limpiar}
            disabled={!hayFiltros}
          >
            <X size={16} />
            Limpiar filtros
          </Button>
        </div>
      </form>

      {auditoria.isPending && (
        <p role="status" className="text-sm text-[#718096]">
          Cargando registros de auditoría…
        </p>
      )}
      {auditoria.isError && (
        <ErrorAlert
          error={auditoria.error}
          fallback="No se pudieron cargar los registros de auditoría."
        />
      )}
      {auditoria.isSuccess && auditoria.data.length === 0 && (
        <p
          role="status"
          className={`${cardClass} p-6 text-center text-sm text-[#718096]`}
        >
          No hay registros de auditoría con estos filtros.
        </p>
      )}
      {auditoria.isSuccess && auditoria.data.length > 0 && (
        <div className={`${cardClass} overflow-x-auto`}>
          <table className="w-full text-left text-sm">
            <thead className="bg-[#f5f7f8] text-xs font-semibold text-[#52616b] uppercase">
              <tr>
                <th scope="col" className="w-10 px-2 py-3">
                  <span className="sr-only">Detalle</span>
                </th>
                <th scope="col" className="px-3 py-3">
                  Fecha
                </th>
                <th scope="col" className="px-3 py-3">
                  Acción
                </th>
                <th scope="col" className="px-3 py-3">
                  Entidad
                </th>
                <th scope="col" className="px-3 py-3">
                  Identificador
                </th>
                <th scope="col" className="px-3 py-3">
                  Usuario
                </th>
                <th scope="col" className="px-3 py-3">
                  IP
                </th>
              </tr>
            </thead>
            <tbody>
              {auditoria.data.map((registro) => (
                <FilaRegistro key={registro.id} registro={registro} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
