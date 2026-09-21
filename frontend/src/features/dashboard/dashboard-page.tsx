import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  FileText,
  ShieldCheck,
} from 'lucide-react'
import { getHealth } from '@/api/health'
import { Button } from '@/shared/ui/button'

const metrics = [
  {
    label: 'Solicitudes activas',
    value: '24',
    detail: '+8% frente al ciclo anterior',
    icon: FileText,
    color: 'text-[#0f766e]',
    bg: 'bg-[#d9eee9]',
  },
  {
    label: 'En seguimiento',
    value: '08',
    detail: '3 requieren atencion hoy',
    icon: Clock3,
    color: 'text-[#b7791f]',
    bg: 'bg-[#f8edcf]',
  },
  {
    label: 'Resueltas este mes',
    value: '41',
    detail: '92% dentro del SLA',
    icon: CheckCircle2,
    color: 'text-[#39735e]',
    bg: 'bg-[#e1f0e5]',
  },
]

export function DashboardPage() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    retry: 1,
  })

  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Panel de control
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-[#17212b] sm:text-4xl">
            Buenos dias, Administrador
          </h1>
          <p className="mt-2 text-[#718096]">
            Aqui tienes el pulso de la gestion institucional.
          </p>
        </div>
        <Button>
          <ArrowUpRight size={16} />
          Nueva solicitud
        </Button>
      </section>
      <section className="grid gap-4 md:grid-cols-3">
        {metrics.map(({ label, value, detail, icon: Icon, color, bg }) => (
          <article
            key={label}
            className="rounded-xl border border-[#dce6e4] bg-white p-5 shadow-[0_8px_24px_rgba(35,64,62,0.04)]"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-[#718096]">{label}</p>
                <p className="mt-3 font-mono text-3xl font-bold tracking-tight">
                  {value}
                </p>
              </div>
              <div
                className={`grid size-10 place-items-center rounded-lg ${bg} ${color}`}
              >
                <Icon size={19} />
              </div>
            </div>
            <p className="mt-4 text-xs text-[#718096]">{detail}</p>
          </article>
        ))}
      </section>
      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <article className="rounded-xl border border-[#dce6e4] bg-white p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold">Actividad reciente</h2>
              <p className="mt-1 text-sm text-[#718096]">
                Ultimas actualizaciones del sistema
              </p>
            </div>
            <Button variant="ghost">Ver todo</Button>
          </div>
          <div className="mt-6 divide-y divide-[#edf2f1]">
            {[
              'Solicitud de mantenimiento actualizada',
              'Nuevo registro de conocimiento creado',
              'SLA de infraestructura revisado',
            ].map((item, index) => (
              <div
                key={item}
                className="flex items-center gap-4 py-4 first:pt-0 last:pb-0"
              >
                <div className="grid size-9 shrink-0 place-items-center rounded-full bg-[#edf6f4] text-[#0f766e]">
                  <ShieldCheck size={17} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item}</p>
                  <p className="mt-1 text-xs text-[#87959c]">
                    Hace {index + 1} horas · Sistema SIGPI
                  </p>
                </div>
                <span className="size-2 rounded-full bg-[#e6b85c]" />
              </div>
            ))}
          </div>
        </article>
        <article className="rounded-xl bg-[#123b3a] p-6 text-white">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-white/70">Conexion API</p>
            <span
              className={`size-2 rounded-full ${health.isSuccess ? 'bg-[#8bd3a8]' : 'bg-[#e6b85c]'}`}
            />
          </div>
          <h2 className="mt-8 text-2xl font-bold">
            {health.isSuccess ? 'Sistema operativo' : 'Esperando backend'}
          </h2>
          <p className="mt-2 text-sm leading-6 text-white/60">
            {health.isSuccess
              ? `${health.data.service} responde correctamente.`
              : 'Inicia FastAPI en el puerto 8000 para verificar la conexion.'}
          </p>
          <div className="mt-8 border-t border-white/10 pt-4 text-xs text-white/45">
            GET /health · TanStack Query
          </div>
        </article>
      </section>
    </div>
  )
}
