import { describe, expect, it } from 'vitest'
import type { RequestStatus } from '@/api/seguimiento'
import {
  puedeAtender,
  puedeCerrar,
  puedeDiagnosticar,
  puedeIniciar,
  puedeReanudar,
  puedeResolver,
} from './estados-atencion'

// Tabla esperada según backend/app/domain/estados.py.
// [estatus, iniciar, diagnosticar, resolver, reanudar, cerrar]
const TABLA: [RequestStatus, boolean, boolean, boolean, boolean, boolean][] = [
  ['registered', false, false, false, false, false],
  ['pending_verification', false, false, false, false, false],
  ['classified', false, false, false, false, false],
  ['pending_review', false, false, false, false, false],
  ['assigned', true, true, true, false, false],
  ['in_progress', false, true, true, false, false],
  ['waiting', false, true, false, true, false],
  ['escalated', false, false, false, false, false],
  ['resolved', false, false, false, false, true],
  ['closed', false, false, false, false, false],
  ['closed_unverified', false, false, false, false, false],
]

describe('reglas de estados de atención', () => {
  it('la tabla cubre los 11 estatus', () => {
    expect(new Set(TABLA.map(([status]) => status)).size).toBe(11)
  })

  it.each(TABLA)(
    '%s → iniciar %s, diagnosticar %s, resolver %s, reanudar %s, cerrar %s',
    (status, iniciar, diagnosticar, resolver, reanudar, cerrar) => {
      expect(puedeIniciar(status)).toBe(iniciar)
      expect(puedeDiagnosticar(status)).toBe(diagnosticar)
      expect(puedeResolver(status)).toBe(resolver)
      expect(puedeReanudar(status)).toBe(reanudar)
      expect(puedeCerrar(status)).toBe(cerrar)
    },
  )
})

describe('puedeAtender', () => {
  it.each([
    [['administrator'], true],
    [['service_manager'], true],
    [['support_agent'], true],
    [['requester', 'support_agent'], true],
    [['requester'], false],
    [['classifier'], false],
    [['knowledge_manager'], false],
    [['auditor'], false],
    [[], false],
    [undefined, false],
  ])('%j → %s', (roles, esperado) => {
    expect(puedeAtender(roles)).toBe(esperado)
  })
})
