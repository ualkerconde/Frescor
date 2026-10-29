/*
 * Formatos das respostas da API usados pelas telas. Espelham os schemas
 * do backend (app/schemas/web.py e app/schemas/importacao.py).
 */

/** GET /web/me */
export interface Me {
  usuario: { id: number; nome: string; email: string }
  central: { id: number; nome: string }
  negocio: { id: number; nome: string }
}

export interface MensagemLinha {
  /** Linha do arquivo (o cabeçalho é a linha 1; 0 = o arquivo como um todo). */
  linha: number
  mensagem: string
}

/** Relatório de POST /vendas/importar e /perdas/importar (200 e 422). */
export interface RelatorioImportacao {
  sucesso: boolean
  linhas_lidas: number
  inseridas: number
  substituidas: number
  codificacao: string
  erros: MensagemLinha[]
  erros_omitidos: number
  avisos: MensagemLinha[]
  avisos_omitidos: number
}

export type TipoImportacao = 'vendas' | 'perdas'

/** GET /web/lojas (lojas da central do gestor). */
export interface LojaWeb {
  id: number
  codigo: string | null
  nome: string
  ativo: boolean
}

export type Unidade = 'UN' | 'KG'

/** Item de GET /web/produtos. */
export interface ProdutoWeb {
  id: number
  codigo: string | null
  nome: string
  unidade: Unidade
  ativo: boolean
  // Fase 6 (lista do cadastro):
  tipo_abastecimento?: TipoAbastecimento
  setor?: string | null
  lojas_ativas?: number
}

export interface ProdutosWeb {
  total: number
  limit: number
  offset: number
  itens: ProdutoWeb[]
}

/** Item de GET /vendas e /perdas. `quantidade` vem como texto decimal ("1.250"). */
export interface ItemDiario {
  data: string // AAAA-MM-DD
  loja: { id: number; codigo: string | null }
  produto: { id: number; codigo: string | null; nome: string }
  quantidade: string
  unidade: Unidade
  origem: 'manual' | 'api' | 'inferida'
}

export interface TotalPorUnidade {
  unidade: Unidade
  quantidade: string
}

/** GET /vendas e /perdas. */
export interface ConsultaDiaria {
  total: number
  limit: number
  offset: number
  itens: ItemDiario[]
  totais: TotalPorUnidade[]
}

// ---- previsão (Fase 3 / F8; backend/app/schemas/previsao.py) ----
// Números decimais chegam como texto ("40.0000"); null = sem valor.

export interface EventoAplicado {
  id: number
  nome: string
  tipo_ajuste: 'multiplicador' | 'valor_fixo'
  valor_ajuste: string
}

/** Item de GET /previsoes: o número do dia e as peças que o compõem. */
export interface ItemPrevisao {
  data: string // AAAA-MM-DD
  loja: { id: number; codigo: string | null; nome: string }
  produto: { id: number; codigo: string | null; nome: string }
  unidade: Unidade
  /** null = sem histórico, sem proxy e sem evento de valor fixo. */
  previsao: string | null
  previsao_sem_evento: string | null
  /** Só com o histórico do produto na loja (base × tendência). */
  previsao_propria: string | null
  /** null = a loja não tem dado daquele dia. */
  venda_semana_passada: string | null
  metodo: 'semanal' | 'sazonal'
  estatistica: string
  base: string | null
  semanas_na_base: number
  /** Fator aplicado, já limitado a 0,7–1,3. */
  tendencia: string
  /** Antes do limite; null = poucos dias para calcular (fator 1). */
  tendencia_bruta: string | null
  dias_na_tendencia: number
  inicio_historico: string | null
  /** 0 a 1; menor que 1 = pouco histórico (cold start). */
  peso_historico: string
  pouco_historico: boolean
  proxy: string | null
  origem_proxy: 'outras_lojas' | 'categoria' | 'unidade' | null
  eventos: EventoAplicado[]
  data_referencia: string
  gerado_em: string
  versao_metodo: string
}

export interface TotalPrevisto {
  unidade: Unidade
  previsto: string
  vendido_semana_passada: string
}

/** GET /previsoes. Lista vazia = ainda não gerou para esse dia. */
export interface Previsoes {
  data: string
  itens: ItemPrevisao[]
  totais: TotalPrevisto[]
}

/** POST /previsoes/gerar */
export interface GeracaoPrevisoes {
  data_referencia: string
  data_inicio: string
  data_fim: string
  gravadas: number
  sem_previsao: number
  substituidas: number
  versao_metodo: string
}

/** Métricas por unidade; frações com 4 casas ("0.1165" = 11,65%). */
export interface QualidadeUnidade {
  unidade: Unidade
  pares: number
  wape: string | null
  vies: string | null
  ingenuo_wape: string | null
  ingenuo_vies: string | null
  vence_ingenuo: boolean | null
}

/** GET /previsoes/qualidade */
export interface QualidadePrevisao {
  data_inicio: string
  data_fim: string
  por_unidade: QualidadeUnidade[]
}

