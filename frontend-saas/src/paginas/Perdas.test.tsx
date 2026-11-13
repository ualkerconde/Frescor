import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { LancamentoPerda } from '@/lib/api/tipos'
import { dataIso, somarDias } from '@/lib/formato'
import { LISTA } from '@/test/cadastros'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

/* Perdas (D110): o gestor vê, lança e corrige os lançamentos das lojas. */

async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } })
  return resultado.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

const LOJAS = [
  { id: 1, codigo: '001', nome: 'Loja Centro', ativo: true },
  { id: 2, codigo: '002', nome: 'Loja Bairro', ativo: true },
]
const HOJE = dataIso(new Date())

function lancamento(extra: Partial<LancamentoPerda> = {}): LancamentoPerda {
  return {
    id: 50, data: '2026-11-10', loja: { id: 1, codigo: '001', nome: 'Loja Centro' },
    produto: { id: 17, codigo: 'INT-007', nome: 'Pão Francês' }, unidade: 'KG', quantidade: '1.500',
    motivo: 'vencido', observacao: null, lancado_por: 'Ana', lancado_em: '2026-11-10T20:00:00',
    alterado_por: null, alterado_em: null, loja_pode_alterar: true, ...extra,
  }
}

type Fetch = ReturnType<typeof simularApi>
const chamadas = (fetch: Fetch, metodo: string, trecho: string) =>
  fetch.mock.calls.filter(([url, init]) => String(url).includes(trecho) && (init?.method ?? 'GET') === metodo)
const corpo = (fetch: Fetch, metodo: string, trecho: string) =>
  JSON.parse(String(chamadas(fetch, metodo, trecho)[0][1]?.body))

function api(lista: LancamentoPerda[], extras: Parameters<typeof simularApi>[0] = {}) {
  let atual = [...lista]
  return simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /web/lojas': resposta(200, LOJAS),
    'GET /web/produtos': resposta(200, LISTA),
    'GET /web/perdas/lancamentos': () => resposta(200, atual),
    'POST /web/perdas/lancamentos': (init) => {
      const c = JSON.parse(String(init.body))
      const novo = lancamento({ id: 60, data: c.data, quantidade: c.quantidade, motivo: c.motivo, observacao: c.observacao })
      atual = [novo, ...atual]
      return resposta(201, novo)
    },
    'PUT /web/perdas/lancamentos/50': (init) => {
      const c = JSON.parse(String(init.body))
      atual = atual.map((l) => (l.id === 50 ? { ...l, ...c, alterado_por: 'Gestor' } : l))
      return resposta(200, atual.find((l) => l.id === 50))
    },
    'DELETE /web/perdas/lancamentos/50': () => {
      atual = atual.filter((l) => l.id !== 50)
      return new Response(null, { status: 204 })
    },
    ...extras,
  })
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

