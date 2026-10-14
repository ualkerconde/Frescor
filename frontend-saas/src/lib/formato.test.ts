import { describe, expect, it } from 'vitest'
import {
  contar,
  dataIso,
  diaDaSemana,
  diasNoPeriodo,
  formatarData,
  formatarInteiro,
  formatarPercentual,
  formatarPrevisao,
  formatarQuantidade,
  formatarTamanho,
  formatarVariacao,
  somarDias,
} from './formato'

describe('formatos pt-BR (skill Frescor)', () => {
  it('inteiro com ponto de milhar', () => {
    expect(formatarInteiro(1232)).toBe('1.232')
    expect(formatarInteiro(0)).toBe('0')
  })

  it('singular e plural', () => {
    expect(contar(1, 'linha', 'linhas')).toBe('1 linha')
    expect(contar(2, 'linha', 'linhas')).toBe('2 linhas')
    expect(contar(0, 'erro', 'erros')).toBe('0 erros')
  })

  it('quantidade sempre com a unidade, vírgula decimal e sem zeros sobrando', () => {
    expect(formatarQuantidade('171.000', 'UN')).toBe('171 un')
    expect(formatarQuantidade('3.750', 'KG')).toBe('3,75 kg')
    expect(formatarQuantidade('18.5', 'KG')).toBe('18,5 kg')
    expect(formatarQuantidade('1240', 'UN')).toBe('1.240 un')
    expect(formatarQuantidade('0.125', 'KG')).toBe('0,125 kg')
  })

  it('data AAAA-MM-DD -> dd/mm/aaaa sem erro de fuso', () => {
    expect(formatarData('2026-09-01')).toBe('01/09/2026')
    expect(formatarData('2026-12-31')).toBe('31/12/2026')
  })

  it('dataIso usa a data local', () => {
    expect(dataIso(new Date(2026, 8, 1))).toBe('2026-09-01')
  })

  it('dias no período contam o primeiro e o último', () => {
    expect(diasNoPeriodo('2026-09-01', '2026-09-07')).toBe(7)
    expect(diasNoPeriodo('2026-09-01', '2026-09-01')).toBe(1)
    expect(diasNoPeriodo('2025-10-01', '2026-10-01')).toBe(366)
    expect(diasNoPeriodo('2026-03-01', '2026-03-31')).toBe(31) // atravessa o horário de verão em alguns fusos
  })

  it('tamanho de arquivo', () => {
    expect(formatarTamanho(512)).toBe('512 bytes')
    expect(formatarTamanho(1536)).toBe('1,5 KB')
    expect(formatarTamanho(5 * 1024 * 1024)).toBe('5 MB')
  })

  it('previsão: 1 casa em UN e 2 em KG, sempre com a unidade', () => {
    expect(formatarPrevisao('44.1234', 'UN')).toBe('44,1 un')
    expect(formatarPrevisao('40.0000', 'UN')).toBe('40 un')
    expect(formatarPrevisao('25.4567', 'KG')).toBe('25,46 kg')
    expect(formatarPrevisao('1240.5', 'UN')).toBe('1.240,5 un')
  })

  it('percentual a partir de fração, com vírgula', () => {
    expect(formatarPercentual('0.0960')).toBe('9,6%')
    expect(formatarPercentual('0.1165')).toBe('11,7%')
    expect(formatarPercentual('0')).toBe('0%')
  })

  it('variação de um fator: sinal, arredondada', () => {
    expect(formatarVariacao('1.10')).toBe('+10%')
    expect(formatarVariacao('0.85')).toBe('−15%')
    expect(formatarVariacao('1.004')).toBe('0%')
    expect(formatarVariacao('1.3')).toBe('+30%')
  })

  it('dia da semana sem erro de fuso, no singular e no plural', () => {
    expect(diaDaSemana('2026-10-14')).toBe('quarta')
    expect(diaDaSemana('2026-10-18', true)).toBe('domingos')
    expect(diaDaSemana('2026-10-17', true)).toBe('sábados')
  })

  it('somar dias atravessa mês e ano', () => {
    expect(somarDias('2026-10-14', -7)).toBe('2026-10-07')
    expect(somarDias('2026-12-28', 7)).toBe('2027-01-04')
    expect(somarDias('2026-03-01', -1)).toBe('2026-02-28')
  })
})