// ---- Ordem de produção (Fase 4 / N7) ----

/** POST /producao/ordens/gerar */
export interface GeracaoOrdem {
  ordem_id: number
  data_producao: string
  data_entrega: string
  itens: number
  linhas: number
  sem_quantidade: number
  substituiu_rascunho: boolean
  previsao_atualizada: boolean
}

/**
 * A conta da necessidade gravada em cada linha (backend: ResultadoNecessidade
 * + pouco_historico e taxa_perda). Números chegam como texto decimal.
 */
export interface ContaNecessidade {
  data_producao: string
  chegada: string | null
  dias_cobertura: string[]
  dias_cobertura_sem_limite: number
  dias_ate_chegada: string[]
  minimo: string | null
  margem: string | null
  origem_margem: 'produto' | 'padrao' | 'pouco_historico' | null
  alvo: string | null
  estoque_contado: string | null
  contagem_valida: boolean
  contagem_local: string | null
  limite_contagem_local: string | null
  estoque_considerado: string
  transito_considerado: string
  /** Entregas confirmadas no prazo depois da contagem válida (D79 (2), Fase 5). */
  recebido_apos_contagem?: string
  /** Entregas sem confirmação presumidas recebidas pela final (D79 (4)); já estão na contagem. */
  recebimento_presumido?: string
  consumo_ate_chegada: string
  vencido_ate_chegada: string
  estoque_na_chegada: string | null
  necessidade_bruta: string | null
  necessidade: string | null
  avisos: string[]
  pouco_historico?: boolean
  /** Perda ÷ venda das 4 semanas até a véspera (fração); null = sem venda. */
  taxa_perda?: string | null
}

export interface TotalOrdem {
  unidade: Unidade
  sugerido: string
  final: string
}

export interface LinhaOrdem {
  id: number
  loja: { id: number; codigo: string | null; nome: string }
  quantidade_sugerida: string | null
  quantidade_final: string | null
  editada: boolean
  editado_em: string | null
  motivo_edicao: string | null
  avisos: string[]
  componentes: Partial<ContaNecessidade>
}

export interface ItemOrdem {
  id: number
  produto: { id: number; codigo: string | null; nome: string }
  tipo_abastecimento: 'produzido' | 'distribuido'
  unidade: Unidade
  total_sugerido: string
  total_final: string
  linhas: LinhaOrdem[]
}

export interface OrdemResumo {
  id: number
  data_producao: string
  data_entrega: string
  tipo: 'programada' | 'emergencial'
  status: 'rascunho' | 'aprovada'
  versao_metodo: string
  referencia_previsao: string | null
  gerado_em: string
  gerado_por: string | null
  aprovado_em: string | null
  aprovado_por: string | null
  linhas: number
  linhas_editadas: number
  linhas_sem_quantidade: number
  totais: TotalOrdem[]
}

/** GET /producao/ordens/{id} */
export interface OrdemDetalhe extends OrdemResumo {
  itens: ItemOrdem[]
}

/** GET /producao/setores (D67) */
export interface SetorProducao {
  id: number
  nome: string
  ordem: number
  ativo: boolean
}

/** GET /producao/ordens?data= */
export interface OrdensDoDia {
  data_producao: string
  ordens: OrdemResumo[]
}

// ---- Distribuição e romaneio (Fase 5 / E6) ----

export interface Referencia {
  id: number
  codigo: string | null
  nome: string
}

/** Situação da entrega, calculada na leitura (D79, D85). */
export type SituacaoEntrega = 'aguardando_saida' | 'a_caminho' | 'sem_confirmacao' | 'recebida' | 'confirmada_com_atraso'

export interface ItemProducao {
  item_id: number
  produto: Referencia
  unidade: Unidade
  tipo_abastecimento: 'produzido' | 'distribuido'
  /** Soma das finais da ordem (D54). */
  planejado: string
  /** null = produção ainda não registrada (D69). */
  produzido: string | null
  registrado_em: string | null
}

export interface ResumoRomaneio {
  id: number
  status: 'rascunho' | 'aprovado'
  entregas: number
  situacoes: Partial<Record<SituacaoEntrega, number>>
}

export interface OrdemDistribuicao {
  ordem_id: number
  data_producao: string
  data_entrega: string
  status_ordem: 'rascunho' | 'aprovada'
  itens: ItemProducao[]
  romaneio: ResumoRomaneio | null
}

/** GET /distribuicao/romaneios?data_entrega= */
export interface DistribuicaoDoDia {
  data_entrega: string
  ordens: OrdemDistribuicao[]
}

/** POST /distribuicao/ordens/{id}/producao */
export interface ResultadoProducao {
  itens_registrados: number
  /** Havia um rascunho do romaneio: ele não foi refeito (D87). */
  romaneio_desatualizado: boolean
}

/** POST /distribuicao/romaneios/gerar */
export interface GeracaoRomaneio {
  romaneio_id: number
  ordem_id: number
  entregas: number
  itens: number
  produtos_com_escassez: number[]
  produtos_com_sobra: number[]
  substituiu_rascunho: boolean
}

