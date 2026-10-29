import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { Evento } from '@/lib/api/tipos'
import { dataIso } from '@/lib/formato'
import { LISTA } from '@/test/cadastros'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

const LOJAS = [
  { id: 1, codigo: '001', nome: 'Loja Centro', ativo: true },
  { id: 2, codigo: '002', nome: 'Loja Bairro', ativo: true },
  { id: 3, codigo: '003', nome: 'Loja Antiga', ativo: false },
]

function evento(extra: Partial<Evento> = {}): Evento {
  return {
    id: 5, nome: 'Natal', data_inicio: '2026-12-24', data_fim: '2026-12-25', tipo_ajuste: 'multiplicador',
    valor_ajuste: '1.8000', escopo_loja: 'todas', loja_ids: [], escopo_produto: 'todos', produto_ids: [],
    pode_apagar: true, ...extra,
  }
}

type Fetch = ReturnType<typeof simularApi>
const chamadas = (fetch: Fetch, metodo: string, trecho: string) =>
  fetch.mock.calls.filter(([url, init]) => String(url).includes(trecho) && (init?.method ?? 'GET') === metodo)

function api(eventos: Evento[], extras: Parameters<typeof simularApi>[0] = {}) {
  let lista = [...eventos]
  return simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /web/lojas': resposta(200, LOJAS),
    'GET /web/produtos': resposta(200, LISTA),
    'GET /eventos': () => resposta(200, lista),
    'POST /eventos': (init) => {
      const c = JSON.parse(String(init.body))
      const novo = evento({ id: 9, ...c, loja_ids: c.loja_ids ?? [], produto_ids: c.produto_ids ?? [],
        escopo_produto: c.produto_ids ? 'especificos' : 'todos' })
      lista = [...lista, novo]
      return resposta(201, novo)
    },
    'DELETE /eventos/5': () => {
      lista = lista.filter((e) => e.id !== 5)
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

describe('cadastros: eventos (C5)', () => {
  it('lista de hoje em diante, com o ajuste em palavras, lojas e produtos pelo nome', async () => {
    const fetch = api([
      evento(),
      evento({ id: 6, nome: 'Feriado', data_inicio: '2026-11-20', data_fim: '2026-11-20', tipo_ajuste: 'valor_fixo',
        valor_ajuste: '0.0000', escopo_loja: 'especificas', loja_ids: [2], escopo_produto: 'especificos', produto_ids: [17],
        pode_apagar: false }),
    ])
    renderizarApp('/cadastros/eventos')
    const tabela = await screen.findByRole('table', { name: 'Eventos' })
    const [, natal, feriado] = within(tabela).getAllByRole('row')
    expect(natal).toHaveTextContent('Natal24/12/2026 a 25/12/2026Previsão × 1,8 (80% a mais)Todas as lojas da centralTodos os produtos')
    await waitFor(() => expect(feriado).toHaveTextContent('Previsão fixa em 0 por loja e produto002 · Loja BairroINT-007 · Pão Francês'))
    // Evento que vale para outra central: sem "Apagar" (a API responderia 403 e a sessão cairia).
    expect(within(feriado).queryByRole('button', { name: /Apagar/ })).not.toBeInTheDocument()
    expect(feriado).toHaveTextContent('Vale também para outra central')
    expect(String(chamadas(fetch, 'GET', '/eventos')[0][0])).toContain(`data_inicio=${dataIso(new Date())}`)
  })

  it('sem eventos: estado vazio; apagar a data mostra também os passados', async () => {
    const fetch = api([])
    renderizarApp('/cadastros/eventos')
    expect(await screen.findByText(/^Nenhum evento a partir de/)).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Eventos a partir de'))
    expect(await screen.findByText('Nenhum evento cadastrado.')).toBeInTheDocument()
    expect(String(chamadas(fetch, 'GET', '/eventos').at(-1)?.[0])).not.toContain('data_inicio')
  })

  it('novo evento: valida no navegador e envia lojas e produtos escolhidos', async () => {
    const fetch = api([])
    renderizarApp('/cadastros/eventos')
    await userEvent.click(await screen.findByRole('button', { name: 'Novo evento' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Novo evento' })
    await userEvent.click(within(dialogo).getByRole('checkbox', { name: /Todas as lojas da central/ }))
    await userEvent.click(within(dialogo).getByRole('checkbox', { name: 'Todos os produtos' }))
    // A loja inativa não aparece para escolha.
    expect(within(dialogo).queryByRole('checkbox', { name: /Loja Antiga/ })).not.toBeInTheDocument()
    await userEvent.type(within(dialogo).getByLabelText('Multiplicar por'), '1,23456')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Cadastrar evento' }))
    expect(within(dialogo).getByText('Informe o nome do evento.')).toBeInTheDocument()
    expect(within(dialogo).getByText('Informe no máximo 4 casas decimais.')).toBeInTheDocument()
    expect(within(dialogo).getByText('Escolha pelo menos uma loja.')).toBeInTheDocument()
    expect(within(dialogo).getByText('Escolha pelo menos um produto.')).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/eventos')).toHaveLength(0)

    await userEvent.type(within(dialogo).getByLabelText('Nome do evento'), 'Festa do bairro')
    await userEvent.type(within(dialogo).getByLabelText('Primeiro dia'), '2026-11-14')
    await userEvent.type(within(dialogo).getByLabelText('Último dia'), '2026-11-15')
    await userEvent.click(within(dialogo).getByRole('radio', { name: /Fixar um valor/ }))
    const valor = within(dialogo).getByLabelText('Valor por loja e produto')
    await userEvent.clear(valor)
    await userEvent.type(valor, '30')
    await userEvent.click(within(dialogo).getByRole('checkbox', { name: '002 · Loja Bairro' }))
    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Adicionar produto' }))
    await userEvent.click(await screen.findByRole('option', { name: 'INT-007 · Pão Francês' }))
    expect(within(dialogo).getByRole('list', { name: 'Produtos do evento' })).toHaveTextContent('INT-007 · Pão Francês')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Cadastrar evento' }))

    await waitFor(() => expect(chamadas(fetch, 'POST', '/eventos')).toHaveLength(1))
    expect(JSON.parse(String(chamadas(fetch, 'POST', '/eventos')[0][1]?.body))).toEqual({
      nome: 'Festa do bairro', data_inicio: '2026-11-14', data_fim: '2026-11-15', tipo_ajuste: 'valor_fixo',
      valor_ajuste: '30', escopo_loja: 'especificas', loja_ids: [2], produto_ids: [17],
    })
    expect(await screen.findByText(/Evento “Festa do bairro” cadastrado/)).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: 'Festa do bairro' })).toBeInTheDocument()
  })

  it('todas as lojas e todos os produtos vão sem lista; erro da API fica no diálogo', async () => {
    const fetch = api([], { 'POST /eventos': resposta(422, { detail: 'O período do evento pode ter no máximo 366 dias.' }) })
    renderizarApp('/cadastros/eventos')
    await userEvent.click(await screen.findByRole('button', { name: 'Novo evento' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Novo evento' })
    await userEvent.type(within(dialogo).getByLabelText('Nome do evento'), 'Longo')
    await userEvent.type(within(dialogo).getByLabelText('Primeiro dia'), '2026-01-01')
    await userEvent.type(within(dialogo).getByLabelText('Último dia'), '2027-12-31')
    await userEvent.type(within(dialogo).getByLabelText('Multiplicar por'), '2')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Cadastrar evento' }))
    expect(await within(dialogo).findByText('O evento não foi cadastrado. O período do evento pode ter no máximo 366 dias.')).toBeInTheDocument()
    expect(JSON.parse(String(chamadas(fetch, 'POST', '/eventos')[0][1]?.body))).toMatchObject({
      tipo_ajuste: 'multiplicador', valor_ajuste: '2', escopo_loja: 'todas', loja_ids: null, produto_ids: null,
    })
  })

  it('apagar pede confirmação e some da lista', async () => {
    const fetch = api([evento()])
    renderizarApp('/cadastros/eventos')
    await userEvent.click(await screen.findByRole('button', { name: 'Apagar: Natal' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Apagar o evento “Natal”?' })
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Apagar evento' }))
    await waitFor(() => expect(chamadas(fetch, 'DELETE', '/eventos/5')).toHaveLength(1))
    expect(await screen.findByText(/^Nenhum evento a partir de/)).toBeInTheDocument()
  })
})
