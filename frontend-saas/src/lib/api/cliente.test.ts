import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ErroApi,
  MENSAGEM_DADOS_INVALIDOS,
  MENSAGEM_SEM_CONEXAO,
  MENSAGEM_SERVIDOR,
  MENSAGEM_SESSAO_EXPIRADA,
  apiFetch,
  apiJson,
  apiUpload,
  entrar,
} from './cliente'
import { aoEncerrarSessao, lerTokens, salvarTokens } from './sessao'

/** Resposta JSON como o backend devolveria. */
function resposta(status: number, corpo: unknown = {}): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } })
}

let fetchSimulado: ReturnType<typeof vi.fn>
let motivosFimDeSessao: string[]
let pararDeOuvir: () => void

/** Cabeçalho Authorization enviado na chamada de índice `i`. */
function tokenEnviado(i: number): string | null {
  const init = fetchSimulado.mock.calls[i][1] as RequestInit
  return new Headers(init.headers).get('Authorization')
}

beforeEach(() => {
  localStorage.clear()
  fetchSimulado = vi.fn()
  vi.stubGlobal('fetch', fetchSimulado)
  motivosFimDeSessao = []
  pararDeOuvir = aoEncerrarSessao((motivo) => motivosFimDeSessao.push(motivo))
})

afterEach(() => {
  pararDeOuvir()
  vi.unstubAllGlobals()
})

describe('entrar (login do gestor)', () => {
  it('chama /auth/web/login com JSON, sem token, e guarda os dois tokens', async () => {
    fetchSimulado.mockResolvedValueOnce(resposta(200, { access_token: 'A1', refresh_token: 'R1' }))
    await entrar('gestor@teste.com', 'senha123')

    const [url, init] = fetchSimulado.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/backend/auth/web/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ email: 'gestor@teste.com', senha: 'senha123' })
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(tokenEnviado(0)).toBeNull()
    expect(lerTokens()).toEqual({ accessToken: 'A1', refreshToken: 'R1' })
  })

  it('401: lança a mensagem da API, não guarda nada e não tenta renovar', async () => {
    fetchSimulado.mockResolvedValueOnce(resposta(401, { detail: 'E-mail ou senha incorretos.' }))
    await expect(entrar('x@teste.com', 'errada')).rejects.toMatchObject({
      status: 401,
      message: 'E-mail ou senha incorretos.',
    })
    expect(fetchSimulado).toHaveBeenCalledTimes(1)
    expect(lerTokens()).toEqual({ accessToken: null, refreshToken: null })
  })

  it('403: lança a mensagem da API (ex.: operador de loja)', async () => {
    fetchSimulado.mockResolvedValueOnce(resposta(403, { detail: 'Acesso restrito a gestores de central de produção.' }))
    await expect(entrar('admin@teste.com', 'senha123')).rejects.toMatchObject({
      status: 403,
      message: 'Acesso restrito a gestores de central de produção.',
    })
    expect(motivosFimDeSessao).toEqual([]) // login recusado não é "fim de sessão"
  })
})

