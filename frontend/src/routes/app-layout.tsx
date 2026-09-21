import {
  Activity,
  ClipboardList,
  LayoutDashboard,
  Menu,
  Settings2,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/shared/lib/utils'

const navigation = [
  { label: 'Resumen', to: '/', icon: LayoutDashboard, end: true },
  { label: 'Solicitudes', to: '/solicitudes', icon: ClipboardList },
]

export function AppLayout() {
  return (
    <div className="min-h-screen bg-[#f5f7f8] text-[#17212b]">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-[#dce6e4] bg-[#123b3a] text-white lg:flex lg:flex-col">
        <div className="flex h-20 items-center gap-3 border-b border-white/10 px-7">
          <div className="grid size-9 place-items-center rounded-lg bg-[#e6b85c] text-[#123b3a]">
            <Activity size={20} strokeWidth={2.5} />
          </div>
          <div>
            <p className="font-semibold tracking-tight">SIGPI</p>
            <p className="text-xs text-white/55">Gestion institucional</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-7">
          <p className="px-4 pb-3 text-[10px] font-bold tracking-[0.18em] text-white/40 uppercase">
            Espacio de trabajo
          </p>
          {navigation.map(({ label, to, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium text-white/65 transition-colors hover:bg-white/10 hover:text-white',
                  isActive && 'bg-[#0f766e] text-white shadow-sm',
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 p-5">
          <div className="flex items-center gap-3 rounded-lg bg-white/5 p-3">
            <div className="grid size-8 place-items-center rounded-full bg-[#e6b85c] text-xs font-bold text-[#123b3a]">
              AD
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">Administrador</p>
              <p className="truncate text-xs text-white/45">
                Control operativo
              </p>
            </div>
            <Settings2 size={16} className="ml-auto text-white/45" />
          </div>
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="flex h-20 items-center justify-between border-b border-[#dce6e4] bg-white px-5 sm:px-8">
          <button
            type="button"
            className="rounded-md p-2 text-[#52616b] lg:hidden"
            aria-label="Abrir menu"
          >
            <Menu size={20} />
          </button>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-[#718096] sm:inline">
              Ciclo operativo 2026
            </span>
            <div className="grid size-9 place-items-center rounded-full bg-[#d9eee9] text-xs font-bold text-[#0f766e]">
              AD
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl p-5 sm:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
