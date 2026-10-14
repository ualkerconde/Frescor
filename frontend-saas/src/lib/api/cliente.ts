/*
 * Cliente da API do SaaS (passo W3).
 *
 * - Chamadas vão para /backend/... (proxy do Vite -> backend), ou para
 *   VITE_API_URL se definido.
 * - Manda o access token do SaaS em toda chamada autenticada.
 * - 401: tenta renovar a sessão em /auth/web/refresh UMA vez e repete a
 *   chamada uma vez. Várias chamadas que recebem 401 ao mesmo tempo
 *   compartilham o mesmo refresh.
 * - Refresh recusado, ou 403 numa chamada autenticada (acesso revogado,
 *   central desativada...): encerra a sessão com o motivo, e a tela volta
 *   ao login mostrando esse motivo.
 * - Corpo FormData (upload de CSV): NÃO define Content-Type, para o
 *   navegador montar o multipart com o boundary.
 * - Erros viram ErroApi com uma mensagem em português para mostrar na tela
 *   (skill Frescor: nada de "Erro 422"; o que houve + o que fazer).
 */

import { encerrarSessao, lerTokens, salvarTokens } from './sessao'

const BASE = import.meta.env.VITE_API_URL ?? '/backend'

const ROTAS_SEM_RENOVACAO = ['/auth/web/login', '/auth/web/refresh']

export const MENSAGEM_SEM_CONEXAO =
  'Não foi possível falar com o servidor. Confira sua conexão e tente de novo.'
export const MENSAGEM_SESSAO_EXPIRADA = 'Sua sessão expirou. Entre de novo para continuar.'
export const MENSAGEM_SERVIDOR = 'O servidor não respondeu como esperado. Tente de novo em alguns minutos.'
export const MENSAGEM_DADOS_INVALIDOS = 'Alguns dados enviados não são válidos. Confira e tente de novo.'

/** Erro de uma chamada à API, com a mensagem pronta para a tela. */
export class ErroApi extends Error {
  readonly status: number
  /** Corpo `detail` original da API (string, lista de validação ou relatório). */
  readonly detalhe: unknown
  /** Corpo inteiro da resposta (ex.: relatório de importação no 422). */
  readonly corpo: unknown

  constructor(status: number, mensagem: string, detalhe?: unknown, corpo?: unknown) {
    super(mensagem)
    this.name = 'ErroApi'
    this.status = status
    this.detalhe = detalhe
    this.corpo = corpo
  }
}

/** Traduz uma resposta de erro numa mensagem para a tela. */
export function mensagemDeErro(status: number, corpo: unknown): string {
  const detalhe = typeof corpo === 'object' && corpo !== null ? (corpo as { detail?: unknown }).detail : undefined
  // As mensagens do backend já são frases em português para o usuário.
  if (typeof detalhe === 'string' && detalhe.trim() !== '') return detalhe
  if (status >= 500) return MENSAGEM_SERVIDOR
  // 422 de validação do FastAPI (lista de campos): sem jargão na tela.
  if (status === 422) return MENSAGEM_DADOS_INVALIDOS
  if (status === 401) return MENSAGEM_SESSAO_EXPIRADA
  return MENSAGEM_SERVIDOR
}

async function lerCorpo(resposta: Response): Promise<unknown> {
  const texto = await resposta.text()
  if (texto === '') return null
  try {
    return JSON.parse(texto)
  } catch {
    return texto
  }
}

async function erroDaResposta(resposta: Response): Promise<ErroApi> {
  const corpo = await lerCorpo(resposta)
  const detalhe = typeof corpo === 'object' && corpo !== null ? (corpo as { detail?: unknown }).detail : undefined
  return new ErroApi(resposta.status, mensagemDeErro(resposta.status, corpo), detalhe, corpo)
}

