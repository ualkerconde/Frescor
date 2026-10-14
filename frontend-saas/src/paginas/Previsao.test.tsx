import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { ItemPrevisao, LojaWeb, Previsoes, QualidadePrevisao } from '@/lib/api/tipos'
import { dataIso, somarDias } from '@/lib/formato'
import { itemPrevisao } from '@/test/previsao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

const LOJAS: LojaWeb[] = [
  { id: 1, codigo: '001', nome: 'Loja Centro', ativo: true },
  { id: 8, codigo: '002', nome: 'Loja Bairro', ativo: true },
]

const hoje = dataIso(new Date())
const amanha = somarDias(hoje, 1)

/** Pão Francês normal, Croissant com pouco histórico, Bolo sem previsão, Sonho com evento. */
function itensPadrao(data: string): ItemPrevisao[] {
  return [
    itemPrevisao({ data }),
    itemPrevisao({
      data,
      produto: { id: 11, codigo: 'INT-001', nome: 'Croissant' },
      unidade: 'UN',
      base: '20.0000',
      previsao_propria: '22.0000',
      pouco_historico: true,
      peso_historico: '0.5000',
      proxy: '30.0000',
      origem_proxy: 'categoria',
      previsao: '26.0000',
      previsao_sem_evento: '26.0000',
      venda_semana_passada: '24.000',
    }),
    itemPrevisao({
      data,
      loja: { id: 8, codigo: '002', nome: 'Loja Bairro' },
      produto: { id: 30, codigo: 'INT-030', nome: 'Bolo de Milho' },
      unidade: 'UN',
      previsao: null,
      previsao_sem_evento: null,
      previsao_propria: null,
      base: null,
      semanas_na_base: 0,
      pouco_historico: true,
      peso_historico: '0',
      inicio_historico: null,
      venda_semana_passada: null,
    }),
    itemPrevisao({
      data,
      produto: { id: 12, codigo: 'INT-002', nome: 'Sonho' },
      unidade: 'UN',
      base: '10.0000',
      previsao_propria: '11.0000',
      previsao_sem_evento: '11.0000',
      previsao: '16.5000',
      venda_semana_passada: '9.000',
      eventos: [{ id: 3, nome: 'Feriado', tipo_ajuste: 'multiplicador', valor_ajuste: '1.5000' }],
    }),
  ]
}

function previsoes(data: string, itens = itensPadrao(data)): Previsoes {
  return {
    data,
    itens,
    totais: [
      { unidade: 'UN', previsto: '42.5000', vendido_semana_passada: '33.000' },
      { unidade: 'KG', previsto: '44.0000', vendido_semana_passada: '41.500' },
    ],
  }
}

const QUALIDADE: QualidadePrevisao = {
  data_inicio: '2026-09-16',
  data_fim: '2026-10-13',
  por_unidade: [
    { unidade: 'KG', pares: 168, wape: '0.0960', vies: '0.0050', ingenuo_wape: '0.1020', ingenuo_vies: '0.0040', vence_ingenuo: true },
    { unidade: 'UN', pares: 448, wape: '0.1030', vies: '-0.0300', ingenuo_wape: '0.0950', ingenuo_vies: '0.0010', vence_ingenuo: false },
  ],
}

function chamadas(fetchSimulado: ReturnType<typeof simularApi>, caminho: string, metodo = 'GET') {
  return fetchSimulado.mock.calls
    .filter(([, init]) => ((init as RequestInit | undefined)?.method ?? 'GET') === metodo)
    .map(([url]) => new URL(String(url), 'http://localhost'))
    .filter((u) => u.pathname === `/backend${caminho}`)
    .map((u) => u.searchParams)
}

type Rotas = Parameters<typeof simularApi>[0]

function api(extra: Rotas = {}) {
  return simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /web/lojas': resposta(200, LOJAS),
    'GET /previsoes': (_init, url) => resposta(200, previsoes(url.searchParams.get('data') ?? amanha)),
    'GET /previsoes/qualidade': resposta(200, QUALIDADE),
    ...extra,
  })
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('A1', 'R1')
})
afterEach(() => vi.unstubAllGlobals())

