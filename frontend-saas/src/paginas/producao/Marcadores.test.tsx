import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { IndicadorPerda } from './Marcadores'

describe('indicador de perda (D66, D111)', () => {
  it('0% sem perda lançada não vira "perda baixa" verde', () => {
    render(<IndicadorPerda taxa="0" perdaRegistrada={false} />)
    expect(screen.getByText('sem perda lançada')).toBeInTheDocument()
    expect(screen.queryByText(/perda baixa/)).not.toBeInTheDocument()
  })

  it('0% com perda registrada (zero declarado) continua perda baixa', () => {
    render(<IndicadorPerda taxa="0" perdaRegistrada />)
    expect(screen.getByText('0% · perda baixa')).toBeInTheDocument()
  })

  it('ordem antiga, sem o campo, mantém o comportamento de antes', () => {
    render(<IndicadorPerda taxa="0.02" />)
    expect(screen.getByText('2% · perda baixa')).toBeInTheDocument()
  })

  it('sem venda continua "sem venda"', () => {
    render(<IndicadorPerda taxa={null} perdaRegistrada={false} />)
    expect(screen.getByText('sem venda')).toBeInTheDocument()
  })
})
