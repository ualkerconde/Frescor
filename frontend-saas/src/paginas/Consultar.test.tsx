import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { ConsultaDiaria, ItemDiario, LojaWeb, ProdutosWeb } from '@/lib/api/tipos'
import { dataIso } from '@/lib/formato'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

const LOJAS: LojaWeb[] = [
  { id: 1, codigo: '001', nome: 'Loja Centro', ativo: true },
  { id: 8, codigo: '002', nome: 'Loja Bairro', ativo: true },
  { id: 9, codigo: '003', nome: 'Loja Antiga', ativo: false },
]

const PRODUTOS: ProdutosWeb = {
  total: 2,
  limit: 20,
  offset: 0,
  itens: [
    { id: 17, codigo: 'INT-007', nome: 'Pão Francês', unidade: 'KG', ativo: true },
    { id: 18, codigo: 'INT-008', nome: 'Pão de Forma', unidade: 'KG', ativo: true },
  ],
}

function item(parcial: Partial<ItemDiario> = {}): ItemDiario {
  return {
    data: '2026-09-01',
    loja: { id: 1, codigo: '001' },
    produto: { id: 17, codigo: 'INT-007', nome: 'Pão Francês' },
    quantidade: '3.750',
    unidade: 'KG',
    origem: 'manual',
    ...parcial,
  }
}

function consulta(parcial: Partial<ConsultaDiaria> = {}): ConsultaDiaria {
  return { total: 1, limit: 50, offset: 0, itens: [item()], totais: [], ...parcial }
}

/** Período padrão da tela: 7 dias até ontem. */
function periodoPadrao() {
  const ontem = new Date()
  ontem.setDate(ontem.getDate() - 1)
  const inicio = new Date(ontem)
  inicio.setDate(ontem.getDate() - 6)
  return { inicio: dataIso(inicio), fim: dataIso(ontem) }
}

/** Chamadas feitas a uma rota, com os parâmetros da URL. */
function chamadas(fetchSimulado: ReturnType<typeof simularApi>, caminho: string): URLSearchParams[] {
  return fetchSimulado.mock.calls
    .map(([url]) => new URL(String(url), 'http://localhost'))
    .filter((u) => u.pathname === `/backend${caminho}`)
    .map((u) => u.searchParams)
}

type Rotas = Parameters<typeof simularApi>[0]

function api(extra: Rotas = {}) {
  return simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /web/lojas': resposta(200, LOJAS),
    'GET /web/produtos': resposta(200, PRODUTOS),
    'GET /vendas': (_init, url) =>
      url.searchParams.get('limit') === '1'
        ? resposta(200, consulta({ totais: [{ unidade: 'UN', quantidade: '171.000' }, { unidade: 'KG', quantidade: '3.750' }] }))
        : resposta(200, consulta({ itens: [item(), item({ data: '2026-09-02', loja: { id: 8, codigo: '002' }, quantidade: '40.000', unidade: 'UN', origem: 'api', produto: { id: 11, codigo: 'INT-001', nome: 'Croissant' } })], total: 2 })),
    'GET /perdas': (_init, url) =>
      url.searchParams.get('limit') === '1'
        ? resposta(200, consulta({ totais: [{ unidade: 'UN', quantidade: '2.000' }] }))
        : resposta(200, consulta({ itens: [item({ quantidade: '0.500' })] })),
    ...extra,
  })
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('A1', 'R1')
})
afterEach(() => vi.unstubAllGlobals())

