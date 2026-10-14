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
