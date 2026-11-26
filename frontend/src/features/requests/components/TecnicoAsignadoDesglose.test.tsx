import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import {
    getAsignacionVigente,
    type AsignacionVigente,
} from '@/api/asignaciones'
import { TecnicoAsignadoDesglose } from './TecnicoAsignadoDesglose'

vi.mock('@/api/asignaciones', () => ({
    getAsignacionVigente: vi.fn(),
}))

const authState = vi.hoisted(() => ({ roles: ['support_agent'] as string[] }))
vi.mock('@/features/auth/auth-context', () => ({
    useAuth: () => ({
        user: { id: 'usuario-1', full_name: 'Persona', roles: authState.roles },
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        logout: vi.fn(),
    }),
}))

const getAsignacionMock = vi.mocked(getAsignacionVigente)

const REQUEST_ID = '11111111-1111-4111-8111-111111111111'

const ASIGNACION: AsignacionVigente = {
    id: 'asig-1',
    request_id: REQUEST_ID,
    technician_id: 'tec-1',
    full_name: 'Ana López',
    score: 128,
    score_breakdown:
        'Especialidad +100 (atiende la categoría) · Turno +20 (Matutino: en turno) · Carga +8 (2 solicitudes activas)',
    components: [
        { concepto: 'Especialidad', puntos: 100, detalle: 'atiende la categoría' },
        { concepto: 'Turno', puntos: 20, detalle: 'Matutino: en turno' },
        { concepto: 'Carga', puntos: 8, detalle: '2 solicitudes activas' },
    ],
    is_automatic: false,
    assigned_at: '2026-11-25T10:00:00Z',
}

function renderSeccion() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    })
    return render(
        <QueryClientProvider client={queryClient}>
            <TecnicoAsignadoDesglose requestId={REQUEST_ID} />
        </QueryClientProvider>,
    )
}

beforeEach(() => {
    vi.clearAllMocks()
    authState.roles = ['support_agent']
})

describe('TecnicoAsignadoDesglose', () => {
    it('muestra el técnico asignado con el desglose y el total de su puntaje', async () => {
        getAsignacionMock.mockResolvedValue(ASIGNACION)
        renderSeccion()

        expect(screen.getByRole('status')).toHaveTextContent(
            'Cargando técnico asignado…',
        )
        expect(await screen.findByText('Ana López')).toBeInTheDocument()
        const seccion = screen.getByRole('region', { name: 'Técnico asignado' })
        expect(getAsignacionMock).toHaveBeenCalledWith(REQUEST_ID)
        expect(within(seccion).getByText(/Asignación manual/)).toBeInTheDocument()

        const lista = within(seccion).getByRole('list', {
            name: 'Desglose del puntaje',
        })
        const items = within(lista).getAllByRole('listitem')
        expect(items).toHaveLength(3)
        expect(items[0]).toHaveTextContent(
            'Especialidad (+100 pts): atiende la categoría',
        )
        expect(items[2]).toHaveTextContent('Carga (+8 pts): 2 solicitudes activas')
        expect(within(seccion).getByText(/Puntaje total/)).toHaveTextContent(
            'Puntaje total: 128',
        )
    })

    it('indica si la asignación fue automática', async () => {
        getAsignacionMock.mockResolvedValue({ ...ASIGNACION, is_automatic: true })
        renderSeccion()

        expect(
            await screen.findByText(/Asignación automática/),
        ).toBeInTheDocument()
    })

    it('avisa si la solicitud todavía no tiene técnico', async () => {
        getAsignacionMock.mockResolvedValue(null)
        renderSeccion()

        expect(
            await screen.findByText(
                'Esta solicitud todavía no tiene técnico asignado.',
            ),
        ).toBeInTheDocument()
        expect(screen.queryByRole('list')).not.toBeInTheDocument()
    })

    it('si la asignación no guarda puntaje lo dice, sin desglose', async () => {
        getAsignacionMock.mockResolvedValue({
            ...ASIGNACION,
            score: null,
            score_breakdown: null,
            components: [],
        })
        renderSeccion()

        expect(await screen.findByText('Ana López')).toBeInTheDocument()
        expect(
            screen.getByText('Esta asignación no tiene puntaje registrado.'),
        ).toBeInTheDocument()
        expect(screen.queryByRole('list')).not.toBeInTheDocument()
        expect(screen.queryByText(/Puntaje total/)).not.toBeInTheDocument()
    })

    it('si el desglose no pudo separarse muestra el texto guardado', async () => {
        getAsignacionMock.mockResolvedValue({
            ...ASIGNACION,
            components: [],
            score_breakdown: 'Puntaje calculado con el método anterior',
        })
        renderSeccion()

        expect(
            await screen.findByText('Puntaje calculado con el método anterior'),
        ).toBeInTheDocument()
        expect(
            screen.queryByText('Esta asignación no tiene puntaje registrado.'),
        ).not.toBeInTheDocument()
    })

    it('muestra el error al cargar la asignación', async () => {
        getAsignacionMock.mockRejectedValue(new ApiError(500, 'Fallo del servidor'))
        renderSeccion()

        expect(await screen.findByRole('alert')).toBeInTheDocument()
    })

    it.each(['requester', 'classifier'])(
        'no aparece ni consulta nada para el rol %s',
        (rol) => {
            authState.roles = [rol]
            const { container } = renderSeccion()

            expect(container).toBeEmptyDOMElement()
            expect(getAsignacionMock).not.toHaveBeenCalled()
        },
    )

    it('aparece para un jefe de servicio', async () => {
        authState.roles = ['service_manager']
        getAsignacionMock.mockResolvedValue(ASIGNACION)
        renderSeccion()

        expect(await screen.findByText('Ana López')).toBeInTheDocument()
    })
})
