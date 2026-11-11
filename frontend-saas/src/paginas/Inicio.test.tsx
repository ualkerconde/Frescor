import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

/* Visão geral (padrão de 11/11/2026): só lê endpoints que já existem. */

/** axe-core sem contraste (o jsdom não renderiza cor; o contraste fica no tema.test.ts). */
async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } })
  return resultado.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

const ORDEM = {
  id: 7,
  data_producao: '2026-11-12',
  data_entrega: '2026-11-12',
  tipo: 'programada',
  status: 'rascunho',
  versao_metodo: 'n2',
  referencia_previsao: null,
  gerado_em: '2026-11-11T10:00:00',
  gerado_por: 'Gestor',
  aprovado_em: null,
  aprovado_por: null,
  linhas: 24,
  linhas_editadas: 3,
  linhas_sem_quantidade: 1,
  totais: [
    { unidade: 'UN', sugerido: '1300.0000', final: '1240.0000' },
    { unidade: 'KG', sugerido: '20.0000', final: '18.5000' },
  ],
}

const ROMANEIOS = {
  data_entrega: '2026-11-11',
  ordens: [
    {
      ordem_id: 6,
      data_producao: '2026-11-11',
      data_entrega: '2026-11-11',
      status_ordem: 'aprovada',
      itens: [],
      romaneio: { id: 3, status: 'aprovado', entregas: 3, situacoes: { recebida: 2, a_caminho: 1 } },
    },
  ],
}

function consulta(totais: { unidade: string; quantidade: string }[]) {
  return { total: totais.length, limit: 1, offset: 0, itens: [], totais }
}

