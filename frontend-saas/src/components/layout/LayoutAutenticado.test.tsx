import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { lerTokens, salvarTokens } from '@/lib/api/sessao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

beforeEach(() => {
  localStorage.clear()
  salvarTokens('A1', 'R1')
})
afterEach(() => vi.unstubAllGlobals())

describe('estrutura das telas autenticadas (W5)', () => {
  it('"/" abre a importação, com o cabeçalho mostrando gestor, central e negócio', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Importar vendas e perdas' })).toBeInTheDocument()
    const cabecalho = screen.getByRole('banner')
    expect(await within(cabecalho).findByText('Gestor Central Teste')).toBeInTheDocument()
    expect(within(cabecalho).getByText('Central Principal · Rede Padaria Teste')).toBeInTheDocument()
    expect(within(cabecalho).getByText('Frescor')).toBeInTheDocument()
  })

  it('enquanto carrega o gestor, mostra "Carregando…"', () => {
    simularApi({ 'GET /web/me': () => new Promise<Response>(() => {}) })
    renderizarApp('/importar')
    expect(within(screen.getByRole('banner')).getByText('Carregando…')).toBeInTheDocument()
  })

  it('navegação: Importar marcado como página atual; clicar em Consultar troca a tela', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    expect(within(nav).getByRole('link', { name: 'Importar' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Consultar' })).not.toHaveAttribute('aria-current')

    await userEvent.click(within(nav).getByRole('link', { name: 'Consultar' }))

    expect(screen.getByRole('heading', { level: 1, name: 'Consultar vendas e perdas' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Consultar' })).toHaveAttribute('aria-current', 'page')
  })

  it('"Sair": apaga os tokens, limpa os dados em cache e volta ao login sem aviso', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    const { queryClient } = renderizarApp('/importar')
    await screen.findByText('Gestor Central Teste')
    expect(queryClient.getQueryData(['me'])).toEqual(ME)

    await userEvent.click(screen.getByRole('button', { name: 'Sair' }))

    expect(screen.getByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(lerTokens()).toEqual({ accessToken: null, refreshToken: null })
    expect(queryClient.getQueryData(['me'])).toBeUndefined()
  })

  it('falha ao carregar o gestor (servidor): avisa no cabeçalho e a tela continua usável', async () => {
    simularApi({ 'GET /web/me': resposta(500, 'erro') })
    renderizarApp('/importar')
    expect(await screen.findByText('Não foi possível carregar seus dados.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Importar vendas' })).toBeInTheDocument()
  })

  it('acesso revogado (403 no /web/me): volta ao login mostrando o motivo', async () => {
    const motivo = 'A central de produção vinculada ao seu usuário está inativa. Fale com o administrador.'
    simularApi({ 'GET /web/me': resposta(403, { detail: motivo }) })
    renderizarApp('/importar')
    expect(await screen.findByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(motivo)
  })

  it('tem o link "Pular para o conteúdo" apontando para a área principal', () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    expect(screen.getByRole('link', { name: 'Pular para o conteúdo' })).toHaveAttribute('href', '#conteudo')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'conteudo')
  })

  it('"Sair" não é botão primário (a ação principal é da tela)', () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    expect(screen.getByRole('button', { name: 'Sair' }).className).not.toContain('bg-primary')
  })
})
