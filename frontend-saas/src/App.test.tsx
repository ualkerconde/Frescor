import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it } from 'vitest'
import App from './App'
import { SessaoProvider } from './lib/sessao/SessaoProvider'

describe('App (rotas)', () => {
  beforeEach(() => localStorage.clear())

  it('sem sessão, qualquer rota leva ao login', () => {
    render(
      <MemoryRouter initialEntries={['/qualquer-coisa']}>
        <SessaoProvider>
          <App />
        </SessaoProvider>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
  })
})
