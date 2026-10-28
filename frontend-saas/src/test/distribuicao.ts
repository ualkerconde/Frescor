/*
 * Dados de teste da distribuição (E10), no formato da API (E6).
 * Ordem 7: Pão Francês (UN, planejado 19) e Baguete (KG, planejado 4,5).
 * Romaneio 30: Pão produzido 10 (rateio 3 / 7) e Baguete 4,5 (2,5 / 2).
 */
import type { EntregaRomaneio, ItemProducao, ItemRomaneio, OrdemDistribuicao, RomaneioDetalhe } from '@/lib/api/tipos'

export const PAO = { id: 1, codigo: 'INT-007', nome: 'Pão Francês' }
export const BAGUETE = { id: 2, codigo: 'INT-009', nome: 'Baguete' }
export const LOJA_CENTRO = { id: 1, codigo: '001', nome: 'Loja Centro' }
export const LOJA_BAIRRO = { id: 2, codigo: '002', nome: 'Loja Bairro' }

export function itensProducao(produzidos: [string | null, string | null] = [null, null]): ItemProducao[] {
  return [
    { item_id: 10, produto: PAO, unidade: 'UN', tipo_abastecimento: 'produzido', planejado: '19.000', produzido: produzidos[0], registrado_em: null },
    { item_id: 11, produto: BAGUETE, unidade: 'KG', tipo_abastecimento: 'produzido', planejado: '4.500', produzido: produzidos[1], registrado_em: null },
  ]
}

export function ordemDoDia(data: string, extra: Partial<OrdemDistribuicao> = {}): OrdemDistribuicao {
  return { ordem_id: 7, data_producao: data, data_entrega: data, status_ordem: 'aprovada', itens: itensProducao(), romaneio: null, ...extra }
}

function item(id: number, produto: typeof PAO, unidade: 'UN' | 'KG', final: string, extra: Partial<ItemRomaneio> = {}): ItemRomaneio {
  return {
    id, produto, unidade, quantidade_sugerida: final, quantidade_final: final, quantidade_recebida: null,
    motivo_divergencia: null, observacao_divergencia: null, editado_em: null, motivo_edicao: null, ...extra,
  }
}

export function entregas(): EntregaRomaneio[] {
  const aguardando = { situacao: 'aguardando_saida' as const, pode_confirmar: false, com_diferenca: false }
  return [
    { id: 101, loja: LOJA_CENTRO, situacao: aguardando, expedido_em: null, recebido_em: null,
      itens: [item(201, PAO, 'UN', '3.000'), item(202, BAGUETE, 'KG', '2.500')] },
    { id: 102, loja: LOJA_BAIRRO, situacao: aguardando, expedido_em: null, recebido_em: null,
      itens: [item(203, PAO, 'UN', '7.000'), item(204, BAGUETE, 'KG', '2.000')] },
  ]
}

export function romaneioDetalhe(data: string, extra: Partial<RomaneioDetalhe> = {}): RomaneioDetalhe {
  return {
    id: 30, ordem_id: 7, data_producao: data, data_entrega: data, status: 'rascunho', gerado_em: '2026-10-28T12:00:00',
    aprovado_em: null, desatualizado: false,
    producao: [
      { produto: PAO, unidade: 'UN', tipo_abastecimento: 'produzido', planejado: '19.000', produzido: '10.000', total_final: '10.000' },
      { produto: BAGUETE, unidade: 'KG', tipo_abastecimento: 'produzido', planejado: '4.500', produzido: '4.500', total_final: '4.500' },
    ],
    entregas: entregas(),
    ...extra,
  }
}

/** Ordem do dia com o resumo do romaneio, como a lista do dia devolve. */
export function ordemComRomaneio(r: RomaneioDetalhe): OrdemDistribuicao {
  const situacoes: Record<string, number> = {}
  for (const e of r.entregas) situacoes[e.situacao.situacao] = (situacoes[e.situacao.situacao] ?? 0) + 1
  return ordemDoDia(r.data_entrega, {
    itens: itensProducao(['10.000', '4.500']),
    romaneio: { id: r.id, status: r.status, entregas: r.entregas.length, situacoes },
  })
}
