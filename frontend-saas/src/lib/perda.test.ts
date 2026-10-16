import { describe, expect, it } from 'vitest'
import { faixaPerda, LIMITES_PERDA, ROTULO_FAIXA } from './perda'

describe('faixas do indicador de perda (D66)', () => {
  it.each([
    ['0', 'baixa'],
    ['0.0300', 'baixa'],
    ['0.0301', 'normal'],
    ['0.0500', 'normal'],
    ['0.0501', 'alta'],
    ['0.0800', 'alta'],
    ['0.0801', 'muito_alta'],
    ['0.25', 'muito_alta'],
  ])('%s -> %s', (taxa, faixa) => {
    expect(faixaPerda(taxa)).toBe(faixa)
  })

  it('sem venda (null, vazio, texto inválido) -> sem faixa', () => {
    expect(faixaPerda(null)).toBeNull()
    expect(faixaPerda(undefined)).toBeNull()
    expect(faixaPerda('')).toBeNull()
    expect(faixaPerda('abc')).toBeNull()
  })

  it('limites numa constante única, com os valores decididos', () => {
    expect(LIMITES_PERDA).toEqual({ baixa: 0.03, normal: 0.05, alta: 0.08 })
    expect(ROTULO_FAIXA).toEqual({
      baixa: 'perda baixa',
      normal: 'normal',
      alta: 'perda alta',
      muito_alta: 'perda muito alta',
    })
  })
})
