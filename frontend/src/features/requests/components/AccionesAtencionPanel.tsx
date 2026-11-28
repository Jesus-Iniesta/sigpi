import type { RequestDetail } from '@/api/seguimiento'
import { useAuth } from '@/features/auth/auth-context'
import { puedeAtender } from '@/features/requests/estados-atencion'

type AccionesAtencionPanelProps = {
  request: RequestDetail
}

/**
 * Acciones con las que el técnico atiende la solicitud (HU-04.1, HU-04.2).
 * Solo se muestra a quien puede atender; cada acción decide si aparece según
 * el estatus de la solicitud.
 */
export function AccionesAtencionPanel({ request }: AccionesAtencionPanelProps) {
  const { user } = useAuth()
  if (!puedeAtender(user?.roles)) return null

  return (
    <section
      aria-labelledby="detalle-acciones-atencion"
      className="rounded-xl border border-[#dce6e4] bg-white p-6"
    >
      <h2 id="detalle-acciones-atencion" className="text-lg font-bold">
        Atención
      </h2>
      {/* La clave reinicia el estado de las acciones al cambiar de solicitud. */}
      <div key={request.id} className="mt-4 flex flex-wrap gap-3">
        {/* Acciones: S5-16 a S5-20 */}
      </div>
    </section>
  )
}
