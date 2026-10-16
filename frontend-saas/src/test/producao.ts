/*
 * Dados de teste da ordem de produção (N9), no formato da API (N7).
 */
import type { ContaNecessidade, ItemOrdem, LinhaOrdem, OrdemDetalhe, OrdemResumo } from '@/lib/api/tipos'

export function conta(extra: Partial<ContaNecessidade> = {}): Partial<ContaNecessidade> {
  return {
    dias_cobertura: ['2026-10-16'],
    dias_cobertura_sem_limite: 1,
    dias_ate_chegada: [],
    minimo: '40.0000',
    margem: '10',
    origem_margem: 'padrao',
    alvo: '44.00000',
    estoque_contado: null,
    contagem_valida: false,
    contagem_local: null,
    estoque_considerado: '0',
    transito_considerado: '0',
    consumo_ate_chegada: '0',
    vencido_ate_chegada: '0',
    estoque_na_chegada: '0',
    necessidade_bruta: '44.00000',
    necessidade: '44',
    avisos: [],
    pouco_historico: false,
    taxa_perda: '0.0200',
    ...extra,
  }
}

export function linha(id: number, extra: Partial<LinhaOrdem> = {}): LinhaOrdem {
  return {
    id,
    loja: { id: 1, codigo: '001', nome: 'Loja Centro' },
    quantidade_sugerida: '44.000',
    quantidade_final: '44.000',
    editada: false,
    editado_em: null,
    motivo_edicao: null,
    avisos: [],
    componentes: conta(),
    ...extra,
  }
}

/** Pão (produzido, 2 lojas: perda baixa e normal), Bolo (sem calendário, sem quantidade), Manteiga (distribuída). */
export function itensPadrao(): ItemOrdem[] {
  return [
    {
      id: 10,
      produto: { id: 1, codigo: 'INT-007', nome: 'Pão Francês' },
      tipo_abastecimento: 'produzido',
      unidade: 'UN',
      total_sugerido: '88.000',
      total_final: '88.000',
      linhas: [
        linha(101),
        linha(102, {
          loja: { id: 2, codigo: '002', nome: 'Loja Bairro' },
          avisos: ['sem_contagem'],
          componentes: conta({ taxa_perda: '0.0400', avisos: ['sem_contagem'] }),
        }),
      ],
    },
    {
      id: 11,
      produto: { id: 2, codigo: 'INT-002', nome: 'Bolo de Chocolate' },
      tipo_abastecimento: 'produzido',
      unidade: 'UN',
      total_sugerido: '0',
      total_final: '0',
      linhas: [
        linha(103, {
          quantidade_sugerida: null,
          quantidade_final: null,
          avisos: ['sem_calendario'],
          componentes: conta({ minimo: null, alvo: null, dias_cobertura: [], avisos: ['sem_calendario'], taxa_perda: '0.0600' }),
        }),
      ],
    },
    {
      id: 12,
      produto: { id: 3, codigo: 'INT-011', nome: 'Manteiga' },
      tipo_abastecimento: 'distribuido',
      unidade: 'UN',
      total_sugerido: '9.000',
      total_final: '9.000',
      linhas: [linha(104, { quantidade_sugerida: '9.000', quantidade_final: '9.000', componentes: conta({ taxa_perda: '0.0900' }) })],
    },
  ]
}

export function ordemDetalhe(data: string, extra: Partial<OrdemDetalhe> = {}): OrdemDetalhe {
  return {
    id: 7,
    data_producao: data,
    data_entrega: data,
    tipo: 'programada',
    status: 'rascunho',
    versao_metodo: '2026.10-n1',
    referencia_previsao: data,
    gerado_em: '2026-10-15T23:00:00',
    gerado_por: 'Gestor Central Teste',
    aprovado_em: null,
    aprovado_por: null,
    linhas: 4,
    linhas_editadas: 0,
    linhas_sem_quantidade: 1,
    totais: [{ unidade: 'UN', sugerido: '97.000', final: '97.000' }],
    itens: itensPadrao(),
    ...extra,
  }
}

export function resumoDe(o: OrdemDetalhe): OrdemResumo {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { itens, ...resumo } = o
  return resumo
}
