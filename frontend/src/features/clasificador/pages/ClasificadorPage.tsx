import { useState } from 'react'
import {
  BrainCircuit,
  CheckCircle2,
  RefreshCw,
  SlidersHorizontal,
} from 'lucide-react'
import {
  UMBRAL_MAXIMO,
  UMBRAL_MINIMO,
  UMBRAL_PASO,
  type EstadoClasificador,
  type ReentrenamientoResult,
} from '@/api/clasificador'
import { Button } from '@/shared/ui/button'
import { ErrorAlert } from '@/shared/ui/error-alert'
import {
  useEstadoClasificador,
  useGuardarUmbral,
  useReentrenarClasificador,
} from '../use-clasificador'

const cardClass = 'rounded-xl border border-[#dce6e4] bg-white p-6 shadow-sm'

/** Convierte una proporción 0–1 en texto de porcentaje; «Sin medir» si es nula. */
function formatPorcentaje(value: number | null): string {
  if (value === null) return 'Sin medir'
  return `${(value * 100).toFixed(1)} %`
}

function formatFecha(value: string | null): string {
  if (!value) return 'Sin registro'
  return new Intl.DateTimeFormat('es-MX', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatUmbral(value: number): string {
  return value.toFixed(2)
}

function EstadoCard({ estado }: { estado: EstadoClasificador }) {
  const items = [
    { label: 'Versión', value: estado.version },
    { label: 'Ejemplos de entrenamiento', value: String(estado.ejemplos) },
    { label: 'Exactitud', value: formatPorcentaje(estado.exactitud) },
    { label: 'Entrenado el', value: formatFecha(estado.entrenado_en) },
    {
      label: 'Correcciones pendientes',
      value: String(estado.correcciones_pendientes),
    },
    {
      label: `Enviadas a «Por revisar» (últimos ${estado.dias_recientes} días)`,
      value: formatPorcentaje(estado.proporcion_por_revisar),
    },
  ]

  return (
    <section className={cardClass} aria-labelledby="estado-clasificador">
      <div className="flex items-center gap-2">
        <BrainCircuit size={18} className="text-[#0f766e]" />
        <h2 id="estado-clasificador" className="text-lg font-bold">
          Estado del modelo
        </h2>
      </div>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-[#f5f7f8] p-4">
            <dt className="text-xs font-medium text-[#718096]">{label}</dt>
            <dd className="mt-1 text-xl font-semibold text-[#17212b]">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function UmbralCard({ umbralActual }: { umbralActual: number }) {
  const [umbral, setUmbral] = useState(umbralActual)
  const guardar = useGuardarUmbral()

  const onChange = (raw: string) => {
    const value = Number(raw)
    if (!Number.isNaN(value)) setUmbral(value)
  }

  return (
    <section className={cardClass} aria-labelledby="umbral-clasificador">
      <div className="flex items-center gap-2">
        <SlidersHorizontal size={18} className="text-[#0f766e]" />
        <h2 id="umbral-clasificador" className="text-lg font-bold">
          Umbral de confianza
        </h2>
      </div>
      <p className="mt-2 text-sm text-[#718096]">
        Un umbral más alto envía más solicitudes a revisión humana; uno más bajo
        acepta más clasificaciones automáticas.
      </p>
      <form
        className="mt-5 flex flex-wrap items-end gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          guardar.mutate(umbral)
        }}
      >
        <label className="flex-1 text-sm font-medium text-[#334155]">
          Umbral
          <input
            type="range"
            min={UMBRAL_MINIMO}
            max={UMBRAL_MAXIMO}
            step={UMBRAL_PASO}
            value={umbral}
            onChange={(event) => onChange(event.target.value)}
            className="mt-2 block w-full accent-[#0f766e]"
            disabled={guardar.isPending}
          />
        </label>
        <label className="text-sm font-medium text-[#334155]">
          Valor
          <input
            type="number"
            min={UMBRAL_MINIMO}
            max={UMBRAL_MAXIMO}
            step={UMBRAL_PASO}
            value={umbral}
            onChange={(event) => onChange(event.target.value)}
            className="mt-1.5 block h-10 w-24 rounded-lg border border-[#dce6e4] bg-[#fafcfc] px-3 outline-none focus:border-[#0f766e]"
            disabled={guardar.isPending}
          />
        </label>
        <Button type="submit" disabled={guardar.isPending}>
          {guardar.isPending ? 'Guardando…' : 'Guardar umbral'}
        </Button>
      </form>
      {guardar.isSuccess && (
        <p
          role="status"
          className="mt-4 flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-700"
        >
          <CheckCircle2 size={16} />
          Umbral actualizado de {formatUmbral(
            guardar.data.umbral_anterior,
          )} a {formatUmbral(guardar.data.umbral)}.
        </p>
      )}
      {guardar.isError && (
        <ErrorAlert
          className="mt-4"
          error={guardar.error}
          fallback="No se pudo guardar el umbral."
        />
      )}
    </section>
  )
}

function ResultadoReentrenamiento({
  resultado,
}: {
  resultado: ReentrenamientoResult
}) {
  return (
    <div
      role="status"
      className={
        resultado.activado
          ? 'mt-4 rounded-lg bg-green-50 p-4 text-sm text-green-800'
          : 'mt-4 rounded-lg bg-amber-50 p-4 text-sm text-amber-800'
      }
    >
      <p className="font-semibold">
        {resultado.activado
          ? `Versión ${resultado.version} activada`
          : `Versión ${resultado.version} no activada`}
      </p>
      <p className="mt-1">{resultado.mensaje}</p>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        <div>
          <dt className="text-xs opacity-75">Exactitud nueva</dt>
          <dd className="font-semibold">
            {formatPorcentaje(resultado.exactitud)}
          </dd>
        </div>
        <div>
          <dt className="text-xs opacity-75">
            Exactitud anterior ({resultado.version_anterior})
          </dt>
          <dd className="font-semibold">
            {formatPorcentaje(resultado.exactitud_anterior)}
          </dd>
        </div>
        <div>
          <dt className="text-xs opacity-75">Ejemplos</dt>
          <dd className="font-semibold">{resultado.ejemplos}</dd>
        </div>
        <div>
          <dt className="text-xs opacity-75">Correcciones incorporadas</dt>
          <dd className="font-semibold">
            {resultado.correcciones_incorporadas}
          </dd>
        </div>
      </dl>
    </div>
  )
}

function ReentrenarCard() {
  const [confirmando, setConfirmando] = useState(false)
  const reentrenar = useReentrenarClasificador()

  return (
    <section className={cardClass} aria-labelledby="reentrenar-clasificador">
      <div className="flex items-center gap-2">
        <RefreshCw size={18} className="text-[#0f766e]" />
        <h2 id="reentrenar-clasificador" className="text-lg font-bold">
          Reentrenamiento
        </h2>
      </div>
      <p className="mt-2 text-sm text-[#718096]">
        Entrena una versión nueva con el conjunto de datos y las correcciones
        pendientes. Solo se activa si su exactitud no empeora.
      </p>
      {!confirmando ? (
        <Button
          className="mt-5"
          onClick={() => setConfirmando(true)}
          disabled={reentrenar.isPending}
        >
          {reentrenar.isPending ? 'Reentrenando…' : 'Reentrenar modelo'}
        </Button>
      ) : (
        <div
          role="alertdialog"
          aria-labelledby="confirmar-reentrenar"
          className="mt-5 rounded-lg border border-[#dce6e4] bg-[#fafcfc] p-4"
        >
          <p id="confirmar-reentrenar" className="text-sm font-medium">
            ¿Reentrenar el modelo ahora? Puede tardar unos segundos.
          </p>
          <div className="mt-3 flex gap-3">
            <Button variant="secondary" onClick={() => setConfirmando(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => {
                setConfirmando(false)
                reentrenar.mutate()
              }}
            >
              Sí, reentrenar
            </Button>
          </div>
        </div>
      )}
      {reentrenar.isSuccess && (
        <ResultadoReentrenamiento resultado={reentrenar.data} />
      )}
      {reentrenar.isError && (
        <ErrorAlert
          className="mt-4"
          error={reentrenar.error}
          fallback="No se pudo reentrenar el modelo."
        />
      )}
    </section>
  )
}

export function ClasificadorPage() {
  const estado = useEstadoClasificador()

  return (
    <div className="space-y-6">
      <header>
        <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
          Clasificación
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Clasificador</h1>
        <p className="mt-2 max-w-2xl text-[#718096]">
          Consulta el estado del modelo, ajusta el umbral de confianza y
          reentrénalo con las correcciones de las personas revisoras.
        </p>
      </header>

      {estado.isPending && (
        <p role="status" className="text-sm text-[#718096]">
          Cargando estado del clasificador…
        </p>
      )}
      {estado.isError && (
        <ErrorAlert
          error={estado.error}
          fallback="No se pudo cargar el estado del clasificador."
        />
      )}
      {estado.isSuccess && (
        <>
          <EstadoCard estado={estado.data} />
          <UmbralCard umbralActual={estado.data.umbral} />
          <ReentrenarCard />
        </>
      )}
    </div>
  )
}