function rotasCompletas(extra: Record<string, Response> = {}) {
  return {
    'GET /web/me': resposta(200, ME),
    'GET /producao/ordens': resposta(200, { data_producao: '2026-11-12', ordens: [ORDEM] }),
    'GET /distribuicao/romaneios': resposta(200, ROMANEIOS),
    'GET /vendas': resposta(200, consulta([{ unidade: 'UN', quantidade: '1000.0000' }])),
    'GET /perdas': resposta(200, consulta([{ unidade: 'UN', quantidade: '38.0000' }])),
    'GET /distribuicao/divergencias': resposta(200, {
      data_inicio: '2026-11-04',
      data_fim: '2026-11-11',
      divergencias: [{}, {}],
      totais: [],
    }),
    ...extra,
  }
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('A1', 'R1')
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 10, 11, 9, 30))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('visão geral', () => {
  it('saúda pelo primeiro nome com a data por extenso e resume o momento', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    expect(await screen.findByRole('heading', { level: 1, name: 'Bom dia, Gestor' })).toBeInTheDocument()
    expect(screen.getByText('quarta-feira, 11 de novembro de 2026')).toBeInTheDocument()
    expect(await screen.findByText('está em rascunho')).toBeInTheDocument()
    expect(await screen.findByText('2 divergências')).toBeInTheDocument()
  })

  it('painel da ordem de amanhã: status, totais por unidade (sem somar UN e KG) e as 3 contagens', async () => {
    const api = simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const painel = await screen.findByRole('region', { name: 'Ordem de produção de amanhã' })
    expect(await within(painel).findByText('Em rascunho')).toBeInTheDocument()
    const itens = within(painel).getAllByRole('listitem')
    expect(itens[0]).toHaveTextContent(/^1\.240 un$/)
    expect(itens[1]).toHaveTextContent(/^18,5 kg$/)
    // Sugerido x final, por unidade: 1.300 -> 1.240 un (-5%) e 20 -> 18,5 kg (-7%, arredondado como no resto da tela).
    expect(itens[2]).toHaveTextContent('1.300 un → 1.240 un (−5%)')
    expect(itens[3]).toHaveTextContent('20 kg → 18,5 kg (−7%)')
    expect(within(painel).getByText('24')).toBeInTheDocument()
    expect(within(painel).getByText('3')).toBeInTheDocument()
    expect(within(painel).getByText('1')).toBeInTheDocument()
    expect(within(painel).getByRole('link', { name: 'Abrir produção' })).toHaveAttribute('href', '/producao?data=2026-11-12')
    const urls = api.mock.calls.map((c) => String(c[0]))
    expect(urls).toContain('/backend/producao/ordens?data=2026-11-12')
    expect(urls).toContain('/backend/vendas?data_inicio=2026-11-04&data_fim=2026-11-10&limit=1&offset=0')
  })

  it('sem ordem para amanhã: "Ainda não gerada"', async () => {
    simularApi(rotasCompletas({ 'GET /producao/ordens': resposta(200, { data_producao: '2026-11-12', ordens: [] }) }))
    renderizarApp('/inicio')
    expect(await screen.findByText('Ainda não gerada')).toBeInTheDocument()
    expect(await screen.findByText('ainda não foi gerada')).toBeInTheDocument()
  })

  it('entregas de hoje com a legenda das situações (cor nunca sozinha)', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const cartao = await screen.findByRole('region', { name: 'Entregas de hoje' })
    expect(await within(cartao).findByText('3')).toBeInTheDocument()
    expect(within(cartao).getByText(/Recebidas/)).toBeInTheDocument()
    expect(within(cartao).getByText(/A caminho/)).toBeInTheDocument()
  })

  it('perda da semana com o percentual sobre o vendido na mesma unidade', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const cartao = await screen.findByRole('region', { name: 'Perda' })
    expect(await within(cartao).findByText('38 un')).toBeInTheDocument()
    expect(within(cartao).getByText('3,8%')).toBeInTheDocument()
  })

  it('perda ÷ venda só na mesma unidade: venda em kg não entra na conta da perda em un', async () => {
    simularApi(
      rotasCompletas({
        'GET /vendas': resposta(
          200,
          consulta([
            { unidade: 'KG', quantidade: '50.0000' },
            { unidade: 'UN', quantidade: '1000.0000' },
          ]),
        ),
      }),
    )
    renderizarApp('/inicio')
    const cartao = await screen.findByRole('region', { name: 'Perda' })
    expect(await within(cartao).findByText('3,8%')).toBeInTheDocument()
    expect(within(cartao).queryByText('76%')).not.toBeInTheDocument()
  })

  it('com ordem emergencial no dia, o painel mostra a programada e conta a emergencial', async () => {
    const emergencial = { ...ORDEM, id: 8, tipo: 'emergencial', status: 'aprovada', totais: [{ unidade: 'UN', sugerido: '50', final: '50' }] }
    simularApi(
      rotasCompletas({ 'GET /producao/ordens': resposta(200, { data_producao: '2026-11-12', ordens: [ORDEM, emergencial] }) }),
    )
    renderizarApp('/inicio')
    const painel = await screen.findByRole('region', { name: 'Ordem de produção de amanhã' })
    expect(await within(painel).findByText('Em rascunho')).toBeInTheDocument()
    expect(within(painel).getAllByRole('listitem')[0]).toHaveTextContent(/^1\.240 un$/)
    expect(within(painel).getByText(/mais 1 ordem emergencial/)).toBeInTheDocument()
  })

  it('sem vendas na semana: aviso com o caminho para a integração de vendas', async () => {
    simularApi(rotasCompletas({ 'GET /vendas': resposta(200, consulta([])) }))
    renderizarApp('/inicio')
    expect(await screen.findByText('Nenhuma venda chegou nos últimos 7 dias.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Veja a integração de vendas' })).toHaveAttribute('href', '/integracao')
  })

  it('acessibilidade (axe): visão geral carregada e a busca de telas aberta, sem violação', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    await screen.findAllByText('1.240 un')
    await screen.findByText('38 un')
    expect(await violacoes()).toEqual([])
    vi.useRealTimers()
    await userEvent.click(screen.getByRole('button', { name: /Buscar tela/ }))
    await screen.findByRole('dialog', { name: 'Buscar tela' })
    expect(await violacoes()).toEqual([])
  })

  it('um bloco com erro não derruba os outros', async () => {
    simularApi(rotasCompletas({ 'GET /distribuicao/romaneios': resposta(500, 'erro') }))
    renderizarApp('/inicio')
    expect(await screen.findByText('Não foi possível carregar as entregas.')).toBeInTheDocument()
    expect((await screen.findAllByText('1.240 un')).length).toBeGreaterThan(0)
  })
})