async function chamar(caminho: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${BASE}${caminho}`, init)
  } catch {
    throw new ErroApi(0, MENSAGEM_SEM_CONEXAO)
  }
}

function cabecalhos(init: RequestInit, comToken: boolean): Headers {
  const headers = new Headers(init.headers)
  if (comToken) {
    const { accessToken } = lerTokens()
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return headers
}

// ---- renovação da sessão (compartilhada entre chamadas simultâneas) ----

type ResultadoRenovacao = { ok: true } | { ok: false; motivo: string }
let renovacaoEmAndamento: Promise<ResultadoRenovacao> | null = null

async function renovar(): Promise<ResultadoRenovacao> {
  const { refreshToken } = lerTokens()
  if (!refreshToken) return { ok: false, motivo: MENSAGEM_SESSAO_EXPIRADA }
  // Sem conexão, `chamar` lança ErroApi(0): a chamada falha, mas a sessão
  // NÃO é encerrada (não é culpa do gestor nem do token).
  const resposta = await chamar('/auth/web/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (resposta.ok) {
    const corpo = (await resposta.json()) as { access_token: string }
    salvarTokens(corpo.access_token)
    return { ok: true }
  }
  // 403: o gestor perdeu o acesso (ex.: central desativada) -> motivo da API.
  const erro = await erroDaResposta(resposta)
  return { ok: false, motivo: resposta.status === 403 ? erro.message : MENSAGEM_SESSAO_EXPIRADA }
}

function renovarUmaVez(): Promise<ResultadoRenovacao> {
  if (!renovacaoEmAndamento) {
    renovacaoEmAndamento = renovar().finally(() => {
      renovacaoEmAndamento = null
    })
  }
  return renovacaoEmAndamento
}

/**
 * Chamada autenticada. Devolve a Response se ela for 2xx; senão lança ErroApi.
 * `autenticar: false` só para rotas públicas (login).
 */
export async function apiFetch(caminho: string, init: RequestInit = {}, autenticar = true): Promise<Response> {
  let resposta = await chamar(caminho, { ...init, headers: cabecalhos(init, autenticar) })

  if (resposta.status === 401 && autenticar && !ROTAS_SEM_RENOVACAO.includes(caminho)) {
    const renovacao = await renovarUmaVez()
    if (!renovacao.ok) {
      encerrarSessao(renovacao.motivo)
      throw new ErroApi(401, renovacao.motivo)
    }
    resposta = await chamar(caminho, { ...init, headers: cabecalhos(init, true) })
    if (resposta.status === 401) {
      encerrarSessao(MENSAGEM_SESSAO_EXPIRADA)
      throw new ErroApi(401, MENSAGEM_SESSAO_EXPIRADA)
    }
  }

  if (resposta.ok) return resposta

  const erro = await erroDaResposta(resposta)
  // 403 numa chamada autenticada do SaaS = o gestor perdeu o acesso.
  if (resposta.status === 403 && autenticar) encerrarSessao(erro.message)
  throw erro
}

/** Chamada que manda e/ou recebe JSON. */
export async function apiJson<T>(
  caminho: string,
  opcoes: { method?: string; json?: unknown; autenticar?: boolean } = {},
): Promise<T> {
  const init: RequestInit = { method: opcoes.method ?? 'GET' }
  if (opcoes.json !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(opcoes.json)
  }
  const resposta = await apiFetch(caminho, init, opcoes.autenticar ?? true)
  return (await lerCorpo(resposta)) as T
}

/** Envio de arquivo (multipart). O navegador define o Content-Type. */
export async function apiUpload<T>(caminho: string, formulario: FormData): Promise<T> {
  const resposta = await apiFetch(caminho, { method: 'POST', body: formulario })
  return (await lerCorpo(resposta)) as T
}

// ---- autenticação do gestor ----

interface TokensResposta {
  access_token: string
  refresh_token: string
}

/** Login do gestor. Lança ErroApi com a mensagem da API (401/403) se falhar. */
export async function entrar(email: string, senha: string): Promise<void> {
  const tokens = await apiJson<TokensResposta>('/auth/web/login', {
    method: 'POST',
    json: { email, senha },
    autenticar: false,
  })
  salvarTokens(tokens.access_token, tokens.refresh_token)
}
