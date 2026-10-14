/*
 * Verificação automática de acessibilidade (passo W8) com o axe-core, nas
 * telas e nos estados principais: login (vazio e com erro), importação
 * (vazia, com sucesso e com erros) e consulta (com dados e vazia).
 *
 * Limitação: no jsdom o axe não calcula contraste de cor (não há
 * renderização real). Os contrastes são garantidos pelo tema.test.ts, que
 * confere as cores da skill Frescor e recalcula a razão de contraste.
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, {
    rules: { 'color-contrast': { enabled: false } },
  })
  return resultado.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  )
}

const LOJAS = [{ id: 1, codigo: '001', nome: 'Loja Centro', ativo: true }]
const CONSULTA = {
  total: 1,
  limit: 50,
  offset: 0,
  itens: [
    {
      data: '2026-09-01',
      loja: { id: 1, codigo: '001' },
      produto: { id: 17, codigo: 'INT-007', nome: 'Pão Francês' },
      quantidade: '3.750',
      unidade: 'KG',
      origem: 'manual',
    },
  ],
  totais: [{ unidade: 'KG', quantidade: '3.750' }],
}
const RELATORIO_OK = { sucesso: true, linhas_lidas: 2, inseridas: 2, substituidas: 0, codificacao: 'utf-8', erros: [], erros_omitidos: 0, avisos: [{ linha: 2, mensagem: 'produto não habilitado' }], avisos_omitidos: 0 }
const RELATORIO_ERRO = { ...RELATORIO_OK, sucesso: false, inseridas: 0, erros: [{ linha: 3, mensagem: 'data inexistente' }] }

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('acessibilidade (axe-core, WCAG)', () => {
  it('login vazio', async () => {
    simularApi()
    renderizarApp('/entrar')
    expect(await violacoes()).toEqual([])
  })

  it('login com erros de campo e do servidor', async () => {
    simularApi({ 'POST /auth/web/login': resposta(401, { detail: 'E-mail ou senha incorretos.' }) })
    renderizarApp('/entrar')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await violacoes()).toEqual([])
    await userEvent.type(screen.getByLabelText('E-mail'), 'gestor@teste.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await screen.findByRole('alert')
    expect(await violacoes()).toEqual([])
  })

  describe('telas autenticadas', () => {
    beforeEach(() => salvarTokens('A1', 'R1'))

    it('importação: vazia, com sucesso e com erros', async () => {
      let relatorio: { status: number; corpo: unknown } = { status: 200, corpo: RELATORIO_OK }
      simularApi({
        'GET /web/me': resposta(200, ME),
        'POST /vendas/importar': () => resposta(relatorio.status, relatorio.corpo),
      })
      renderizarApp('/importar')
      await screen.findByText('Gestor Central Teste')
      expect(await violacoes()).toEqual([])

      const arquivo = new File(['data;codigo_loja;codigo_produto;quantidade\r\n'], 'v.csv', { type: 'text/csv' })
      await userEvent.upload(screen.getByLabelText('Arquivo CSV'), arquivo)
      await userEvent.click(screen.getByRole('button', { name: 'Importar vendas' }))
      await screen.findByRole('heading', { name: '2 linhas importadas' })
      expect(await violacoes()).toEqual([])

      relatorio = { status: 422, corpo: RELATORIO_ERRO }
      await userEvent.click(screen.getByRole('button', { name: 'Importar vendas' }))
      await screen.findByRole('heading', { name: 'Nada foi gravado: 1 erro' })
      expect(await violacoes()).toEqual([])
    })

    it('consulta com dados', async () => {
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /web/lojas': resposta(200, LOJAS),
        'GET /vendas': resposta(200, CONSULTA),
        'GET /perdas': resposta(200, CONSULTA),
      })
      renderizarApp('/consultar')
      await screen.findByRole('table')
      expect(await violacoes()).toEqual([])
    })

    it('consulta vazia', async () => {
      const vazia = { ...CONSULTA, total: 0, itens: [], totais: [] }
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /web/lojas': resposta(200, LOJAS),
        'GET /vendas': resposta(200, vazia),
        'GET /perdas': resposta(200, vazia),
      })
      renderizarApp('/consultar')
      await screen.findByText('Nenhuma venda importada neste período.')
      expect(await violacoes()).toEqual([])
    })
  })
})
