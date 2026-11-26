type BarrasHorizontalesProps = {
  titulo: string
  datos: Record<string, number>
  /** Texto visible de cada llave (por ejemplo, el estatus en español). */
  etiqueta?: (llave: string) => string
}

/** Barras horizontales sencillas con HTML/CSS, de mayor a menor. */
export function BarrasHorizontales({
  titulo,
  datos,
  etiqueta = (llave) => llave,
}: BarrasHorizontalesProps) {
  const filas = Object.entries(datos).sort((a, b) => b[1] - a[1])
  const maximo = Math.max(1, ...filas.map(([, valor]) => valor))

  return (
    <section
      aria-label={titulo}
      className="rounded-xl border border-[#dce6e4] bg-white p-5"
    >
      <h2 className="mb-4 text-sm font-semibold text-[#17212b]">{titulo}</h2>
      {filas.length === 0 ? (
        <p className="text-sm text-[#718096]">Sin datos en el rango.</p>
      ) : (
        <ul className="space-y-3">
          {filas.map(([llave, valor]) => (
            <li key={llave} className="text-sm">
              <div className="mb-1 flex justify-between gap-3">
                <span className="truncate text-[#334155]">
                  {etiqueta(llave)}
                </span>
                <span className="font-semibold tabular-nums">{valor}</span>
              </div>
              <div className="h-2 rounded-full bg-[#eef3f2]">
                <div
                  className="h-2 rounded-full bg-[#0f766e]"
                  style={{ width: `${(valor / maximo) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
