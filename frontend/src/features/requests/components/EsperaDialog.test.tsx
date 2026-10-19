import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EsperaDialog } from './EsperaDialog'

vi.mock('@/api/solicitudes', () => ({
  putRequestOnHold: vi.fn(),
}))

const renderDialog = (
  props: {
    open?: boolean
    onClose?: () => void
    folio?: string
    onConfirm?: (reason: string, detail: string | null) => Promise<void>
  } = {},
) => {
  const {
    open = true,
    onClose = vi.fn(),
    folio = 'SIG-0001',
    onConfirm = vi.fn().mockResolvedValue(undefined),
  } = props
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <EsperaDialog
        open={open}
        onClose={onClose}
        folio={folio}
        onConfirm={onConfirm}
      />
    </QueryClientProvider>,
  )
}

describe('EsperaDialog: motivo de espera (S3-16, HU-04.2)', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('muestra el folio y los motivos predefinidos', () => {
    renderDialog({ folio: 'SIG-0042' })

    expect(screen.getByText('Motivo de espera')).toBeInTheDocument()
    expect(screen.getByText(/SIG-0042/)).toBeInTheDocument()
    expect(screen.getByLabelText('Motivo')).toBeInTheDocument()
    expect(screen.getByText('Esperando insumo externo')).toBeInTheDocument()
    expect(
      screen.getByText('Esperando información del solicitante'),
    ).toBeInTheDocument()
    expect(screen.getByText('Otro (especificar)')).toBeInTheDocument()
  })

  it('al confirmar con motivo predefinido llama a onConfirm sin detalle', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    renderDialog({ onConfirm })

    const user = userEvent.setup()
    await user.selectOptions(
      screen.getByLabelText('Motivo'),
      'user_information',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar espera' }))

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1))
    expect(onConfirm).toHaveBeenCalledWith('user_information', null)
  })

  it('al seleccionar "Otro" muestra el campo de detalle', async () => {
    renderDialog()

    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('Motivo'), 'other')

    expect(screen.getByLabelText('Describe el motivo')).toBeInTheDocument()
  })

  it('al confirmar con "Otro" y detalle llama a onConfirm con ambos valores', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    renderDialog({ onConfirm })

    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('Motivo'), 'other')
    await user.type(
      screen.getByLabelText('Describe el motivo'),
      'Pendiente de repuesto del proveedor',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar espera' }))

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1))
    expect(onConfirm).toHaveBeenCalledWith(
      'user_information',
      'Pendiente de repuesto del proveedor',
    )
  })

  it('al confirmar "Otro" sin detalle muestra error de validación y no llama a onConfirm', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    renderDialog({ onConfirm })

    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('Motivo'), 'other')
    await user.click(screen.getByRole('button', { name: 'Guardar espera' }))

    expect(
      await screen.findByText('Por favor describe el motivo de espera.'),
    ).toBeInTheDocument()
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('al cancelar cierra el diálogo sin llamar a onConfirm', async () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    renderDialog({ onClose, onConfirm })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('cuando la API falla muestra el mensaje de error y no cierra', async () => {
    const onConfirm = vi
      .fn()
      .mockRejectedValue(
        new Error(
          'La solicitud no está en un estado que permita ponerla en espera',
        ),
      )
    renderDialog({ onConfirm })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Guardar espera' }))

    expect(
      await screen.findByText(
        'La solicitud no está en un estado que permita ponerla en espera',
      ),
    ).toBeInTheDocument()
    // El diálogo sigue abierto
    expect(screen.getByText('Motivo de espera')).toBeInTheDocument()
  })
})
