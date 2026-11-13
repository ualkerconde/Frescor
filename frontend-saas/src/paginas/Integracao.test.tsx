import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { ExecucaoSyncVendas, IntegracaoVendas, PendenciaSyncVendas } from '@/lib/api/tipos'
import { dataIso, somarDias } from '@/lib/formato'
import { LISTA } from '@/test/cadastros'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

/* Integração de vendas (D107, D108): estado, "Buscar agora", execuções e pendências. */

async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } })
  return resultado.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

const HOJE = dataIso(new Date())

function execucao(extra: Partial<ExecucaoSyncVendas> = {}): ExecucaoSyncVendas {
  return {
    id: 9, origem: 'agendada', situacao: 'sucesso', data_inicio: '2026-11-07', data_fim: '2026-11-10',
    iniciada_em: '2026-11-11T06:00:00', terminada_em: '2026-11-11T06:00:04', linhas_recebidas: 1200,
    linhas_gravadas: 1180, linhas_pendentes: 20, linhas_invalidas: 0, mensagem: null, ...extra,
  }
}

const PENDENCIA_PRODUTO: PendenciaSyncVendas = {
  motivo: 'produto_desconhecido', codigo: '7890001', linhas: 20, primeira_data: '2026-11-07',
  ultima_data: '2026-11-10', lojas: ['001', '002'],
}
const PENDENCIA_LOJA: PendenciaSyncVendas = {
  motivo: 'loja_desconhecida', codigo: '099', linhas: 4, primeira_data: '2026-11-10', ultima_data: '2026-11-10',
  lojas: ['099'],
}

function integracao(extra: Partial<IntegracaoVendas> = {}): IntegracaoVendas {
  return {
    configurada: true, modo: 'busca', ativa: true, sistema: 'Sistema X', horario_busca: '03:00:00', dias_rebusca: 3,
    chave_prefixo: null, execucoes: [execucao()], pendencias: [PENDENCIA_PRODUTO, PENDENCIA_LOJA], ...extra,
  }
}

type Fetch = ReturnType<typeof simularApi>
const chamadas = (fetch: Fetch, metodo: string, trecho: string) =>
  fetch.mock.calls.filter(([url, init]) => String(url).includes(trecho) && (init?.method ?? 'GET') === metodo)
const corpo = (fetch: Fetch, metodo: string, trecho: string) =>
  JSON.parse(String(chamadas(fetch, metodo, trecho)[0][1]?.body))

function api(estado: IntegracaoVendas, extras: Parameters<typeof simularApi>[0] = {}) {
  return simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /web/produtos': resposta(200, LISTA),
    'GET /web/integracao/vendas': () => resposta(200, estado),
    ...extras,
  })
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