describe('tela de consulta (W7)', () => {
  it('abre com os últimos 7 dias até ontem e já consulta vendas e perdas desse período', async () => {
    const fetchSimulado = api()
    renderizarApp('/consultar')
    const { inicio, fim } = periodoPadrao()
    expect(screen.getByLabelText('Data inicial')).toHaveValue(inicio)
    expect(screen.getByLabelText('Data final')).toHaveValue(fim)
    await screen.findByRole('table', { name: 'Vendas do período' })
    for (const caminho of ['/vendas', '/perdas']) {
      const p = chamadas(fetchSimulado, caminho)[0]
      expect(p.get('data_inicio')).toBe(inicio)
      expect(p.get('data_fim')).toBe(fim)
      expect(p.has('loja_id')).toBe(false)
      expect(p.has('produto_id')).toBe(false)
    }
  })

  it('resumo no topo: total vendido e de perda, por unidade, antes da tabela', async () => {
    api()
    renderizarApp('/consultar')
    const resumo = await screen.findByRole('region', { name: 'Resumo do período' })
    expect(await within(resumo).findByText('171 un')).toBeInTheDocument()
    expect(within(resumo).getByText('3,75 kg')).toBeInTheDocument()
    expect(within(resumo).getByText('2 un')).toBeInTheDocument()
    expect(within(resumo).getByText('Vendido no período')).toBeInTheDocument()
    expect(within(resumo).getByText('Perda no período')).toBeInTheDocument()
    const tabela = await screen.findByRole('table')
    // o resumo vem antes da tabela no documento
    expect(resumo.compareDocumentPosition(tabela) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('tabela: data dd/mm/aaaa, loja com nome, produto, quantidade com unidade à direita e origem em português', async () => {
    api()
    renderizarApp('/consultar')
    const tabela = await screen.findByRole('table', { name: 'Vendas do período' })
    const linhas = within(tabela).getAllByRole('row')
    expect(within(linhas[1]).getByText('01/09/2026')).toBeInTheDocument()
    expect(within(linhas[1]).getByText('001 · Loja Centro')).toBeInTheDocument()
    expect(within(linhas[1]).getByText('INT-007 · Pão Francês')).toBeInTheDocument()
    const qtd = within(linhas[1]).getByText('3,75 kg')
    expect(qtd.className).toContain('text-right')
    expect(within(linhas[1]).getByText('Importação')).toBeInTheDocument()
    expect(within(linhas[2]).getByText('40 un')).toBeInTheDocument()
    expect(within(linhas[2]).getByText('PDV')).toBeInTheDocument()
  })

  it('uma única ação principal: "Consultar"', async () => {
    api()
    renderizarApp('/consultar')
    await screen.findByRole('table')
    const primarios = within(screen.getByRole('main'))
      .getAllByRole('button')
      .filter((b) => b.className.includes('bg-primary'))
    expect(primarios.map((b) => b.textContent)).toEqual(['Consultar'])
  })

  it('"Perdas" troca a tabela e consulta /perdas', async () => {
    const fetchSimulado = api()
    renderizarApp('/consultar')
    await screen.findByRole('table', { name: 'Vendas do período' })
    await userEvent.click(screen.getByRole('radio', { name: 'Perdas' }))
    const tabela = await screen.findByRole('table', { name: 'Perdas do período' })
    expect(within(tabela).getByText('0,5 kg')).toBeInTheDocument()
    expect(chamadas(fetchSimulado, '/perdas').some((p) => p.get('limit') === '50')).toBe(true)
  })

  it('paginação de 50: "Mostrando 1–50 de 120 linhas", Próxima pede offset 50, Anterior desabilitado na 1ª', async () => {
    const fetchSimulado = api({
      'GET /vendas': (_init, url) =>
        resposta(200, consulta({ total: 120, offset: Number(url.searchParams.get('offset')), itens: [item()] })),
    })
    renderizarApp('/consultar')
    expect(await screen.findByText('Mostrando 1–50 de 120 linhas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Próxima' }))
    expect(await screen.findByText('Mostrando 51–100 de 120 linhas')).toBeInTheDocument()
    expect(chamadas(fetchSimulado, '/vendas').some((p) => p.get('offset') === '50' && p.get('limit') === '50')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Próxima' }))
    expect(await screen.findByText('Mostrando 101–120 de 120 linhas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Próxima' })).toBeDisabled()
  })

  it('filtro de loja: escolhe "002 · Loja Bairro" e consulta com loja_id', async () => {
    const fetchSimulado = api()
    renderizarApp('/consultar')
    await screen.findByRole('table')
    const usuario = userEvent.setup()
    await usuario.click(screen.getByRole('combobox', { name: 'Loja' }))
    expect(await screen.findByRole('option', { name: '003 · Loja Antiga (inativa)' })).toBeInTheDocument()
    await usuario.click(screen.getByRole('option', { name: '002 · Loja Bairro' }))
    await usuario.click(screen.getByRole('button', { name: 'Consultar' }))
    await waitFor(() => expect(chamadas(fetchSimulado, '/vendas').some((p) => p.get('loja_id') === '8')).toBe(true))
    expect(chamadas(fetchSimulado, '/perdas').some((p) => p.get('loja_id') === '8')).toBe(true)
    expect(await screen.findByText(/· loja 002/)).toBeInTheDocument()
  })

  it('busca de produto usa /web/produtos (o backend ignora acentos) e filtra por produto_id', async () => {
    const fetchSimulado = api()
    renderizarApp('/consultar')
    await screen.findByRole('table')
    const usuario = userEvent.setup()
    await usuario.click(screen.getByRole('combobox', { name: 'Produto' }))
    await usuario.type(screen.getByRole('combobox', { name: 'Buscar produto' }), 'pao')
    await waitFor(() => expect(chamadas(fetchSimulado, '/web/produtos').some((p) => p.get('busca') === 'pao')).toBe(true))
    await usuario.click(await screen.findByRole('option', { name: 'INT-007 · Pão Francês' }))
    expect(screen.getByRole('combobox', { name: 'Produto' })).toHaveTextContent('INT-007 · Pão Francês')
    await usuario.click(screen.getByRole('button', { name: 'Consultar' }))
    await waitFor(() => expect(chamadas(fetchSimulado, '/vendas').some((p) => p.get('produto_id') === '17')).toBe(true))
  })

  it('data inicial depois da final: explica e não consulta', async () => {
    const fetchSimulado = api()
    renderizarApp('/consultar')
    await screen.findByRole('table')
    const antes = fetchSimulado.mock.calls.length
    const usuario = userEvent.setup()
    await usuario.clear(screen.getByLabelText('Data inicial'))
    await usuario.type(screen.getByLabelText('Data inicial'), '2026-09-30')
    await usuario.clear(screen.getByLabelText('Data final'))
    await usuario.type(screen.getByLabelText('Data final'), '2026-09-01')
    await usuario.click(screen.getByRole('button', { name: 'Consultar' }))
    expect(screen.getByText('A data inicial é depois da final. Confira o período.')).toBeInTheDocument()
    expect(screen.getByLabelText('Data inicial')).toHaveAttribute('aria-invalid', 'true')
    expect(fetchSimulado.mock.calls.length).toBe(antes)
  })

  it('período acima de 366 dias: explica e não consulta', async () => {
    api()
    renderizarApp('/consultar')
    await screen.findByRole('table')
    const usuario = userEvent.setup()
    await usuario.clear(screen.getByLabelText('Data inicial'))
    await usuario.type(screen.getByLabelText('Data inicial'), '2025-01-01')
    await usuario.clear(screen.getByLabelText('Data final'))
    await usuario.type(screen.getByLabelText('Data final'), '2026-09-01')
    await usuario.click(screen.getByRole('button', { name: 'Consultar' }))
    expect(screen.getByText(/o máximo é 366\. Escolha um período menor\./)).toBeInTheDocument()
  })

  it('filtros na URL: abrir com inicio, fim e tipo=perdas já consulta isso', async () => {
    const fetchSimulado = api()
    renderizarApp('/consultar?inicio=2026-09-01&fim=2026-09-30&tipo=perdas')
    expect(await screen.findByRole('table', { name: 'Perdas do período' })).toBeInTheDocument()
    expect(screen.getByLabelText('Data inicial')).toHaveValue('2026-09-01')
    expect(screen.getByRole('radio', { name: 'Perdas' })).toBeChecked()
    const p = chamadas(fetchSimulado, '/perdas').find((x) => x.get('limit') === '50')!
    expect(p.get('data_inicio')).toBe('2026-09-01')
    expect(p.get('data_fim')).toBe('2026-09-30')
    expect(screen.getByText(/Período de 01\/09\/2026 a 30\/09\/2026/)).toBeInTheDocument()
  })

  it('sem dados: estado vazio útil com o caminho para importar', async () => {
    api({
      'GET /vendas': resposta(200, consulta({ total: 0, itens: [], totais: [] })),
      'GET /perdas': resposta(200, consulta({ total: 0, itens: [], totais: [] })),
    })
    renderizarApp('/consultar')
    expect(await screen.findByText('Nenhuma venda importada neste período.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Importar CSV' })).toHaveAttribute('href', '/importar')
    expect(screen.getByText('Nenhuma venda no período.')).toBeInTheDocument()
    expect(screen.getByText('Nenhuma perda no período.')).toBeInTheDocument()
  })

  it('erro da API na consulta: mensagem em português, sem código', async () => {
    api({ 'GET /vendas': resposta(500, 'erro') })
    renderizarApp('/consultar')
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('O servidor não respondeu como esperado. Tente de novo em alguns minutos.')
    expect(document.body.textContent).not.toMatch(/\b500\b/)
  })
})
