import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { Acompanhamento } from '@/lib/api/tipos'
import { dataIso, somarDias } from '@/lib/formato'
import { LISTA } from '@/test/cadastros'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

/* Acompanhamento (D115/D116): previsto × pedido × produzido × enviado × vendido × perda. */

async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } })
  return resultado.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

const LOJAS = [
  { id: 1, codigo: '001', nome: 'Loja Centro', ativo: true },
  { id: 2, codigo: '002', nome: 'Loja Bairro', ativo: true },
]
const vazio = { previsto: null, sugerido: null, final: null, produzido: null, enviado: null, vendido: null, perda: null }

function dados(extra: Partial<Acompanhamento> = {}): Acompanhamento {
  return {
    data_inicio: '2026-10-05',
    data_fim: '2026-10-06',
    produzido_disponivel: true,
    unidades: [
      {
        unidade: 'UN',
        totais: { previsto: '27.0000', sugerido: '16.000', final: '18.000', produzido: '20.000', enviado: '12.000', vendido: '26.000', perda: '1.000' },
        erro: { wape: '0.1154', vies: '0.0385', celulas: 3 },
        dias: [
          { data: '2026-10-05', previsto: '15.0000', sugerido: '16.000', final: '18.000', produzido: '20.000', enviado: '12.000', vendido: '14.000', perda: '1.000' },
          { data: '2026-10-06', ...vazio, previsto: '12.0000', vendido: '12.000' },
        ],
      },
      {
        unidade: 'KG',
        totais: { ...vazio, previsto: '2.5000', vendido: '2.000' },
        erro: { wape: '0.2500', vies: '0.2500', celulas: 1 },
        dias: [
          { data: '2026-10-05', ...vazio, previsto: '2.5000', vendido: '2.000' },
          { data: '2026-10-06', ...vazio },
        ],
      },
    ],
    produtos: [
      {
        produto: { id: 17, codigo: 'INT-007', nome: 'Pão Francês' }, unidade: 'UN',
        totais: { previsto: '27.0000', sugerido: '16.000', final: '18.000', produzido: '20.000', enviado: '12.000', vendido: '26.000', perda: '1.000' },
        erro: { wape: '0.1154', vies: '-0.0600', celulas: 3 }, sobra: '-15.000',
      },
    ],
    ...extra,
  }
}

type Fetch = ReturnType<typeof simularApi>
const chamadas = (fetch: Fetch, trecho: string) => fetch.mock.calls.filter(([url]) => String(url).includes(trecho))

function api(d: Acompanhamento) {
  return simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /web/lojas': resposta(200, LOJAS),
    'GET /web/produtos': resposta(200, LISTA),
    'GET /web/acompanhamento': () => resposta(200, d),
  })
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

describe('acompanhamento (D115/D116)', () => {
  it('padrão: 7 dias até ontem; um bloco por unidade com erro, viés, vendido e perda', async () => {
    const fetch = api(dados())
    renderizarApp('/acompanhamento')
    const un = await screen.findByRole('region', { name: 'Produtos em unidade (un)' })
    expect(screen.getByRole('region', { name: 'Produtos em quilo (kg)' })).toBeInTheDocument()
    expect(within(un).getByText('11,5%')).toBeInTheDocument()
    expect(within(un).getByText('+3,9%')).toBeInTheDocument()
    expect(within(un).getByText('A previsão ficou acima da venda.')).toBeInTheDocument()
    expect(within(un).getByText('3,8% do vendido.')).toBeInTheDocument()
    const ontem = somarDias(dataIso(new Date()), -1)
    const url = String(chamadas(fetch, '/web/acompanhamento')[0][0])
    expect(url).toContain(`data_inicio=${somarDias(ontem, -6)}`)
    expect(url).toContain(`data_fim=${ontem}`)
    expect(await violacoes()).toEqual([])
  })

  it('totais do período e dia a dia na unidade certa; dia sem registro mostra traço', async () => {
    api(dados())
    renderizarApp('/acompanhamento')
    const un = await screen.findByRole('region', { name: 'Produtos em unidade (un)' })
    const totais = within(un).getByRole('list', { name: 'Totais do período' })
    expect(within(totais).getAllByRole('listitem').map((l) => l.textContent)).toEqual([
      'Previsto27 un', 'Sugerido16 un', 'Pedido18 un', 'Produzido20 un', 'Enviado12 un', 'Vendido26 un', 'Perda1 un',
    ])
    const tabela = within(un).getByRole('table', { name: 'Dia a dia: Produtos em unidade (un)' })
    const [, d1, d2] = within(tabela).getAllByRole('row')
    expect(d1).toHaveTextContent('05/10 seg15 un16 un18 un20 un12 un14 un1 un')
    expect(d2).toHaveTextContent('06/10 ter12 un————12 un—')
  })

  it('com loja escolhida, a produção sai das colunas e o aviso explica', async () => {
    api(dados({ produzido_disponivel: false }))
    renderizarApp('/acompanhamento')
    expect(await screen.findByText(/a produção fica de fora/)).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Produzido' })).not.toBeInTheDocument()
    const un = screen.getByRole('region', { name: 'Produtos em unidade (un)' })
    const totais = within(un).getByRole('list', { name: 'Totais do período' })
    expect(within(totais).queryByText('Produzido')).not.toBeInTheDocument()
  })

  it('por produto: erro, viés negativo e sobra', async () => {
    api(dados())
    renderizarApp('/acompanhamento')
    const tabela = await screen.findByRole('table', { name: 'Por produto' })
    const [, pao] = within(tabela).getAllByRole('row')
    expect(pao).toHaveTextContent('INT-007 · Pão Francês27 un18 un20 un12 un26 un1 un11,5%−6%-15 un')
  })

  it('passar o mouse no gráfico mostra o dia', async () => {
    api(dados())
    renderizarApp('/acompanhamento')
    const un = await screen.findByRole('region', { name: 'Produtos em unidade (un)' })
    const grafico = within(un).getByRole('img', { name: /Previsto × vendido por dia/ })
    grafico.getBoundingClientRect = () => ({ left: 0, top: 0, width: 720, height: 240, right: 720, bottom: 240, x: 0, y: 0, toJSON: () => ({}) })
    fireEvent.pointerMove(grafico, { clientX: 50, clientY: 100 })
    expect(await within(un).findByText('segunda, 05/10/2026')).toBeInTheDocument()
  })

  it('sem nada no período: explica', async () => {
    api(dados({ unidades: [], produtos: [] }))
    renderizarApp('/acompanhamento')
    expect(await screen.findByText(/nem previsão, nem pedido, nem venda/)).toBeInTheDocument()
  })

  it('período maior que 28 dias não consulta', async () => {
    const fetch = api(dados())
    renderizarApp('/acompanhamento')
    await screen.findByRole('region', { name: 'Produtos em unidade (un)' })
    const inicio = screen.getByLabelText('Data inicial')
    await userEvent.clear(inicio)
    await userEvent.type(inicio, '2026-01-01')
    await userEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    expect(screen.getByText('O período pode ter até 28 dias.')).toBeInTheDocument()
    await waitFor(() => expect(chamadas(fetch, '/web/acompanhamento')).toHaveLength(1))
  })
})