describe('integração de vendas (D108)', () => {
  it('modo busca: como a venda chega, última execução, pendências e execuções; sem violações de acessibilidade', async () => {
    api(integracao())
    renderizarApp('/integracao')
    expect(await screen.findByText(/O Frescor busca todo dia às 03:00 a venda de ontem e confere de novo 3 dias anteriores/)).toBeInTheDocument()
    expect(screen.getByText('Sistema X')).toBeInTheDocument()
    expect(screen.getByText('Ligada')).toBeInTheDocument()

    const pendencias = screen.getByRole('table', { name: 'Códigos sem cadastro' })
    const [, produto, loja] = within(pendencias).getAllByRole('row')
    expect(produto).toHaveTextContent('7890001Produto sem cadastro2007/11/2026 a 10/11/2026001, 002')
    expect(within(produto).getByRole('button', { name: 'Ligar o código 7890001 a um produto' })).toBeInTheDocument()
    expect(loja).toHaveTextContent('Loja sem cadastro')
    expect(within(loja).queryByRole('button')).not.toBeInTheDocument()

    const execucoes = screen.getByRole('table', { name: 'Últimas execuções da integração' })
    expect(within(execucoes).getAllByRole('row')[1]).toHaveTextContent('Busca automática07/11/2026 a 10/11/2026Tudo certo1.180de 1.200200')

    const principais = screen.getAllByRole('button').filter((b) => b.dataset.variant === 'default')
    expect(principais.map((b) => b.textContent)).toEqual(['Buscar agora'])
    expect(screen.getByRole('link', { name: 'Carga de histórico (CSV)' })).toHaveAttribute('href', '/importar')
    expect(await violacoes()).toEqual([])
  })

  it('sem configuração: avisa e aponta para a carga de histórico; sem "Buscar agora"', async () => {
    api({ ...integracao(), configurada: false, modo: null, ativa: null, sistema: null, horario_busca: null,
      dias_rebusca: null, execucoes: [], pendencias: [] })
    renderizarApp('/integracao')
    expect(await screen.findByText('A integração com o sistema de vendas ainda não foi ligada.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Buscar agora' })).not.toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Últimas execuções da integração' })).not.toBeInTheDocument()
    expect(screen.getByText(/Nenhuma venda pendente/)).toBeInTheDocument()
  })

  it('modo envio: mostra o começo da chave e não oferece "Buscar agora"', async () => {
    api(integracao({ modo: 'envio', horario_busca: null, dias_rebusca: null, chave_prefixo: 'frv_ab12',
      execucoes: [execucao({ origem: 'envio' })] }))
    renderizarApp('/integracao')
    expect(await screen.findByText(/O sistema do cliente envia a venda para o Frescor, com a chave que começa por frv_ab12/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Buscar agora' })).not.toBeInTheDocument()
    expect(screen.getByText('Envio do sistema')).toBeInTheDocument()
  })

  it('última busca falhou: alerta com a mensagem do erro', async () => {
    api(integracao({ execucoes: [execucao({ situacao: 'falhou', mensagem: 'O sistema respondeu 500.', linhas_gravadas: 0 }), execucao({ id: 8 })] }))
    renderizarApp('/integracao')
    expect(await screen.findByText(/A última busca falhou/)).toBeInTheDocument()
    expect(screen.getAllByText(/O sistema respondeu 500\./).length).toBeGreaterThan(0)
  })

  it('pausada: avisa e "Buscar agora" fica desabilitado', async () => {
    api(integracao({ ativa: false }))
    renderizarApp('/integracao')
    expect(await screen.findByText('A integração está pausada: nenhuma venda nova entra.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Buscar agora' })).toBeDisabled()
  })

  it('"Buscar agora": período padrão (ontem e os 3 dias de rebusca), validação e envio', async () => {
    const fetch = api(integracao(), {
      'POST /web/integracao/vendas/buscar': resposta(200, execucao({ id: 10, origem: 'manual', linhas_gravadas: 300, linhas_pendentes: 0 })),
    })
    renderizarApp('/integracao')
    await userEvent.click(await screen.findByRole('button', { name: 'Buscar agora' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Buscar vendas agora' })
    const ontem = somarDias(HOJE, -1)
    expect(within(dialogo).getByLabelText('Primeiro dia')).toHaveValue(somarDias(ontem, -3))
    expect(within(dialogo).getByLabelText('Último dia')).toHaveValue(ontem)

    const primeiro = within(dialogo).getByLabelText('Primeiro dia')
    await userEvent.clear(primeiro)
    await userEvent.type(primeiro, somarDias(ontem, -40))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Buscar' }))
    expect(within(dialogo).getByText('Busque até 31 dias de cada vez.')).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/buscar')).toHaveLength(0)

    await userEvent.clear(primeiro)
    await userEvent.type(primeiro, somarDias(ontem, -3))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Buscar' }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/buscar')).toHaveLength(1))
    expect(corpo(fetch, 'POST', '/buscar')).toEqual({ data_inicio: somarDias(ontem, -3), data_fim: ontem })
    expect(await screen.findByText('Busca feita: 300 linhas gravadas.')).toBeInTheDocument()
  })

  it('ligar um código a um produto: escolhe o produto e envia o código', async () => {
    const fetch = api(integracao(), {
      'POST /web/integracao/vendas/pendencias/casar': resposta(200, { gravadas: 20, pendentes: 0, invalidas: [] }),
    })
    renderizarApp('/integracao')
    await userEvent.click(await screen.findByRole('button', { name: 'Ligar o código 7890001 a um produto' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Ligar o código 7890001 a um produto' })
    expect(dialogo).toHaveTextContent('20 linhas de venda de 07/11/2026 a 10/11/2026 (lojas 001, 002)')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Ligar ao produto' }))
    expect(within(dialogo).getByText('Escolha o produto.')).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/casar')).toHaveLength(0)

    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Produto do Frescor' }))
    await userEvent.click(await screen.findByRole('option', { name: 'INT-007 · Pão Francês' }))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Ligar ao produto' }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/casar')).toHaveLength(1))
    expect(corpo(fetch, 'POST', '/casar')).toEqual({ codigo_produto: '7890001', produto_id: 17 })
    expect(await screen.findByText(/Código 7890001 ligado a INT-007 · Pão Francês: 20 linhas de venda gravadas/)).toBeInTheDocument()
  })

  it('erro do backend ao ligar (código já de outro produto) aparece no diálogo', async () => {
    api(integracao(), {
      'POST /web/integracao/vendas/pendencias/casar': resposta(422, { detail: 'O código 7890001 já é do produto Bolo.' }),
    })
    renderizarApp('/integracao')
    await userEvent.click(await screen.findByRole('button', { name: 'Ligar o código 7890001 a um produto' }))
    const dialogo = await screen.findByRole('dialog')
    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Produto do Frescor' }))
    await userEvent.click(await screen.findByRole('option', { name: 'INT-007 · Pão Francês' }))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Ligar ao produto' }))
    expect(await within(dialogo).findByText(/O código não foi ligado\. O código 7890001 já é do produto Bolo\./)).toBeInTheDocument()
  })
})
