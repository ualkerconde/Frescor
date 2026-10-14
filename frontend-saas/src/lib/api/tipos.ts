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
