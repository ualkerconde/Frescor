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
  it('"/" abre a visão geral, com o cabeçalho mostrando gestor, central e negócio', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/')
    expect(
      await screen.findByRole('heading', { level: 1, name: /^(Bom dia|Boa tarde|Boa noite), Gestor$/ }),
    ).toBeInTheDocument()
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

  it('navegação: Perdas marcado como página atual; clicar em Consultar troca a tela', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME), 'GET /web/lojas': resposta(200, []), 'GET /web/perdas/lancamentos': resposta(200, []) })
    renderizarApp('/perdas')
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    expect(await within(nav).findByRole('link', { name: 'Perdas' })).toHaveAttribute('aria-current', 'page')
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

  it('menu por seções (padrão 11/11/2026): rótulos das seções e as 9 telas na ordem; a carga de CSV fica fora (D107)', () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    for (const secao of ['Visão', 'Dados', 'Planejamento', 'Operação', 'Configuração'])
      expect(within(nav).getByText(secao)).toBeInTheDocument()
    expect(within(nav).getAllByRole('link').map((l) => l.textContent)).toEqual([
      'Visão geral',
      'Acompanhamento',
      'Consultar',
      'Previsão',
      'Produção',
      'Distribuição',
      'Perdas',
      'Cadastros',
      'Integração de vendas',
    ])
    // Fora do menu, a carga de histórico ainda diz onde está na barra do topo.
    const barra = screen.getByRole('region', { name: 'Barra superior' })
    expect(within(barra).getByText('Configuração')).toBeInTheDocument()
    expect(within(barra).getByText('Carga de histórico')).toBeInTheDocument()
  })

  it('barra superior mostra a seção e a tela atual', () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/consultar')
    const barra = screen.getByRole('region', { name: 'Barra superior' })
    expect(within(barra).getByText('Dados')).toBeInTheDocument()
    expect(within(barra).getByText('Consultar')).toBeInTheDocument()
  })

  it('busca de telas: Ctrl K abre, digitar filtra e Enter abre a tela', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    const usuario = userEvent.setup()
    await usuario.keyboard('{Control>}k{/Control}')
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar tela' })
    await usuario.type(within(dialogo).getByRole('combobox'), 'consul')
    expect(within(dialogo).queryByText('Previsão')).not.toBeInTheDocument()
    await usuario.keyboard('{Enter}')
    expect(await screen.findByRole('heading', { level: 1, name: 'Consultar vendas e perdas' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('busca de telas também abre pelo botão da barra superior', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    await userEvent.click(screen.getByRole('button', { name: /Buscar tela/ }))
    expect(await screen.findByRole('dialog', { name: 'Buscar tela' })).toBeInTheDocument()
  })

  it('"Sair" não é botão primário (a ação principal é da tela)', () => {
    simularApi({ 'GET /web/me': resposta(200, ME) })
    renderizarApp('/importar')
    expect(screen.getByRole('button', { name: 'Sair' }).className).not.toContain('bg-primary')
  })
})
