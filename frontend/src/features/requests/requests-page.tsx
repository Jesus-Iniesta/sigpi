import { Filter, Plus, Search } from 'lucide-react'
import { Button } from '@/shared/ui/button'

type Priority = 'P1' | 'P2' | 'P3' | 'P4'

type RequestRow = {
  id: string
  title: string
  area: string
  priority: Priority
  status: string
  updated: string
}

const requests: RequestRow[] = [
  {
    id: 'SIG-024',
    title: 'Acceso a plataforma academica',
    area: 'Tecnologia',
    priority: 'P1',
    status: 'En progreso',
    updated: 'Hoy, 09:42',
  },
  {
    id: 'SIG-023',
    title: 'Mantenimiento de laboratorio',
    area: 'Infraestructura',
    priority: 'P2',
    status: 'Pendiente',
    updated: 'Ayer, 16:20',
  },
  {
    id: 'SIG-022',
    title: 'Actualizacion de catalogo',
    area: 'Administracion',
    priority: 'P3',
    status: 'En progreso',
    updated: 'Ayer, 11:08',
  },
  {
    id: 'SIG-021',
    title: 'Revision de permisos',
    area: 'Recursos humanos',
    priority: 'P4',
    status: 'Resuelta',
    updated: '18 sep, 14:35',
  },
]

const priorityStyles: Record<Priority, string> = {
  P1: 'bg-[#fce4df] text-[#b54735]',
  P2: 'bg-[#f8edcf] text-[#a56c14]',
  P3: 'bg-[#dceef0] text-[#28717a]',
  P4: 'bg-[#e8edf0] text-[#60717a]',
}

export function RequestsPage() {
  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-[#0f766e] uppercase">
            Gestion operativa
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Solicitudes
          </h1>
          <p className="mt-2 text-[#718096]">
            Consulta y prioriza las solicitudes institucionales.
          </p>
        </div>
        <Button>
          <Plus size={17} />
          Nueva solicitud
        </Button>
      </section>
      <section className="overflow-hidden rounded-xl border border-[#dce6e4] bg-white">
        <div className="flex flex-col gap-3 border-b border-[#edf2f1] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative max-w-sm flex-1">
            <Search
              size={16}
              className="absolute top-1/2 left-3 -translate-y-1/2 text-[#87959c]"
            />
            <input
              className="h-10 w-full rounded-lg border border-[#dce6e4] bg-[#fafcfc] pr-3 pl-9 text-sm outline-none placeholder:text-[#a0adb2] focus:border-[#0f766e]"
              placeholder="Buscar solicitudes..."
            />
          </div>
          <Button variant="secondary">
            <Filter size={16} />
            Filtrar
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-175 text-left text-sm">
            <thead className="bg-[#f8faf9] text-xs tracking-wide text-[#87959c] uppercase">
              <tr>
                <th className="px-5 py-3 font-semibold">Solicitud</th>
                <th className="px-5 py-3 font-semibold">Area</th>
                <th className="px-5 py-3 font-semibold">Prioridad</th>
                <th className="px-5 py-3 font-semibold">Estado</th>
                <th className="px-5 py-3 font-semibold">Actualizada</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#edf2f1]">
              {requests.map((request) => (
                <tr key={request.id} className="hover:bg-[#fbfdfc]">
                  <td className="px-5 py-4">
                    <p className="font-semibold text-[#24343d]">
                      {request.title}
                    </p>
                    <p className="mt-1 font-mono text-xs text-[#87959c]">
                      {request.id}
                    </p>
                  </td>
                  <td className="px-5 py-4 text-[#52616b]">{request.area}</td>
                  <td className="px-5 py-4">
                    <span
                      className={`inline-flex rounded-md px-2 py-1 text-xs font-bold ${priorityStyles[request.priority]}`}
                    >
                      {request.priority}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-[#52616b]">{request.status}</td>
                  <td className="px-5 py-4 text-[#87959c]">
                    {request.updated}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
