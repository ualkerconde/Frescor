import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './button'

describe('Button (ajustado à skill Frescor)', () => {
  it('primário usa a cor primária, 44px de altura e texto 16px', () => {
    render(<Button>Importar vendas</Button>)
    const botao = screen.getByRole('button', { name: 'Importar vendas' })
    expect(botao.className).toContain('bg-primary')
    expect(botao.className).toContain('h-11')
    expect(botao.className).toContain('text-base')
  })

  it('secundário tem borda de 2px e texto na cor primária', () => {
    render(<Button variant="secondary">Baixar modelo de CSV</Button>)
    const botao = screen.getByRole('button', { name: 'Baixar modelo de CSV' })
    expect(botao.className).toContain('border-2')
    expect(botao.className).toContain('border-primary')
    expect(botao.className).toContain('text-primary')
  })

  it('carregando mostra o texto, fica ocupado e bloqueia o clique', async () => {
    const clique = vi.fn()
    render(
      <Button carregando textoCarregando="Enviando…" onClick={clique}>
        Importar vendas
      </Button>,
    )
    const botao = screen.getByRole('button', { name: 'Enviando…' })
    expect(botao).toBeDisabled()
    expect(botao).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(botao)
    expect(clique).not.toHaveBeenCalled()
  })

  it('todos os tamanhos têm pelo menos 44px (área de toque da skill)', () => {
    for (const size of ['default', 'sm', 'icon', 'icon-sm'] as const) {
      const { unmount } = render(<Button size={size} aria-label={`b-${size}`} />)
      const classes = screen.getByRole('button', { name: `b-${size}` }).className
      expect(classes, size).toMatch(/\b(h-11|size-11)\b/)
      unmount()
    }
  })
})
