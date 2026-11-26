import type { ComponentePuntaje } from '@/api/asignaciones'
import { cn } from '@/shared/lib/utils'

type PuntajeDesgloseProps = {
    componentes: ComponentePuntaje[]
    /** Puntaje total; si se indica, se muestra al final del desglose. */
    total?: number | null
    /** Texto original del desglose, por si no pudo separarse en componentes. */
    textoRespaldo?: string | null
    className?: string
}

/** 100 → «100»; 87.5 → «87.5». */
function formatPuntaje(total: number): string {
    return Number.isInteger(total) ? String(total) : total.toFixed(1)
}

/**
 * Desglose del puntaje de asignación (S5-12, HU-03.1): especialidad, turno y
 * carga con los puntos que aportó cada uno. Se usa para los candidatos de la
 * propuesta y para el técnico ya asignado.
 */
export function PuntajeDesglose({
    componentes,
    total,
    textoRespaldo,
    className,
}: PuntajeDesgloseProps) {
    if (componentes.length === 0) {
        if (!textoRespaldo) return null
        return (
            <p className={cn('text-xs text-[#52616b]', className)}>{textoRespaldo}</p>
        )
    }

    return (
        <div className={className}>
            <ul
                aria-label="Desglose del puntaje"
                className="space-y-1 text-xs text-[#52616b]"
            >
                {componentes.map((componente) => (
                    <li key={componente.concepto}>
                        <span className="font-semibold text-[#24343d]">
                            {componente.concepto}
                        </span>{' '}
                        ({componente.puntos > 0 ? '+' : ''}
                        {componente.puntos} pts): {componente.detalle}
                    </li>
                ))}
            </ul>
            {total !== null && total !== undefined && (
                <p className="mt-2 text-xs text-[#52616b]">
                    Puntaje total: <strong>{formatPuntaje(total)}</strong>
                </p>
            )}
        </div>
    )
}