export interface SituacaoDaEntrega {
  situacao: SituacaoEntrega
  pode_confirmar: boolean
  com_diferenca: boolean
}

export interface ItemRomaneio {
  id: number
  produto: Referencia
  unidade: Unidade
  quantidade_sugerida: string
  /** O que vai para a loja (é a quantidade expedida, D76). */
  quantidade_final: string
  quantidade_recebida: string | null
  motivo_divergencia: MotivoDivergencia | null
  observacao_divergencia: string | null
  editado_em: string | null
  motivo_edicao: string | null
}

export interface EntregaRomaneio {
  id: number
  loja: Referencia
  situacao: SituacaoDaEntrega
  expedido_em: string | null
  recebido_em: string | null
  itens: ItemRomaneio[]
}

export interface ProducaoRomaneio {
  produto: Referencia
  unidade: Unidade
  tipo_abastecimento: 'produzido' | 'distribuido'
  planejado: string
  produzido: string | null
  /** Soma das finais das lojas; ao aprovar, não pode passar do produzido (D71). */
  total_final: string
}

/** GET /distribuicao/romaneios/{id} */
export interface RomaneioDetalhe {
  id: number
  ordem_id: number
  data_producao: string
  data_entrega: string
  status: 'rascunho' | 'aprovado'
  gerado_em: string
  aprovado_em: string | null
  /** Rascunho com a produção mudada depois de gerado (D87). */
  desatualizado: boolean
  producao: ProducaoRomaneio[]
  entregas: EntregaRomaneio[]
}

/** POST /distribuicao/romaneios/{id}/saida */
export interface ResultadoSaida {
  entregas: number[]
}

export type MotivoDivergencia = 'falta' | 'avaria' | 'a_mais' | 'outro'

export interface Divergencia {
  data_entrega: string
  loja: Referencia
  produto: Referencia
  unidade: Unidade
  quantidade_enviada: string
  quantidade_recebida: string
  /** Recebida − enviada (negativa = chegou menos). */
  diferenca: string
  motivo: MotivoDivergencia
  observacao: string | null
  recebido_em: string
}

/** GET /distribuicao/divergencias */
export interface Divergencias {
  data_inicio: string
  data_fim: string
  divergencias: Divergencia[]
  totais: { unidade: Unidade; enviada: string; recebida: string; diferenca: string }[]
}

// ---------------------------------------------------------------- cadastros (Fase 6)

export type TipoAbastecimento = 'produzido' | 'distribuido'
export type DiaSemana = 'segunda' | 'terca' | 'quarta' | 'quinta' | 'sexta' | 'sabado' | 'domingo'

/** GET /web/central (D103) */
export interface CentralCadastro {
  id: number
  nome: string
  secao: 'padaria' | 'acougue' | 'hortifruti'
  prazo_entrega_dias: number
  ativa: boolean
  lojas: number
}

/** GET /web/produtos/{id} (C2). Decimais chegam como texto. */
export interface ProdutoDetalhe {
  id: number
  codigo: string | null
  nome: string
  codigo_barras: string | null
  unidade: Unidade
  peso_medio_kg: string | null
  ativo: boolean
  tipo_abastecimento: TipoAbastecimento
  dias_validade: number | null
  margem_maxima_percentual: string | null
  data_inicio_vigencia: string | null
  data_fim_vigencia: string | null
  vigencia_recorrente: boolean
  ciclo_previsao: 'semanal' | 'sazonal'
  setor: { id: number; nome: string } | null
  dias_producao: DiaSemana[]
  tem_historico: boolean
}

/** Corpo de POST /web/produtos e PATCH /web/produtos/{id}. */
export interface ProdutoEnvio {
  nome: string
  codigo: string | null
  codigo_barras: string | null
  unidade_medida: Unidade
  peso_medio_kg: string | null
  ativo: boolean
  tipo_abastecimento: TipoAbastecimento
  dias_validade: number | null
  margem_maxima_percentual: string | null
  data_inicio_vigencia: string | null
  data_fim_vigencia: string | null
  vigencia_recorrente: boolean
  ciclo_previsao: 'semanal' | 'sazonal'
  setor_producao_id: number | null
  dias_producao: DiaSemana[]
  habilitar_lojas?: boolean
}

/** GET /web/produtos/{id}/lojas (C3, D100) */
export interface LojaDoProduto {
  loja_id: number
  codigo: string | null
  nome: string
  loja_ativa: boolean
  habilitado: boolean
  ativo: boolean
}

/** GET /eventos (F3, D24) */
export interface Evento {
  id: number
  nome: string
  data_inicio: string
  data_fim: string
  tipo_ajuste: 'multiplicador' | 'valor_fixo'
  valor_ajuste: string
  escopo_loja: 'todas' | 'especificas'
  loja_ids: number[]
  escopo_produto: 'todos' | 'especificos'
  produto_ids: number[]
}
