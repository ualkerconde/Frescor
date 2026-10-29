/*
 * Dados de teste dos cadastros (Fase 6 / C4), no formato da API (C1–C3).
 */
import type { CentralCadastro, LojaDoProduto, ProdutoDetalhe, ProdutosWeb, SetorProducao } from '@/lib/api/tipos'

export const SETORES: SetorProducao[] = [
  { id: 1, nome: 'Pães', ordem: 1, ativo: true },
  { id: 2, nome: 'Bolos', ordem: 2, ativo: true },
  { id: 3, nome: 'Velho', ordem: 3, ativo: false },
]

export const LISTA: ProdutosWeb = {
  total: 2,
  limit: 50,
  offset: 0,
  itens: [
    { id: 17, codigo: 'INT-007', nome: 'Pão Francês', unidade: 'KG', ativo: true, tipo_abastecimento: 'produzido', setor: 'Pães', lojas_ativas: 2 },
    { id: 18, codigo: 'INT-020', nome: 'Manteiga', unidade: 'UN', ativo: false, tipo_abastecimento: 'distribuido', setor: null, lojas_ativas: 0 },
  ],
}

export function produtoDetalhe(extra: Partial<ProdutoDetalhe> = {}): ProdutoDetalhe {
  return {
    id: 17, codigo: 'INT-007', nome: 'Pão Francês', codigo_barras: null, unidade: 'KG', peso_medio_kg: '0.0500',
    ativo: true, tipo_abastecimento: 'produzido', dias_validade: 1, margem_maxima_percentual: null,
    data_inicio_vigencia: null, data_fim_vigencia: null, vigencia_recorrente: false, ciclo_previsao: 'semanal',
    setor: { id: 1, nome: 'Pães' }, dias_producao: ['segunda', 'quarta'], tem_historico: true,
    ...extra,
  }
}

export function lojasDoProduto(): LojaDoProduto[] {
  return [
    { loja_id: 1, codigo: '001', nome: 'Loja Centro', loja_ativa: true, habilitado: true, ativo: true },
    { loja_id: 2, codigo: '002', nome: 'Loja Bairro', loja_ativa: true, habilitado: false, ativo: false },
  ]
}

export const CENTRAL: CentralCadastro = {
  id: 1, nome: 'Central Principal', secao: 'padaria', prazo_entrega_dias: 0, ativa: true, lojas: 2,
}