describe('apiFetch (chamadas autenticadas)', () => {
  it('manda o access token do SaaS', async () => {
    salvarTokens('A1', 'R1')
    fetchSimulado.mockResolvedValueOnce(resposta(200, { ok: true }))
    await apiJson('/web/me')
    expect(tokenEnviado(0)).toBe('Bearer A1')
  })

  it('401: renova uma vez e repete a chamada com o token novo', async () => {
    salvarTokens('VELHO', 'R1')
    fetchSimulado
      .mockResolvedValueOnce(resposta(401, { detail: 'Não foi possível validar as credenciais.' }))
      .mockResolvedValueOnce(resposta(200, { access_token: 'NOVO' }))
      .mockResolvedValueOnce(resposta(200, { nome: 'Gestor' }))

    const dados = await apiJson<{ nome: string }>('/web/me')

    expect(dados).toEqual({ nome: 'Gestor' })
    expect(fetchSimulado).toHaveBeenCalledTimes(3)
    expect(fetchSimulado.mock.calls[1][0]).toBe('/backend/auth/web/refresh')
    expect(JSON.parse((fetchSimulado.mock.calls[1][1] as RequestInit).body as string)).toEqual({ refresh_token: 'R1' })
    expect(tokenEnviado(2)).toBe('Bearer NOVO')
    expect(lerTokens()).toEqual({ accessToken: 'NOVO', refreshToken: 'R1' })
    expect(motivosFimDeSessao).toEqual([])
  })

  it('duas chamadas com 401 ao mesmo tempo fazem um único refresh', async () => {
    salvarTokens('VELHO', 'R1')
    fetchSimulado.mockImplementation(async (url: string, init: RequestInit) => {
      if (url.endsWith('/auth/web/refresh')) return resposta(200, { access_token: 'NOVO' })
      return new Headers(init.headers).get('Authorization') === 'Bearer NOVO' ? resposta(200, {}) : resposta(401)
    })

    await Promise.all([apiJson('/web/me'), apiJson('/web/lojas')])

    const refreshes = fetchSimulado.mock.calls.filter(([url]) => (url as string).endsWith('/auth/web/refresh'))
    expect(refreshes).toHaveLength(1)
  })

  it('refresh recusado (401): encerra a sessão com "sessão expirou"', async () => {
    salvarTokens('VELHO', 'R1')
    fetchSimulado.mockResolvedValueOnce(resposta(401)).mockResolvedValueOnce(resposta(401, { detail: 'Sessão expirada.' }))

    await expect(apiJson('/web/me')).rejects.toMatchObject({ status: 401, message: MENSAGEM_SESSAO_EXPIRADA })
    expect(motivosFimDeSessao).toEqual([MENSAGEM_SESSAO_EXPIRADA])
    expect(lerTokens()).toEqual({ accessToken: null, refreshToken: null })
  })

  it('refresh recusado com 403 (central desativada): encerra a sessão com o motivo da API', async () => {
    const motivo = 'A central de produção vinculada ao seu usuário está inativa. Fale com o administrador.'
    salvarTokens('VELHO', 'R1')
    fetchSimulado.mockResolvedValueOnce(resposta(401)).mockResolvedValueOnce(resposta(403, { detail: motivo }))

    await expect(apiJson('/web/me')).rejects.toBeInstanceOf(ErroApi)
    expect(motivosFimDeSessao).toEqual([motivo])
  })

  it('sem refresh token guardado: encerra a sessão sem chamar o refresh', async () => {
    localStorage.setItem('frescor_web_access_token', 'A1')
    fetchSimulado.mockResolvedValueOnce(resposta(401))

    await expect(apiJson('/web/me')).rejects.toMatchObject({ status: 401 })
    expect(fetchSimulado).toHaveBeenCalledTimes(1)
    expect(motivosFimDeSessao).toEqual([MENSAGEM_SESSAO_EXPIRADA])
  })

  it('repete só uma vez: se a repetição também der 401, encerra a sessão', async () => {
    salvarTokens('VELHO', 'R1')
    fetchSimulado
      .mockResolvedValueOnce(resposta(401))
      .mockResolvedValueOnce(resposta(200, { access_token: 'NOVO' }))
      .mockResolvedValueOnce(resposta(401))

    await expect(apiJson('/web/me')).rejects.toMatchObject({ status: 401 })
    expect(fetchSimulado).toHaveBeenCalledTimes(3)
    expect(motivosFimDeSessao).toEqual([MENSAGEM_SESSAO_EXPIRADA])
  })

  it('403 numa chamada autenticada (acesso revogado): encerra a sessão com o motivo', async () => {
    const motivo = 'Seu usuário não tem permissão para acessar o sistema web. Fale com o administrador.'
    salvarTokens('A1', 'R1')
    fetchSimulado.mockResolvedValueOnce(resposta(403, { detail: motivo }))

    await expect(apiJson('/web/lojas')).rejects.toMatchObject({ status: 403, message: motivo })
    expect(motivosFimDeSessao).toEqual([motivo])
  })

  it('404 não encerra a sessão e traz a mensagem da API', async () => {
    salvarTokens('A1', 'R1')
    fetchSimulado.mockResolvedValueOnce(resposta(404, { detail: 'Loja não encontrada.' }))
    await expect(apiJson('/vendas?loja_id=9')).rejects.toMatchObject({ status: 404, message: 'Loja não encontrada.' })
    expect(motivosFimDeSessao).toEqual([])
    expect(lerTokens().accessToken).toBe('A1')
  })
})

describe('mensagens de erro (sem código técnico na tela)', () => {
  beforeEach(() => salvarTokens('A1', 'R1'))

  it('sem conexão: mensagem de conexão, e a sessão continua', async () => {
    fetchSimulado.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(apiJson('/web/me')).rejects.toMatchObject({ status: 0, message: MENSAGEM_SEM_CONEXAO })
    expect(lerTokens().accessToken).toBe('A1')
    expect(motivosFimDeSessao).toEqual([])
  })

  it('500: mensagem genérica de servidor', async () => {
    fetchSimulado.mockResolvedValueOnce(new Response('Internal Server Error', { status: 500 }))
    await expect(apiJson('/web/me')).rejects.toMatchObject({ status: 500, message: MENSAGEM_SERVIDOR })
  })

  it('422 de validação do FastAPI (lista de campos): mensagem sem jargão', async () => {
    fetchSimulado.mockResolvedValueOnce(
      resposta(422, { detail: [{ type: 'missing', loc: ['query', 'data_inicio'], msg: 'Field required' }] }),
    )
    const erro = (await apiJson('/vendas').catch((e: unknown) => e)) as ErroApi
    expect(erro).toMatchObject({ status: 422, message: MENSAGEM_DADOS_INVALIDOS })
    expect(erro.message).not.toMatch(/422|Field required/)
  })

  it('422 com relatório (importação): mantém o corpo inteiro para a tela', async () => {
    const relatorio = { sucesso: false, erros: [{ linha: 3, mensagem: 'data inexistente' }] }
    fetchSimulado.mockResolvedValueOnce(resposta(422, relatorio))
    const erro = (await apiFetch('/vendas/importar', { method: 'POST' }).catch((e) => e)) as ErroApi
    expect(erro.status).toBe(422)
    expect(erro.corpo).toEqual(relatorio)
  })
})

describe('apiUpload (envio de arquivo)', () => {
  it('não força Content-Type (o navegador monta o multipart) e manda o token', async () => {
    salvarTokens('A1', 'R1')
    fetchSimulado.mockResolvedValueOnce(resposta(200, { sucesso: true }))
    const formulario = new FormData()
    formulario.append('arquivo', new Blob(['data;codigo_loja\r\n'], { type: 'text/csv' }), 'vendas.csv')

    await apiUpload('/vendas/importar', formulario)

    const init = fetchSimulado.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Content-Type')).toBeNull()
    expect(init.body).toBe(formulario)
    expect(tokenEnviado(0)).toBe('Bearer A1')
  })
})
