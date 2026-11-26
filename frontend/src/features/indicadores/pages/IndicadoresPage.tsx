import { useState } from 'react'
import { CheckCircle2, Download } from 'lucide-react'
import type { ResumenIndicadores } from '@/api/indicadores'
import type { RequestStatus } from '@/api/seguimiento'
import { BarrasHorizontales } from '@/features/indicadores/components/BarrasHorizontales'
import { SerieDiaria } from '@/features/indicadores/components/SerieDiaria'
import {
  useExportarIndicadores,
  useResumenIndicadores,
} from '@/features/indicadores/use-indicadores'
import { rangoUltimosDias } from '@/features/indicadores/rango'
import {
  STATUS_LABELS,
  formatMinutes,
} from '@/features/requests/request-labels'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'

function etiquetaEstatus(llave: string): string {
  return STATUS_LABELS[llave as RequestStatus] ?? llave
}

function duracion(minutos: number): string {
  return formatMinutes(Math.round(minutos))
}

function Tarjeta({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div className="rounded-xl border border-[#dce6e4] bg-white p-5">
      <p className="text-sm text-[#718096]">{titulo}</p>
      <p className="mt-2 text-2xl font-bold tracking-tight">{valor}</p>
    </div>
  )
}

function Resumen({ datos }: { datos: ResumenIndicadores }) {
  return (
    <>
      <section
        aria-label="Tarjetas de indicadores"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"
      >
        <Tarjeta titulo="Total de solicitudes" valor={String(datos.total)} />
        <Tarjeta
          titulo="Cumplimiento del SLA"
          valor={`${datos.cumplimiento_sla.toFixed(1)} %`}
        />
        <Tarjeta
          titulo="Tiempo medio de primera respuesta"
          valor={duracion(datos.tiempo_medio_primera_respuesta_min)}
        />
        <Tarjeta
          titulo="Tiempo medio de resolución"
          valor={duracion(datos.tiempo_medio_resolucion_min)}
        />
        <Tarjeta
          titulo="Abiertas vencidas"
          valor={String(datos.abiertas_vencidas)}
        />
      </section>
      <div className="grid gap-4 lg:grid-cols-3">
        <BarrasHorizontales
          titulo="Por estatus"
          datos={datos.por_estatus}
          etiqueta={etiquetaEstatus}
        />
        <BarrasHorizontales
          titulo="Por prioridad"
          datos={datos.por_prioridad}
        />
        <BarrasHorizontales
          titulo="Por categoría"
          datos={datos.por_categoria}
        />
      </div>
      <SerieDiaria datos={datos.por_dia} />
    </>
  )
}

export function IndicadoresPage() {
  const [desde, setDesde] = useState(() => rangoUltimosDias(30).desde)
  const [hasta, setHasta] = useState(() => rangoUltimosDias(30).hasta)
  const [descargado, setDescargado] = useState<string | null>(null)

  const rangoValido = Boolean(desde) && Boolean(hasta) && desde <= hasta
  const rango = rangoValido ? { desde, hasta } : null
  const resumen = useResumenIndicadores(rango)
  const exportar = useExportarIndicadores()

  const aplicarAtajo = (dias: number) => {
    const nuevo = rangoUltimosDias(dias)
    setDesde(nuevo.desde)
    setHasta(nuevo.hasta)
  }

  const handleExportar = () => {
    if (!rango) return
    setDescargado(null)
    exportar.mutate(rango, { onSuccess: (nombre) => setDescargado(nombre) })
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Reportes
          </p>
          <h1 className="text-3xl font-bold tracking-tight">Indicadores</h1>
          <p className="mt-2 max-w-2xl text-[#718096]">
            Volumen, cumplimiento del SLA y tiempos de atención del periodo
            elegido.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={handleExportar}
          disabled={!rango || exportar.isPending}
        >
          <Download size={16} />
          {exportar.isPending ? 'Exportando…' : 'Exportar CSV'}
        </Button>
      </header>

      <section
        aria-label="Rango de fechas"
        className="flex flex-wrap items-end gap-3 rounded-xl border border-[#dce6e4] bg-white p-4"
      >
        <label className="flex flex-col gap-1 text-sm font-medium">
          Desde
          <input
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="rounded-lg border border-[#d7e0df] px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Hasta
          <input
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            className="rounded-lg border border-[#d7e0df] px-3 py-2"
          />
        </label>
        <Button type="button" variant="ghost" onClick={() => aplicarAtajo(7)}>
          7 días
        </Button>
        <Button type="button" variant="ghost" onClick={() => aplicarAtajo(30)}>
          30 días
        </Button>
      </section>

      {!rangoValido && (
        <p role="alert" className="text-sm text-red-700">
          {desde && hasta
            ? 'La fecha «desde» no puede ser posterior a «hasta».'
            : 'Elige ambas fechas del rango.'}
        </p>
      )}

      {descargado && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-700"
        >
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          <span>Se descargó {descargado}.</span>
        </div>
      )}

      {exportar.isError && (
        <ErrorAlert
          error={exportar.error}
          fallback="No se pudo exportar el CSV."
        />
      )}

      {rangoValido && resumen.isPending && (
        <p role="status" className="text-sm text-[#718096]">
          Cargando indicadores…
        </p>
      )}

      {rangoValido && resumen.isError && (
        <ErrorAlert
          error={resumen.error}
          fallback="No se pudieron cargar los indicadores."
        />
      )}

      {rangoValido &&
        resumen.data &&
        (resumen.data.total === 0 ? (
          <p className="rounded-xl border border-dashed border-[#d7e0df] bg-white p-8 text-center text-sm text-[#718096]">
            No hay solicitudes registradas en este rango.
          </p>
        ) : (
          <Resumen datos={resumen.data} />
        ))}
    </div>
  )
}