describe('perdas (D110)', () => {
  it('lista os últimos 7 dias com total, motivo e quem lançou; sem violações de acessibilidade', async () => {
    const fetch = api([
      lancamento(),
      lancamento({ id: 51, produto: { id: 18, codigo: 'INT-020', nome: 'Bolo' }, unidade: 'UN', quantidade: '3.000',
        motivo: 'outro', observacao: 'Caiu', alterado_por: 'Gestor' }),
    ])
    renderizarApp('/perdas')
    const tabela = await screen.findByRole('table', { name: 'Lançamentos de perda' })
    const [, pao, bolo] = within(tabela).getAllByRole('row')
    expect(pao).toHaveTextContent('10/11/2026001 · Loja CentroPão Francês1,5 kgVencidoAna')
    expect(bolo).toHaveTextContent('3 unOutroCaiuAnaCorrigido por Gestor')
    expect(screen.getByText('2 lançamentos · total 3 un · 1,5 kg')).toBeInTheDocument()
    const url = String(chamadas(fetch, 'GET', '/web/perdas/lancamentos')[0][0])
    expect(url).toContain(`data_inicio=${somarDias(HOJE, -6)}`)
    expect(url).toContain(`data_fim=${HOJE}`)
    expect(screen.getByRole('heading', { level: 1, name: 'Perdas' })).toBeInTheDocument()
    expect(await violacoes()).toEqual([])
  })

  it('sem lançamentos: explica que sem registro não dá para saber se perdeu', async () => {
    api([])
    renderizarApp('/perdas')
    expect(await screen.findByText(/não sabe se a loja não perdeu nada ou se não lançou/)).toBeInTheDocument()
  })

  it('filtro de período inválido não consulta', async () => {
    const fetch = api([])
    renderizarApp('/perdas')
    await screen.findByText(/Nenhuma perda lançada/)
    const fim = screen.getByLabelText('Data final')
    await userEvent.clear(fim)
    await userEvent.type(fim, '2020-01-01')
    await userEvent.click(screen.getByRole('button', { name: 'Filtrar' }))
    expect(screen.getByText('A data final não pode ser antes da inicial.')).toBeInTheDocument()
    expect(chamadas(fetch, 'GET', '/web/perdas/lancamentos')).toHaveLength(1)
  })

  it('lança por uma loja, com validação antes de enviar', async () => {
    const fetch = api([])
    renderizarApp('/perdas')
    await screen.findByText(/Nenhuma perda lançada/)
    await userEvent.click(screen.getByRole('button', { name: 'Lançar perda' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Lançar perda' })
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Lançar perda' }))
    expect(within(dialogo).getByText('Escolha a loja.')).toBeInTheDocument()
    expect(within(dialogo).getByText('Escolha o produto.')).toBeInTheDocument()
    expect(within(dialogo).getByText(/quantidade maior que zero/)).toBeInTheDocument()
    expect(within(dialogo).getByText('Escolha o motivo.')).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/web/perdas/lancamentos')).toHaveLength(0)

    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Loja' }))
    await userEvent.click(await screen.findByRole('option', { name: '002 · Loja Bairro' }))
    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Produto' }))
    await userEvent.click(await screen.findByRole('option', { name: 'INT-007 · Pão Francês' }))
    const dia = within(dialogo).getByLabelText('Dia da perda')
    await userEvent.clear(dia)
    await userEvent.type(dia, '2026-11-09')
    await userEvent.type(within(dialogo).getByLabelText(/Quantidade perdida/), '2,5')
    await userEvent.click(within(dialogo).getByRole('radio', { name: 'Outro' }))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Lançar perda' }))
    expect(within(dialogo).getByText(/escreva numa linha o que aconteceu/)).toBeInTheDocument()
    await userEvent.type(within(dialogo).getByLabelText('O que aconteceu?'), 'Queimou no forno')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Lançar perda' }))

    await waitFor(() => expect(chamadas(fetch, 'POST', '/web/perdas/lancamentos')).toHaveLength(1))
    expect(corpo(fetch, 'POST', '/web/perdas/lancamentos')).toEqual({
      loja_id: 2, produto_id: 17, data: '2026-11-09', quantidade: '2.5', motivo: 'outro', observacao: 'Queimou no forno',
    })
    expect(await screen.findByText(/Perda lançada: Pão Francês, 2,5 kg em 09\/11\/2026/)).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Lançamentos de perda' })).toBeInTheDocument()
  })

  it('erro da API fica no diálogo', async () => {
    api([], { 'POST /web/perdas/lancamentos': resposta(422, { detail: 'Este produto é contado por unidade: a quantidade tem de ser inteira.' }) })
    renderizarApp('/perdas')
    await screen.findByText(/Nenhuma perda lançada/)
    await userEvent.click(screen.getByRole('button', { name: 'Lançar perda' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Lançar perda' })
    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Loja' }))
    await userEvent.click(await screen.findByRole('option', { name: '001 · Loja Centro' }))
    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Produto' }))
    await userEvent.click(await screen.findByRole('option', { name: 'INT-007 · Pão Francês' }))
    await userEvent.type(within(dialogo).getByLabelText(/Quantidade perdida/), '1,5')
    await userEvent.click(within(dialogo).getByRole('radio', { name: 'Avariado' }))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Lançar perda' }))
    expect(await within(dialogo).findByText(/A perda não foi lançada. Este produto é contado por unidade/)).toBeInTheDocument()
  })

  it('corrige quantidade e motivo, sem mudar loja, produto nem dia', async () => {
    const fetch = api([lancamento()])
    renderizarApp('/perdas')
    await userEvent.click(await screen.findByRole('button', { name: /Corrigir: Pão Francês/ }))
    const dialogo = await screen.findByRole('dialog', { name: 'Corrigir lançamento de perda' })
    expect(within(dialogo).queryByRole('combobox', { name: 'Loja' })).not.toBeInTheDocument()
    const campo = within(dialogo).getByLabelText('Quantidade perdida (kg)')
    expect(campo).toHaveValue('1,5')
    await userEvent.clear(campo)
    await userEvent.type(campo, '2')
    await userEvent.click(within(dialogo).getByRole('radio', { name: 'Avariado' }))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Salvar correção' }))
    await waitFor(() => expect(chamadas(fetch, 'PUT', '/web/perdas/lancamentos/50')).toHaveLength(1))
    expect(corpo(fetch, 'PUT', '/web/perdas/lancamentos/50')).toEqual({ quantidade: '2', motivo: 'avariado', observacao: null })
    expect(await screen.findByText(/Lançamento corrigido/)).toBeInTheDocument()
  })

  it('apagar pede confirmação', async () => {
    const fetch = api([lancamento()])
    renderizarApp('/perdas')
    await userEvent.click(await screen.findByRole('button', { name: /Apagar: Pão Francês/ }))
    const dialogo = await screen.findByRole('dialog', { name: 'Apagar este lançamento de perda?' })
    expect(chamadas(fetch, 'DELETE', '/web/perdas/lancamentos/50')).toHaveLength(0)
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Apagar lançamento' }))
    await waitFor(() => expect(chamadas(fetch, 'DELETE', '/web/perdas/lancamentos/50')).toHaveLength(1))
    expect(await screen.findByText(/Nenhuma perda lançada/)).toBeInTheDocument()
  })
})
