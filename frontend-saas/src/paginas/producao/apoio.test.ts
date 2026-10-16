import { describe, expect, it } from 'vitest'
import type { ContaNecessidade } from '@/lib/api/tipos'
import { descreverAviso } from './avisos'
import { passosDaConta } from './conta'
import { lerQuantidade } from './quantidade'

const CONTA_PAO: Partial<ContaNecessidade> = {
  dias_cobertura: ['2026-10-16'],
  dias_cobertura_sem_limite: 1,
  dias_ate_chegada: [],
  minimo: '27.9600',
  margem: '10',
  origem_margem: 'padrao',
  alvo: '30.756',
  estoque_contado: '4.3000',
  contagem_valida: true,
  contagem_local: '2026-10-15T21:00:00-03:00',
  estoque_considerado: '4.3000',
  transito_considerado: '0',
  consumo_ate_chegada: '0',
  vencido_ate_chegada: '4.3000',
  estoque_na_chegada: '0',
  necessidade_bruta: '30.756',
  necessidade: '30.8',
  avisos: [],
}

describe('conta da linha da ordem', () => {
  it('pão de validade 1: a sobra contada vence antes da chegada', () => {
    expect(passosDaConta(CONTA_PAO, 'KG')).toEqual([
      'Cobre 1 dia: sex 16/10.',
      'Previsão de venda somada nesses dias: 27,96 kg.',
      'Margem de 10% (padrão): alvo de 30,76 kg.',
      'Contagem da loja: 4,3 kg, em 15/10 às 21:00.',
      'Vence antes da chegada e não conta: 4,3 kg.',
      'Estoque na chegada: 0 kg.',
      'Necessidade: 30,76 kg − 0 kg = 30,76 kg, arredondada para 30,8 kg.',
    ])
  })

  it('cobertura limitada pela validade, contagem antiga e prazo 1 com trânsito', () => {
    const passos = passosDaConta(
      {
        ...CONTA_PAO,
        dias_cobertura: ['2026-10-16', '2026-10-17'],
        dias_cobertura_sem_limite: 4,
        dias_ate_chegada: ['2026-10-15'],
        contagem_valida: false,
        limite_contagem_local: '2026-10-14T19:00:00-03:00',
        contagem_local: '2026-10-12T21:00:00-03:00',
        transito_considerado: '12.000',
        consumo_ate_chegada: '20',
        vencido_ate_chegada: '0',
        origem_margem: 'pouco_historico',
        margem: '20',
      },
      'UN',
    )
    expect(passos[0]).toBe('Cobre 2 dias: sex 16/10, sáb 17/10 (seriam 4 até a próxima entrega; a validade limita).')
    expect(passos).toContain('Margem de 20% (pouco histórico: no mínimo 20%): alvo de 30,8 un.')
    expect(passos).toContain(
      'Contagem de 4,3 un em 12/10 às 21:00 é anterior ao fechamento da véspera (vale a partir de 14/10 às 19:00): estoque considerado 0.',
    )
    expect(passos).toContain('Antes da chegada (qui 15/10), a loja vende 20 un e recebe 12 un já aprovados.')
  })

  it('sem calendário: explica o motivo em vez da conta', () => {
    expect(passosDaConta({ dias_cobertura: [], minimo: null, alvo: null, avisos: ['sem_calendario'] }, 'UN')).toEqual([
      'O produto não tem dias de produção cadastrados. Informe a quantidade ou cadastre o calendário.',
    ])
  })

  it('aviso desconhecido não some', () => {
    expect(descreverAviso('novo_aviso').rotulo).toBe('Atenção')
  })
})

describe('quantidade digitada', () => {
  it.each([
    ['12', 'UN', '12'],
    ['12,0', 'UN', '12.0'],
    ['4,5', 'KG', '4.5'],
    ['4.125', 'KG', '4.125'],
    [' 0 ', 'UN', '0'],
  ] as const)('%s em %s -> %s', (texto, unidade, valor) => {
    expect(lerQuantidade(texto, unidade)).toEqual({ ok: true, valor })
  })

  it.each([
    ['', 'UN', 'Informe a quantidade.'],
    ['doze', 'UN', 'Use só números, por exemplo 12 ou 4,5.'],
    ['-1', 'UN', 'A quantidade não pode ser negativa.'],
    ['12,5', 'UN', 'Este produto é vendido por unidade: informe um número inteiro.'],
    ['4,1234', 'KG', 'Informe no máximo 3 casas decimais.'],
  ] as const)('%s em %s -> erro', (texto, unidade, erro) => {
    expect(lerQuantidade(texto, unidade)).toEqual({ ok: false, erro })
  })
})
