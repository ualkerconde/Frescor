import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderizarApp, simularApi } from './test/renderizar'

describe('App (rotas)', () => {
  beforeEach(() => {
    localStorage.clear()
    simularApi()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('sem sessão, qualquer rota leva ao login', () => {
    renderizarApp('/qualquer-coisa')
    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
  })
})
