import type { ConteoDia } from '@/api/indicadores'

function formatoDia(fecha: string): string {
  const [anio, mes, dia] = fecha.split('-').map(Number)
  return new Date(anio, mes - 1, dia).toLocaleDateString('es-MX', {
    day: 'numeric',
    month: 'short',
  })
}

/** Solicitudes registradas por día, como barras verticales sencillas. */
export function SerieDiaria({ datos }: { datos: ConteoDia[] }) {
  const maximo = Math.max(1, ...datos.map((d) => d.total))

  return (
    <section
      aria-label="Solicitudes por día"
      className="rounded-xl border border-[#dce6e4] bg-white p-5"
    >
      <h2 className="mb-4 text-sm font-semibold text-[#17212b]">
        Solicitudes por día
      </h2>
      {datos.length === 0 ? (
        <p className="text-sm text-[#718096]">Sin datos en el rango.</p>
      ) : (
        <ol className="flex h-40 items-end gap-1 overflow-x-auto">
          {datos.map(({ fecha, total }) => (
            <li
              key={fecha}
              className="flex h-full min-w-3 flex-1 flex-col justify-end"
              title={`${formatoDia(fecha)}: ${total}`}
            >
              <span className="sr-only">{`${formatoDia(fecha)}: ${total}`}</span>
              <div
                className="rounded-t bg-[#0f766e]"
                style={{ height: `${(total / maximo) * 100}%` }}
              />
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
