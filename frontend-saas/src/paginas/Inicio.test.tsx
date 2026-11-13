import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

/* Visão geral no visual Comando (D117, 13/11/2026): só lê endpoints que já existem. */

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

function item(id: number, produtoId: number, nome: string, unidade: 'UN' | 'KG', final: string) {
  return {
    id,
    produto: { id: produtoId, codigo: null, nome },
    tipo_abastecimento: 'produzido',
    unidade,
    total_sugerido: final,
    total_final: final,
    linhas: [],
  }
}

const ORDEM_DETALHE = {
  ...ORDEM,
  itens: [
    item(1, 10, 'Pão Francês', 'UN', '1000.0000'),
    item(2, 11, 'Sonho', 'UN', '240.0000'),
    item(3, 12, 'Pão de Queijo', 'KG', '18.5000'),
  ],
}

const PRODUTOS = {
  total: 3,
  limit: 200,
  offset: 0,
  itens: [
    { id: 10, codigo: null, nome: 'Pão Francês', unidade: 'UN', ativo: true, setor: 'Pães' },
    { id: 11, codigo: null, nome: 'Sonho', unidade: 'UN', ativo: true, setor: 'Doces' },
    { id: 12, codigo: null, nome: 'Pão de Queijo', unidade: 'KG', ativo: true, setor: 'Pães' },
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

const VAZIO = { previsto: null, sugerido: null, final: null, produzido: null, enviado: null, vendido: null, perda: null, sem_registro: null }

function acompanhamento(wape: string | null, vies: string | null = null) {
  const dias = ['2026-11-04', '2026-11-05', '2026-11-06', '2026-11-07', '2026-11-08', '2026-11-09', '2026-11-10'].map(
    (data, i) => ({ ...VAZIO, data, previsto: String(150 + i), vendido: String(140 + i), perda: String(4 + (i % 3)) }),
  )
  return {
    data_inicio: '2026-11-04',
    data_fim: '2026-11-10',
    produzido_disponivel: true,
    unidades: [
      {
        unidade: 'UN',
        totais: { ...VAZIO, previsto: '1050', vendido: '1000', perda: '38' },
        erro: { wape, vies, celulas: 20 },
        dias,
        balancos: 40,
        rupturas: 3,
      },
    ],
    produtos: [
      { produto: { id: 1, codigo: null, nome: 'Baguete' }, unidade: 'UN', totais: VAZIO, erro: { wape: null, vies: null, celulas: 0 }, sobra: null, balancos: 10, rupturas: 2 },
      { produto: { id: 2, codigo: null, nome: 'Sonho' }, unidade: 'UN', totais: VAZIO, erro: { wape: null, vies: null, celulas: 0 }, sobra: null, balancos: 10, rupturas: 1 },
    ],
  }
}

const LOJAS = [
  { id: 1, codigo: '001', nome: 'Centro', ativo: true },
  { id: 2, codigo: '002', nome: 'Bairro', ativo: true },
  { id: 3, codigo: '003', nome: 'Fechada', ativo: false },
]

function consulta(totais: { unidade: string; quantidade: string }[]) {
  return { total: totais.length, limit: 1, offset: 0, itens: [], totais }
}

function rotasCompletas(extra: Record<string, Response | ((init: RequestInit, url: URL) => Response)> = {}) {
  return {
    'GET /web/me': resposta(200, ME),
    'GET /producao/ordens': resposta(200, { data_producao: '2026-11-12', ordens: [ORDEM] }),
    'GET /producao/ordens/7': resposta(200, ORDEM_DETALHE),
    'GET /web/produtos': resposta(200, PRODUTOS),
    'GET /web/lojas': resposta(200, LOJAS),
    // Central inteira: acerto 92% (WAPE 8%); loja 1: 94%; loja 2: sem previsão com venda.
    'GET /web/acompanhamento': (_init: RequestInit, url: URL) => {
      const loja = url.searchParams.get('loja_id')
      return resposta(200, loja === null ? acompanhamento('0.08', '0.05') : acompanhamento(loja === '1' ? '0.06' : null))
    },
    'GET /distribuicao/romaneios': resposta(200, ROMANEIOS),
    'GET /vendas': resposta(200, consulta([{ unidade: 'UN', quantidade: '1000.0000' }])),
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

describe('visão geral (visual Comando)', () => {
  it('manchete: saudação, data · central e o que a central produz amanhã por unidade (sem somar UN e KG)', async () => {
    const api = simularApi(rotasCompletas())
    renderizarApp('/inicio')
    expect(await screen.findByRole('heading', { level: 1, name: 'Bom dia, Gestor' })).toBeInTheDocument()
    expect(await screen.findByText('quarta-feira, 11 de novembro de 2026 · Central Principal')).toBeInTheDocument()
    const manchete = await screen.findByText(/Amanhã a central produz/)
    expect(manchete).toHaveTextContent('Amanhã a central produz 1.240 un e 18,5 kg.')
    expect(screen.getByText('Ordem em rascunho')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisar ordem de quinta' })).toHaveAttribute('href', '/producao?data=2026-11-12')
    const urls = api.mock.calls.map((c) => String(c[0]))
    expect(urls).toContain('/backend/producao/ordens?data=2026-11-12')
    expect(urls).toContain('/backend/web/acompanhamento?data_inicio=2026-11-04&data_fim=2026-11-10')
  })

  it('sem ordem para amanhã: a manchete diz, a pill diz e "Precisa de você" leva a gerar', async () => {
    simularApi(rotasCompletas({ 'GET /producao/ordens': resposta(200, { data_producao: '2026-11-12', ordens: [] }) }))
    renderizarApp('/inicio')
    expect(await screen.findByText('A ordem de amanhã ainda não foi gerada.')).toBeInTheDocument()
    expect(screen.getByText('Ordem não gerada')).toBeInTheDocument()
    const pendencias = screen.getByRole('region', { name: 'Precisa de você' })
    expect(within(pendencias).getByRole('link', { name: 'Gerar a ordem de quinta, 12/11' })).toHaveAttribute(
      'href',
      '/producao?data=2026-11-12',
    )
  })

  it('cartões: acerto (1 − WAPE) com o viés, perda sobre o vendido e ruptura com os produtos', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const acerto = await screen.findByRole('region', { name: 'Acerto da previsão' })
    expect(await within(acerto).findByText('92%')).toBeInTheDocument()
    expect(within(acerto).getByText(/previu 5% a mais/)).toBeInTheDocument()
    const perda = screen.getByRole('region', { name: 'Perda' })
    expect(within(perda).getByText('3,8%')).toBeInTheDocument()
    expect(within(perda).getByText('38 un perdidos em 7 dias')).toBeInTheDocument()
    const ruptura = screen.getByRole('region', { name: 'Ruptura' })
    expect(within(ruptura).getByText('3')).toBeInTheDocument()
    expect(within(ruptura).getByText('Baguete')).toBeInTheDocument()
    expect(within(ruptura).getByText('Sonho')).toBeInTheDocument()
  })

  it('entregas de hoje: recebidas sobre o total, com a legenda das situações (cor nunca sozinha)', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const cartao = await screen.findByRole('region', { name: 'Entregas de hoje' })
    expect(await within(cartao).findByText(/lojas receberam/)).toBeInTheDocument()
    expect(within(cartao).getByText(/lojas receberam/).parentElement).toHaveTextContent('2/3 lojas receberam')
    expect(within(cartao).getByText(/Recebidas/)).toBeInTheDocument()
    expect(within(cartao).getByText(/A caminho/)).toBeInTheDocument()
  })

  it('produção de amanhã por setor: agrupa pelo setor do cadastro e não soma UN com KG', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const bloco = await screen.findByRole('region', { name: 'Produção de quinta por setor' })
    const linhas = await within(bloco).findAllByRole('listitem')
    expect(linhas).toHaveLength(2)
    expect(linhas[0]).toHaveTextContent('Pães')
    expect(linhas[0]).toHaveTextContent('1.000 un · 18,5 kg')
    expect(linhas[1]).toHaveTextContent('Doces')
    expect(linhas[1]).toHaveTextContent('240 un')
  })

  it('acerto por loja: uma consulta por loja ativa, com "sem dado" quando não há previsão com venda', async () => {
    const api = simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const bloco = await screen.findByRole('region', { name: 'Acerto por loja' })
    expect(await within(bloco).findByText('94%')).toBeInTheDocument()
    expect(await within(bloco).findByText('sem dado')).toBeInTheDocument()
    expect(within(bloco).queryByText(/Fechada/)).not.toBeInTheDocument()
    const urls = api.mock.calls.map((c) => String(c[0]))
    expect(urls).toContain('/backend/web/acompanhamento?data_inicio=2026-11-04&data_fim=2026-11-10&loja_id=1')
    expect(urls.some((u) => u.includes('loja_id=3'))).toBe(false)
  })

  it('precisa de você: só pendências reais (ordem em rascunho, divergências e rupturas)', async () => {
    simularApi(rotasCompletas())
    renderizarApp('/inicio')
    const bloco = await screen.findByRole('region', { name: 'Precisa de você' })
    expect(await within(bloco).findByText('3 itens')).toBeInTheDocument()
    expect(within(bloco).getByRole('link', { name: 'Aprovar a ordem de quinta, 12/11' })).toBeInTheDocument()
    expect(within(bloco).getByText('Está em rascunho, com 1 linha sem sugestão.')).toBeInTheDocument()
    expect(within(bloco).getByRole('link', { name: '2 divergências de recebimento' })).toHaveAttribute('href', '/distribuicao')
    expect(within(bloco).getByRole('link', { name: 'Produto acabou na loja 3 vezes' })).toHaveAttribute('href', '/acompanhamento')
  })

  it('com ordem emergencial no dia, a manchete usa a programada e a pill conta a emergencial', async () => {
    const emergencial = { ...ORDEM, id: 8, tipo: 'emergencial', status: 'aprovada', totais: [{ unidade: 'UN', sugerido: '50', final: '50' }] }
    simularApi(
      rotasCompletas({ 'GET /producao/ordens': resposta(200, { data_producao: '2026-11-12', ordens: [ORDEM, emergencial] }) }),
    )
    renderizarApp('/inicio')
    expect(await screen.findByText(/Amanhã a central produz/)).toHaveTextContent('1.240 un e 18,5 kg')
    expect(screen.getByText(/Ordem em rascunho · mais 1 emergencial/)).toBeInTheDocument()
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
    await screen.findByText(/Amanhã a central produz/)
    await screen.findByText('94%')
    await screen.findByText('38 un perdidos em 7 dias')
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
    expect(await screen.findByText(/Amanhã a central produz/)).toBeInTheDocument()
    expect(await screen.findByText('92%')).toBeInTheDocument()
  })
})
