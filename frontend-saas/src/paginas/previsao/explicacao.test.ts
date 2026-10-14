import { describe, expect, it } from 'vitest'
import { itemPrevisao } from '@/test/previsao'
import { explicarPrevisao } from './explicacao'

describe('explicação da previsão (F9)', () => {
  it('caso comum: mediana das últimas 6 quartas × tendência, com a conta', () => {
    const e = explicarPrevisao(itemPrevisao())
    expect(e.situacao).toBe('normal')
    expect(e.resumo).toBe('Mediana das últimas 6 quartas × tendência +10%')
    expect(e.passos).toEqual([
      'Mediana das últimas 6 quartas: 40 kg. A mediana é o valor do meio, que não se deixa levar por um dia fora do comum.',
      'Tendência: os últimos 7 dias venderam 10% acima do normal (+10%).',
      'Conta: 40 kg × 1,1 = 44 kg.',
    ])
  })

  it('semanas faltando na base aparecem no texto', () => {
    const e = explicarPrevisao(itemPrevisao({ semanas_na_base: 4 }))
    expect(e.resumo).toBe('Mediana de 4 das últimas 6 quartas × tendência +10%')
    expect(e.passos[0]).toContain('de 4 das últimas 6 quartas (as outras não tinham venda registrada): 40 kg')
  })

  it('tendência abaixo, estável e sem dias suficientes', () => {
    expect(explicarPrevisao(itemPrevisao({ tendencia: '0.8500', tendencia_bruta: '0.8500' })).resumo).toBe(
      'Mediana das últimas 6 quartas × tendência −15%',
    )
    expect(explicarPrevisao(itemPrevisao({ tendencia: '0.8500', tendencia_bruta: '0.8500' })).passos[1]).toBe(
      'Tendência: os últimos 7 dias venderam 15% abaixo do normal (−15%).',
    )
    expect(explicarPrevisao(itemPrevisao({ tendencia: '1.0020', tendencia_bruta: '1.0020' })).resumo).toBe(
      'Mediana das últimas 6 quartas, vendas estáveis',
    )
    const semDias = explicarPrevisao(itemPrevisao({ tendencia: '1', tendencia_bruta: null, dias_na_tendencia: 3 }))
    expect(semDias.resumo).toBe('Mediana das últimas 6 quartas, sem ajuste de tendência')
    expect(semDias.passos[1]).toBe(
      'Tendência: sem ajuste. Só 3 dos últimos 7 dias tinham venda para comparar (são precisos 5).',
    )
  })

  it('tendência acima do limite: mostra a real e o limite aplicado', () => {
    const e = explicarPrevisao(itemPrevisao({ tendencia: '1.3000', tendencia_bruta: '1.4500', previsao: '52', previsao_propria: '52', previsao_sem_evento: '52' }))
    expect(e.passos[1]).toBe('Tendência: os últimos 7 dias venderam 45% acima do normal; o ajuste é limitado a +30%.')
    // a conta usa o fator limitado (1,3), não o real (1,45)
    expect(e.passos[2]).toBe('Conta: 40 kg × 1,3 = 52 kg.')
  })

  it('sazonal: compara com o mesmo período do ano passado', () => {
    const e = explicarPrevisao(itemPrevisao({ metodo: 'sazonal', semanas_na_base: 5 }))
    expect(e.resumo).toBe('Mediana do mesmo período do ano passado × tendência +10%')
    expect(e.passos[0]).toContain('no mesmo período do ano passado (5 dias): 40 kg')
    expect(e.passos[1]).toContain('acima do mesmo período do ano passado')
  })

  it('pouco histórico com proxy: mistura própria e produtos parecidos, com os pesos', () => {
    const e = explicarPrevisao(
      itemPrevisao({
        pouco_historico: true,
        peso_historico: '0.3333',
        inicio_historico: '2026-09-28',
        proxy: '30.0000',
        origem_proxy: 'categoria',
        previsao: '34.6667',
        previsao_sem_evento: '34.6667',
      }),
    )
    expect(e.situacao).toBe('pouco_historico')
    expect(e.resumo).toBe('Pouco histórico: 33% vendas próprias + 67% média de produtos da mesma categoria')
    expect(e.passos[3]).toBe(
      'Pouco histórico: 2 de 6 semanas de vendas próprias (desde 28/09/2026). Por isso a previsão junta 33% da conta acima com 67% da média dos produtos da mesma categoria nesta loja (30 kg) = 34,67 kg.',
    )
  })

  it('pouco histórico sem venda própria: vale só o proxy (loja nova)', () => {
    const e = explicarPrevisao(
      itemPrevisao({
        pouco_historico: true,
        peso_historico: '0',
        inicio_historico: null,
        base: null,
        semanas_na_base: 0,
        previsao_propria: null,
        proxy: '30.0000',
        origem_proxy: 'outras_lojas',
        previsao: '30.0000',
        previsao_sem_evento: '30.0000',
      }),
    )
    expect(e.situacao).toBe('pouco_historico')
    expect(e.resumo).toBe('Pouco histórico: média de outras lojas')
    expect(e.passos).toEqual([
      'Pouco histórico: ainda não há venda própria para calcular. Vale a média do mesmo produto nas outras lojas da central: 30 kg.',
    ])
  })

  it('pouco histórico sem produto parecido: avisa que vale só a conta própria', () => {
    const e = explicarPrevisao(itemPrevisao({ pouco_historico: true, peso_historico: '0.5000', proxy: null }))
    expect(e.situacao).toBe('pouco_historico')
    expect(e.passos[3]).toContain('3 de 6 semanas de vendas próprias (desde 01/08/2026) e nenhum produto parecido')
  })

  it('sem previsão: explica o motivo e o que fazer (produto novo sem parecido)', () => {
    const e = explicarPrevisao(
      itemPrevisao({
        previsao: null,
        previsao_sem_evento: null,
        previsao_propria: null,
        base: null,
        semanas_na_base: 0,
        pouco_historico: true,
        peso_historico: '0',
      }),
    )
    expect(e.situacao).toBe('sem_previsao')
    expect(e.resumo).toBe('Sem previsão: ainda não há vendas deste produto nesta loja nem produto parecido para comparar.')
    expect(e.passos[1]).toMatch(/^O que fazer: defina a quantidade/)
  })

  it('sem previsão com histórico completo: nenhuma venda no dia da semana', () => {
    const e = explicarPrevisao(itemPrevisao({ previsao: null, previsao_sem_evento: null, previsao_propria: null, base: null, semanas_na_base: 0 }))
    expect(e.resumo).toBe('Sem previsão: nenhuma das últimas 6 quartas tem venda registrada nesta loja.')
  })

  it('evento multiplicador: entra no resumo e na conta', () => {
    const e = explicarPrevisao(
      itemPrevisao({
        previsao: '66.0000',
        eventos: [{ id: 3, nome: 'Feriado', tipo_ajuste: 'multiplicador', valor_ajuste: '1.5000' }],
      }),
    )
    expect(e.resumo).toBe('Mediana das últimas 6 quartas × tendência +10% × evento “Feriado” (×1,5)')
    expect(e.passos.at(-1)).toBe('Evento “Feriado” (×1,5): 44 kg → 66 kg.')
  })

  it('evento de valor fixo: substitui o cálculo, e diz quanto seria sem ele', () => {
    const e = explicarPrevisao(
      itemPrevisao({
        previsao: '80.0000',
        eventos: [{ id: 4, nome: 'Festa junina', tipo_ajuste: 'valor_fixo', valor_ajuste: '80.0000' }],
      }),
    )
    expect(e.situacao).toBe('valor_fixo')
    expect(e.resumo).toBe('Valor fixo do evento “Festa junina”')
    expect(e.passos).toEqual([
      'O evento “Festa junina” define 80 kg para este dia, no lugar do cálculo normal.',
      'Sem o evento, a previsão seria 44 kg.',
    ])
  })

  it('UN com 1 casa decimal', () => {
    const e = explicarPrevisao(itemPrevisao({ unidade: 'UN', base: '12.5000', previsao_propria: '13.7500', previsao: '13.7500', tendencia: '1.1', tendencia_bruta: '1.1' }))
    expect(e.passos[2]).toBe('Conta: 12,5 un × 1,1 = 13,8 un.')
  })
})