describe('tela de previsão (F9)', () => {
  it('abre em /previsao pelo menu, com o dia de amanhã, e consulta a previsão desse dia', async () => {
    const fetchSimulado = api()
    renderizarApp('/importar')
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    await userEvent.click(within(nav).getByRole('link', { name: 'Previsão' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Previsão de vendas' })).toBeInTheDocument()
    expect(screen.getByLabelText('Dia previsto')).toHaveValue(amanha)
    await screen.findByRole('table', { name: 'Previsão por loja e produto' })
    const p = chamadas(fetchSimulado, '/previsoes')[0]
    expect(p.get('data')).toBe(amanha)
    expect(p.has('loja_id')).toBe(false)
  })

  it('resumo no topo: previsto por unidade ao lado da semana passada, antes da tabela', async () => {
    api()
    renderizarApp('/previsao')
    const resumo = await screen.findByRole('region', { name: 'Resumo do dia previsto' })
    expect(within(resumo).getByText('42,5 un')).toBeInTheDocument()
    expect(within(resumo).getByText('44 kg')).toBeInTheDocument()
    expect(within(resumo).getByText(/\+29% vs\. semana passada \(33 un\)/)).toBeInTheDocument()
    expect(within(resumo).getByText(/\+6% vs\. semana passada \(41,5 kg\)/)).toBeInTheDocument()
    expect(within(resumo).getByText('Não inclui 1 produto sem previsão.')).toBeInTheDocument()
    expect(within(resumo).getByText('3 com previsão · 1 sem previsão')).toBeInTheDocument()
    const tabela = screen.getByRole('table')
    expect(resumo.compareDocumentPosition(tabela) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('produtos sem previsão e com pouco histórico são citados pelo nome no resumo', async () => {
    api()
    renderizarApp('/previsao')
    const nota = await screen.findByRole('note')
    expect(nota).toHaveTextContent('Confira estes produtos antes de usar os números')
    expect(nota).toHaveTextContent(/Sem previsão.*INT-030 · Bolo de Milho \(loja 002\)/)
    expect(nota).toHaveTextContent(/Pouco histórico.*INT-001 · Croissant \(loja 001\)/)
  })

  it('cada linha traz a explicação curta; produto sem previsão continua na tabela', async () => {
    api()
    renderizarApp('/previsao')
    const tabela = await screen.findByRole('table')
    const linhas = within(tabela).getAllByRole('row')
    expect(linhas).toHaveLength(5) // cabeçalho + 4 produtos
    expect(within(linhas[1]).getByText('001 · Loja Centro')).toBeInTheDocument()
    expect(within(linhas[1]).getByText('44 kg').className).toContain('text-right')
    expect(within(linhas[1]).getByText(/^Mediana das últimas 6 \S+ × tendência \+10%$/)).toBeInTheDocument()
    expect(within(linhas[2]).getByText('Pouco histórico')).toBeInTheDocument()
    expect(within(linhas[2]).getByText('Pouco histórico: 50% vendas próprias + 50% média de produtos da mesma categoria')).toBeInTheDocument()
    expect(within(linhas[3]).getByText('Sem previsão')).toBeInTheDocument()
    expect(within(linhas[3]).getByText('sem dado')).toBeInTheDocument()
    expect(within(linhas[3]).getByText(/^Sem previsão: ainda não há vendas/)).toBeInTheDocument()
    expect(within(linhas[4]).getByText('Evento: Feriado')).toBeInTheDocument()
    expect(within(linhas[4]).getByText('16,5 un')).toBeInTheDocument()
  })

  it('"Ver a conta" abre a conta passo a passo da linha, e fecha de novo', async () => {
    api()
    renderizarApp('/previsao')
    await screen.findByRole('table')
    const botao = screen.getByRole('button', { name: 'Ver a conta de Pão Francês na loja 001' })
    expect(botao).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(botao)
    expect(botao).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Conta: 40 kg × 1,1 = 44 kg.')).toBeInTheDocument()
    expect(screen.getByText(/com vendas até 13\/10\/2026 · método 2026\.10-v2/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Esconder a conta de Pão Francês na loja 001' }))
    expect(screen.queryByText('Conta: 40 kg × 1,1 = 44 kg.')).not.toBeInTheDocument()
  })

  it('qualidade: erro médio, sobra/falta e aviso quando não vence a semana passada, por unidade', async () => {
    api()
    renderizarApp('/previsao')
    const card = await screen.findByRole('region', { name: 'Qualidade da previsão' })
    expect(await within(card).findByText('Errou em média 9,6% do volume')).toBeInTheDocument()
    expect(within(card).getByText('Tende a sobrar 0,5%')).toBeInTheDocument()
    expect(within(card).getByText(/Melhor que repetir a venda da semana passada \(que errou 10,2%\)/)).toBeInTheDocument()
    expect(within(card).getByText('Errou em média 10,3% do volume')).toBeInTheDocument()
    expect(within(card).getByText('Tende a faltar 3%')).toBeInTheDocument()
    expect(within(card).getByText(/Repetir a venda da semana passada teria errado menos \(9,5%\)/)).toBeInTheDocument()
    expect(within(card).getByText(/Teste de 16\/09\/2026 a 13\/10\/2026/)).toBeInTheDocument()
  })

  it('a qualidade não é recalculada ao trocar o dia', async () => {
    const fetchSimulado = api()
    renderizarApp('/previsao')
    await screen.findByText('Errou em média 9,6% do volume')
    const input = screen.getByLabelText('Dia previsto')
    await userEvent.clear(input)
    await userEvent.type(input, hoje)
    await waitFor(() => expect(chamadas(fetchSimulado, '/previsoes').some((p) => p.get('data') === hoje)).toBe(true))
    expect(chamadas(fetchSimulado, '/previsoes/qualidade')).toHaveLength(1)
  })

  it('uma única ação principal: "Atualizar previsão" quando já existe previsão', async () => {
    api()
    renderizarApp('/previsao')
    await screen.findByRole('table')
    const primarios = within(screen.getByRole('main'))
      .getAllByRole('button')
      .filter((b) => b.className.includes('bg-primary'))
    expect(primarios.map((b) => b.textContent)).toEqual(['Atualizar previsão'])
  })

  it('sem previsão para o dia: estado vazio com "Gerar previsão"; gerar mostra o aviso e recarrega', async () => {
    let gerou = false
    const fetchSimulado = api({
      'GET /previsoes': (_init, url) => {
        const data = url.searchParams.get('data') ?? amanha
        return resposta(200, gerou ? previsoes(data) : { data, itens: [], totais: [] })
      },
      'POST /previsoes/gerar': () => {
        gerou = true
        return resposta(200, {
          data_referencia: somarDias(hoje, -1),
          data_inicio: hoje,
          data_fim: somarDias(hoje, 6),
          gravadas: 154,
          sem_previsao: 3,
          substituidas: 0,
          versao_metodo: '2026.10-v2',
        })
      },
    })
    renderizarApp('/previsao')
    expect(await screen.findByText(/^Nenhuma previsão gerada para/)).toBeInTheDocument()
    const primarios = within(screen.getByRole('main'))
      .getAllByRole('button')
      .filter((b) => b.className.includes('bg-primary'))
    expect(primarios.map((b) => b.textContent)).toEqual(['Gerar previsão'])

    await userEvent.click(screen.getByRole('button', { name: 'Gerar previsão' }))
    expect(await screen.findByText(/^Previsão pronta de .*: 154 itens, 3 sem previsão\.$/)).toBeInTheDocument()
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Atualizar previsão' })).toBeInTheDocument()
    expect(chamadas(fetchSimulado, '/previsoes/gerar', 'POST')).toHaveLength(1)
  })

  it('erro ao gerar: mensagem em português, sem código, que fica na tela', async () => {
    api({
      'GET /previsoes': (_init, url) => resposta(200, { data: url.searchParams.get('data'), itens: [], totais: [] }),
      'POST /previsoes/gerar': resposta(500, 'erro'),
    })
    renderizarApp('/previsao')
    await screen.findByText(/^Nenhuma previsão gerada para/)
    await userEvent.click(screen.getByRole('button', { name: 'Gerar previsão' }))
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('A previsão não foi gerada. O servidor não respondeu como esperado.')
    expect(document.body.textContent).not.toMatch(/\b500\b/)
  })

  it('dia além dos próximos 7: explica até quando a previsão vai', async () => {
    api({ 'GET /previsoes': (_init, url) => resposta(200, { data: url.searchParams.get('data'), itens: [], totais: [] }) })
    renderizarApp(`/previsao?data=${somarDias(hoje, 10)}`)
    expect(await screen.findByText('A previsão cobre só os próximos 7 dias.')).toBeInTheDocument()
    expect(screen.getByLabelText('Dia previsto')).toHaveAttribute('max', somarDias(hoje, 6))
  })

  it('filtro de loja vai para a URL e para a API, e a coluna Loja some', async () => {
    const fetchSimulado = api()
    renderizarApp('/previsao')
    await screen.findByRole('table')
    expect(screen.getByRole('columnheader', { name: 'Loja' })).toBeInTheDocument()
    const usuario = userEvent.setup()
    await usuario.click(screen.getByRole('combobox', { name: 'Loja' }))
    await usuario.click(await screen.findByRole('option', { name: '002 · Loja Bairro' }))
    await waitFor(() => expect(chamadas(fetchSimulado, '/previsoes').some((p) => p.get('loja_id') === '8')).toBe(true))
    await waitFor(() => expect(chamadas(fetchSimulado, '/previsoes/qualidade').some((p) => p.get('loja_id') === '8')).toBe(true))
    await waitFor(() => expect(screen.queryByRole('columnheader', { name: 'Loja' })).not.toBeInTheDocument())
  })

  it('filtros na URL: abrir com data e loja já consulta isso', async () => {
    const fetchSimulado = api()
    renderizarApp(`/previsao?data=${hoje}&loja=1`)
    await screen.findByRole('table')
    expect(screen.getByLabelText('Dia previsto')).toHaveValue(hoje)
    const p = chamadas(fetchSimulado, '/previsoes')[0]
    expect(p.get('data')).toBe(hoje)
    expect(p.get('loja_id')).toBe('1')
  })

  it('erro na consulta (loja fora do escopo): mensagem da API', async () => {
    api({ 'GET /previsoes': resposta(404, { detail: 'Loja não encontrada.' }) })
    renderizarApp('/previsao?loja=99')
    expect(await screen.findByText('Loja não encontrada.')).toBeInTheDocument()
  })
})
