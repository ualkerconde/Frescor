import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MENSAGEM_SEM_CONEXAO } from '@/lib/api/cliente'
import { encerrarSessao, lerTokens, salvarTokens } from '@/lib/api/sessao'
import { ME, renderizarApp, resposta } from '@/test/renderizar'

let fetchSimulado: ReturnType<typeof vi.fn>

function abrir(rota = '/entrar') {
  renderizarApp(rota)
}

/** Título da primeira tela depois do login (W6). */
const TELA_INICIAL = { name: 'Importar vendas e perdas' }

async function preencherEEntrar(email: string, senha: string) {
  const usuario = userEvent.setup()
  if (email) await usuario.type(screen.getByLabelText('E-mail'), email)
  if (senha) await usuario.type(screen.getByLabelText('Senha'), senha)
  await usuario.click(screen.getByRole('button', { name: 'Entrar' }))
}

beforeEach(() => {
  localStorage.clear()
  // Padrão: a área autenticada busca /web/me; os testes de login trocam a
  // resposta do login com mockResolvedValueOnce.
  fetchSimulado = vi.fn(async (url: string) =>
    url.endsWith('/web/me') ? resposta(200, ME) : resposta(404, { detail: 'rota não simulada' }),
  )
  vi.stubGlobal('fetch', fetchSimulado)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('tela de login', () => {
  it('mostra o nome Frescor, campos com label e um único botão: "Entrar"', () => {
    abrir()
    expect(screen.getByText('Frescor')).toBeInTheDocument()
    expect(screen.getByLabelText('E-mail')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('Senha')).toHaveAttribute('type', 'password')
    const botoes = screen.getAllByRole('button')
    expect(botoes).toHaveLength(1)
    expect(botoes[0]).toHaveAccessibleName('Entrar')
    expect(botoes[0].className).toContain('bg-primary')
  })

  it('campos vazios: erro em cada campo, foco no e-mail, nada enviado', async () => {
    abrir()
    await preencherEEntrar('', '')
    expect(screen.getByText('Informe o e-mail.')).toBeInTheDocument()
    expect(screen.getByText('Informe a senha.')).toBeInTheDocument()
    expect(screen.getByLabelText('E-mail')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('E-mail')).toHaveAccessibleDescription('Informe o e-mail.')
    expect(screen.getByLabelText('E-mail')).toHaveFocus()
    expect(fetchSimulado).not.toHaveBeenCalled()
  })

  it('e-mail sem domínio: explica o formato e não envia', async () => {
    abrir()
    await preencherEEntrar('gestor', 'senha123')
    expect(screen.getByText(/precisa ter @ e um domínio/)).toBeInTheDocument()
    expect(fetchSimulado).not.toHaveBeenCalled()
  })

  it('só a senha vazia: foco na senha', async () => {
    abrir()
    await preencherEEntrar('gestor@teste.com', '')
    expect(screen.getByText('Informe a senha.')).toBeInTheDocument()
    expect(screen.queryByText('Informe o e-mail.')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Senha')).toHaveFocus()
  })

  it('401: "E-mail ou senha incorretos." + o que fazer, sem código de erro na tela', async () => {
    fetchSimulado.mockResolvedValueOnce(resposta(401, { detail: 'E-mail ou senha incorretos.' }))
    abrir()
    await preencherEEntrar('gestor@teste.com', 'errada')
    const alerta = await screen.findByRole('alert')
    expect(within(alerta).getByText('E-mail ou senha incorretos.')).toBeInTheDocument()
    expect(within(alerta).getByText('Confira os dados e tente de novo.')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\b(401|403|422|500)\b/)
    expect(screen.getByLabelText('E-mail')).toHaveValue('gestor@teste.com') // não apaga o que foi digitado
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeEnabled()
  })

  it('403 de operador de loja: mensagem da API + orientação para o app', async () => {
    fetchSimulado.mockResolvedValueOnce(resposta(403, { detail: 'Acesso restrito a gestores de central de produção.' }))
    abrir()
    await preencherEEntrar('admin@teste.com', 'senha123')
    const alerta = await screen.findByRole('alert')
    expect(within(alerta).getByText('Acesso restrito a gestores de central de produção.')).toBeInTheDocument()
    expect(within(alerta).getByText(/app do celular/)).toBeInTheDocument()
  })

  it('403 com outro motivo (central inativa): mostra o motivo da API', async () => {
    const motivo = 'A central de produção vinculada ao seu usuário está inativa. Fale com o administrador.'
    fetchSimulado.mockResolvedValueOnce(resposta(403, { detail: motivo }))
    abrir()
    await preencherEEntrar('gestor@teste.com', 'senha123')
    expect(await screen.findByText(motivo)).toBeInTheDocument()
  })

  it('sem conexão: mensagem de conexão', async () => {
    fetchSimulado.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    abrir()
    await preencherEEntrar('gestor@teste.com', 'senha123')
    expect(await screen.findByText(MENSAGEM_SEM_CONEXAO)).toBeInTheDocument()
  })

  it('enquanto envia: botão "Entrando…" desabilitado (sem clique duplo)', async () => {
    let liberar: (r: Response) => void = () => {}
    fetchSimulado.mockReturnValueOnce(new Promise<Response>((r) => (liberar = r)))
    abrir()
    await preencherEEntrar('gestor@teste.com', 'senha123')
    const botao = screen.getByRole('button', { name: 'Entrando…' })
    expect(botao).toBeDisabled()
    await userEvent.click(botao)
    expect(fetchSimulado).toHaveBeenCalledTimes(1)
    await act(async () => liberar(resposta(200, { access_token: 'A1', refresh_token: 'R1' })))
  })

  it('sucesso: guarda os tokens e abre a área autenticada', async () => {
    fetchSimulado.mockResolvedValueOnce(resposta(200, { access_token: 'A1', refresh_token: 'R1' }))
    abrir()
    await preencherEEntrar('  gestor@teste.com ', 'senha123')
    expect(await screen.findByRole('heading', TELA_INICIAL)).toBeInTheDocument()
    expect(lerTokens()).toEqual({ accessToken: 'A1', refreshToken: 'R1' })
    const corpo = JSON.parse((fetchSimulado.mock.calls[0][1] as RequestInit).body as string)
    expect(corpo).toEqual({ email: 'gestor@teste.com', senha: 'senha123' }) // e-mail sem espaços
  })
})

describe('sessão e rotas', () => {
  it('sem sessão, a área autenticada manda para o login', () => {
    abrir('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
  })

  it('com sessão, /entrar manda para a área autenticada', () => {
    salvarTokens('A1', 'R1')
    abrir('/entrar')
    expect(screen.getByRole('heading', TELA_INICIAL)).toBeInTheDocument()
  })

  it('sessão encerrada sozinha: volta ao login mostrando o motivo', () => {
    salvarTokens('A1', 'R1')
    abrir('/')
    act(() => encerrarSessao('Sua sessão expirou. Entre de novo para continuar.'))
    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Sua sessão expirou. Entre de novo para continuar.')
  })

  it('"Sair": apaga os tokens e volta ao login sem aviso', async () => {
    salvarTokens('A1', 'R1')
    abrir('/')
    await userEvent.click(screen.getByRole('button', { name: 'Sair' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(lerTokens()).toEqual({ accessToken: null, refreshToken: null })
  })
})
