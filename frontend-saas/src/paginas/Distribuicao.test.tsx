import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { OrdemDistribuicao, RomaneioDetalhe } from '@/lib/api/tipos'
import { dataIso } from '@/lib/formato'
import { entregas, itensProducao, ordemComRomaneio, ordemDoDia, romaneioDetalhe } from '@/test/distribuicao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

const hoje = dataIso(new Date())

/** API simulada: a lista do dia sai do estado (ordem e romaneio), que as ações mudam. */
function api(
  inicial: { ordem?: OrdemDistribuicao | null; romaneio?: RomaneioDetalhe | null } = {},
  extras: Record<string, Response | ((init: RequestInit, url: URL) => Response)> = {},
) {
  const romaneio = inicial.romaneio ?? null
  const estado = {
    // Com romaneio, a produção já foi registrada (o romaneio só é gerado assim, D69).
    ordem: inicial.ordem !== undefined ? inicial.ordem : romaneio ? ordemComRomaneio(romaneio) : ordemDoDia(hoje),
    romaneio,
  }
  const dia = () => {
    if (!estado.ordem) return []
    return [estado.romaneio ? { ...ordemComRomaneio(estado.romaneio), itens: estado.ordem.itens } : estado.ordem]
  }
  const fetch = simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /distribuicao/romaneios': () => resposta(200, { data_entrega: hoje, ordens: dia() }),
    'GET /distribuicao/romaneios/30': () =>
      estado.romaneio ? resposta(200, estado.romaneio) : resposta(404, { detail: 'Romaneio não encontrado.' }),
    'GET /distribuicao/divergencias': resposta(200, { data_inicio: hoje, data_fim: hoje, divergencias: [], totais: [] }),
    'POST /distribuicao/ordens/7/producao': () => {
      if (estado.ordem) estado.ordem = { ...estado.ordem, itens: itensProducao(['10.000', '4.500']) }
      return resposta(200, { itens_registrados: 2, romaneio_desatualizado: false })
    },
    'POST /distribuicao/romaneios/gerar': () => {
      estado.romaneio = romaneioDetalhe(hoje)
      return resposta(200, {
        romaneio_id: 30, ordem_id: 7, entregas: 2, itens: 4, produtos_com_escassez: [1], produtos_com_sobra: [],
        substituiu_rascunho: false,
      })
    },
    ...extras,
  })
  return { estado, fetch }
}

function chamadas(fetch: ReturnType<typeof simularApi>, metodo: string, trecho: string) {
  return fetch.mock.calls.filter(([url, init]) => String(url).includes(trecho) && (init?.method ?? 'GET') === metodo)
}

function corpo(fetch: ReturnType<typeof simularApi>, metodo: string, trecho: string, n = 0) {
  const init = chamadas(fetch, metodo, trecho)[n][1]
  return init?.body === undefined ? undefined : JSON.parse(String(init.body))
}

const aprovado = (extra: Partial<RomaneioDetalhe> = {}) =>
  romaneioDetalhe(hoje, { status: 'aprovado', aprovado_em: '2026-10-28T13:00:00', ...extra })

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

describe('tela de distribuição e romaneio (E10)', () => {
  it('menu leva à tela; sem ordem no dia: estado vazio com o caminho para a produção', async () => {
    api({ ordem: null })
    renderizarApp('/distribuicao')
    expect(await screen.findByText(/Nenhuma ordem de produção com entrega em/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir a ordem de produção' })).toHaveAttribute('href', '/producao')
    expect(screen.getByRole('link', { name: /Distribuição/ })).toHaveAttribute('aria-current', 'page')
  })

  it('ordem em rascunho: explica e leva à ordem, sem ações', async () => {
    api({ ordem: ordemDoDia(hoje, { status_ordem: 'rascunho' }) })
    renderizarApp('/distribuicao')
    expect(await screen.findByText('A ordem de produção deste dia ainda é um rascunho.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir a ordem de produção' })).toHaveAttribute('href', `/producao?data=${hoje}`)
    expect(screen.queryByRole('button', { name: /Registrar produção|Gerar romaneio/ })).not.toBeInTheDocument()
  })

  it('sem romaneio: "Registrar produção" é a principal; valida, envia e depois "Gerar romaneio"', async () => {
    const { fetch } = api()
    renderizarApp('/distribuicao')
    const registrar = await screen.findByRole('button', { name: 'Registrar produção' })
    expect(registrar).toHaveAttribute('data-variant', 'default')
    expect(screen.queryByRole('button', { name: 'Gerar romaneio' })).not.toBeInTheDocument()
    await userEvent.click(registrar)
    const dialogo = await screen.findByRole('dialog', { name: /Registrar a produção/ })
    const pao = within(dialogo).getByLabelText('INT-007 · Pão Francês')
    expect(pao).toHaveValue('19') // vem com o planejado
    await userEvent.clear(pao)
    await userEvent.type(pao, '10,5')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar produção' }))
    expect(within(dialogo).getByText('Este produto é vendido por unidade: informe um número inteiro.')).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/producao')).toHaveLength(0)
    await userEvent.clear(pao)
    await userEvent.type(pao, '10')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar produção' }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/distribuicao/ordens/7/producao')).toHaveLength(1))
    expect(corpo(fetch, 'POST', '/distribuicao/ordens/7/producao')).toEqual({
      itens: [{ item_id: 10, quantidade: '10' }, { item_id: 11, quantidade: '4.5' }],
    })
    const gerar = await screen.findByRole('button', { name: 'Gerar romaneio' })
    expect(gerar).toHaveAttribute('data-variant', 'default')
    expect(screen.getByRole('button', { name: 'Corrigir produção' })).toHaveAttribute('data-variant', 'secondary')
    expect(screen.getByText('Faltou: o romaneio divide entre as lojas')).toBeInTheDocument()
    await userEvent.click(gerar)
    await waitFor(() => expect(corpo(fetch, 'POST', '/romaneios/gerar')).toEqual({ ordem_id: 7 }))
    expect(await screen.findByText(/Romaneio gerado: 2 lojas\. 1 produto ficou abaixo do planejado/)).toBeInTheDocument()
  })

  it('rascunho: sugestão por loja, uma ação principal e nada de "Registrar saída"', async () => {
    api({ romaneio: romaneioDetalhe(hoje) })
    renderizarApp('/distribuicao')
    const tabela = await screen.findByRole('table', { name: 'Entregas por loja' })
    const linhas = within(tabela).getAllByRole('row').slice(1).map((r) => r.textContent)
    expect(linhas[0]).toMatch(/001 · Loja Centro.*Pão Francês.*3 un.*3 un/)
    expect(linhas[2]).toMatch(/002 · Loja Bairro.*Pão Francês.*7 un/)
    expect(screen.getByText('Rascunho')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Aprovar romaneio' })).toHaveAttribute('data-variant', 'default')
    for (const nome of ['Gerar de novo', 'Apagar romaneio', 'Corrigir produção']) {
      expect(screen.getByRole('button', { name: nome })).toHaveAttribute('data-variant', 'secondary')
    }
    expect(screen.queryByRole('button', { name: /Registrar saída/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Imprimir' })).not.toBeInTheDocument()
  })

  it('soma das lojas acima do produzido: o navegador avisa e não chama a API', async () => {
    const r = romaneioDetalhe(hoje)
    r.producao[0] = { ...r.producao[0], total_final: '11.000' }
    const { fetch } = api({ romaneio: r })
    renderizarApp('/distribuicao')
    expect(await screen.findByText('1 un além do produzido')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Aprovar romaneio' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/Mais do que o produzido em Pão Francês \(11 un para 10 un produzidos\)/)).toBeInTheDocument()
    expect(within(dialogo).queryByRole('button', { name: 'Aprovar romaneio' })).not.toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/aprovar')).toHaveLength(0)
  })

  it('ajustar uma loja manda o PATCH do item, com o motivo', async () => {
    const { fetch } = api({ romaneio: romaneioDetalhe(hoje) }, { 'PATCH /distribuicao/romaneios/30/itens/203': resposta(200, {}) })
    renderizarApp('/distribuicao')
    await userEvent.click(await screen.findByRole('button', { name: 'Ajustar Pão Francês na loja 002' }))
    const dialogo = await screen.findByRole('dialog', { name: /Ajustar Pão Francês/ })
    const campo = within(dialogo).getByLabelText('Quantidade para a loja')
    await userEvent.clear(campo)
    await userEvent.type(campo, '6')
    await userEvent.type(within(dialogo).getByLabelText('Motivo (opcional)'), 'loja pediu menos')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Salvar quantidade' }))
    await waitFor(() => expect(chamadas(fetch, 'PATCH', '/itens/203')).toHaveLength(1))
    expect(corpo(fetch, 'PATCH', '/itens/203')).toEqual({ quantidade_final: '6', motivo: 'loja pediu menos' })
  })

  it('gerar de novo com ajustes pede confirmação dizendo quantos se perdem', async () => {
    const r = romaneioDetalhe(hoje)
    r.entregas[1].itens[0] = { ...r.entregas[1].itens[0], editado_em: '2026-10-28T12:30:00', motivo_edicao: 'pedido' }
    const { fetch } = api({ romaneio: r })
    renderizarApp('/distribuicao')
    await userEvent.click(await screen.findByRole('button', { name: 'Gerar de novo' }))
    const dialogo = await screen.findByRole('dialog', { name: /Gerar o romaneio de novo/ })
    expect(within(dialogo).getByText(/1 quantidade ajustada será perdida/)).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/gerar')).toHaveLength(0)
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Gerar de novo' }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/gerar')).toHaveLength(1))
  })

  it('aprovar: confirma e chama a API; erro 409 aparece em português, sem código', async () => {
    const { fetch } = api({ romaneio: romaneioDetalhe(hoje) }, {
      'POST /distribuicao/romaneios/30/aprovar': resposta(409, { detail: 'Este romaneio já foi aprovado.' }),
    })
    renderizarApp('/distribuicao')
    await userEvent.click(await screen.findByRole('button', { name: 'Aprovar romaneio' }))
    const dialogo = await screen.findByRole('dialog')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Aprovar romaneio' }))
    expect(await within(dialogo).findByText('Este romaneio já foi aprovado.')).toBeInTheDocument()
    expect(within(dialogo).getByText('Confira o romaneio e tente de novo.')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/409|Erro \d/)
    expect(chamadas(fetch, 'POST', '/aprovar')).toHaveLength(1)
  })

  describe('romaneio aprovado', () => {
    it('"Registrar saída" é a principal e pede confirmação; "todas as que faltam" vai sem lista', async () => {
      const { fetch } = api({ romaneio: aprovado() }, {
        'POST /distribuicao/romaneios/30/saida': resposta(200, { entregas: [101, 102] }),
      })
      renderizarApp('/distribuicao')
      const botao = await screen.findByRole('button', { name: 'Registrar saída' })
      expect(botao).toHaveAttribute('data-variant', 'default')
      expect(screen.getByRole('button', { name: 'Imprimir' })).toHaveAttribute('data-variant', 'secondary')
      await userEvent.click(botao)
      const dialogo = await screen.findByRole('dialog', { name: /Registrar a saída/ })
      expect(within(dialogo).getByText(/não se desfaz/)).toBeInTheDocument()
      expect(chamadas(fetch, 'POST', '/saida')).toHaveLength(0) // nada sai sem confirmar
      expect(within(dialogo).getByLabelText('Todas as que faltam (2 lojas)')).toBeChecked()
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar saída' }))
      await waitFor(() => expect(chamadas(fetch, 'POST', '/saida')).toHaveLength(1))
      expect(corpo(fetch, 'POST', '/saida')).toBeUndefined()
      expect(await screen.findByText('Saída registrada: 2 lojas.')).toBeInTheDocument()
    })

    it('escolher uma loja manda só ela; nenhuma escolhida pede uma', async () => {
      const { fetch } = api({ romaneio: aprovado() }, {
        'POST /distribuicao/romaneios/30/saida': resposta(200, { entregas: [102] }),
      })
      renderizarApp('/distribuicao')
      await userEvent.click(await screen.findByRole('button', { name: 'Registrar saída' }))
      const dialogo = await screen.findByRole('dialog')
      await userEvent.click(within(dialogo).getByLabelText(/Todas as que faltam/))
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar saída' }))
      expect(within(dialogo).getByText('Escolha pelo menos uma loja.')).toBeInTheDocument()
      expect(chamadas(fetch, 'POST', '/saida')).toHaveLength(0)
      await userEvent.click(within(dialogo).getByLabelText('002 · Loja Bairro'))
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar saída' }))
      await waitFor(() => expect(corpo(fetch, 'POST', '/saida')).toEqual({ entrega_ids: [102] }))
    })

    it('acompanhamento por loja: "sem confirmação" nunca aparece como recebido', async () => {
      const e = entregas()
      e[0] = {
        ...e[0], situacao: { situacao: 'sem_confirmacao', pode_confirmar: true, com_diferenca: false },
        expedido_em: '2026-10-27T09:00:00',
      }
      e[1] = {
        ...e[1], situacao: { situacao: 'recebida', pode_confirmar: false, com_diferenca: true },
        expedido_em: '2026-10-27T09:00:00', recebido_em: '2026-10-27T13:00:00',
        itens: [{ ...e[1].itens[0], quantidade_recebida: '5.000', motivo_divergencia: 'falta' }, { ...e[1].itens[1], quantidade_recebida: '2.000' }],
      }
      api({ romaneio: aprovado({ entregas: e }) })
      renderizarApp('/distribuicao')
      const tabela = await screen.findByRole('table', { name: 'Acompanhamento por loja' })
      const [, centro, bairro] = within(tabela).getAllByRole('row')
      expect(within(centro).getByText('Sem confirmação')).toBeInTheDocument()
      expect(centro.textContent).not.toMatch(/Recebido/)
      expect(within(bairro).getByText('Recebido com diferença')).toBeInTheDocument()
      // Tudo saiu: "Imprimir" vira a principal e "Registrar saída" some.
      expect(screen.queryByRole('button', { name: 'Registrar saída' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Imprimir' })).toHaveAttribute('data-variant', 'default')
      await userEvent.click(within(bairro).getByRole('button', { name: 'Ver os itens da loja 002' }))
      expect(screen.getByText(/enviado 7 un · recebido 5 un · Faltou/)).toBeInTheDocument()
      expect(screen.getByText(/2 lojas: 1 sem confirmação · 1 recebido com diferença/)).toBeInTheDocument()
    })

    it('imprimir: todas as lojas por padrão; escolher manda o filtro', async () => {
      const pdf = () => new Response('%PDF-1.4', { status: 200, headers: { 'Content-Type': 'application/pdf' } })
      const { fetch } = api({ romaneio: aprovado() }, { 'GET /distribuicao/romaneios/30/pdf': pdf })
      const aba = { location: { href: '' }, close: vi.fn() }
      vi.stubGlobal('open', vi.fn(() => aba))
      URL.createObjectURL = vi.fn(() => 'blob:pdf-teste')
      renderizarApp('/distribuicao')
      await userEvent.click(await screen.findByRole('button', { name: 'Imprimir' }))
      let dialogo = await screen.findByRole('dialog', { name: /Imprimir o romaneio/ })
      expect(within(dialogo).getByLabelText('Todas as lojas')).toBeChecked()
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Abrir PDF' }))
      await waitFor(() => expect(aba.location.href).toBe('blob:pdf-teste'))
      expect(String(chamadas(fetch, 'GET', '/pdf')[0][0])).toMatch(/\/romaneios\/30\/pdf$/)
      await userEvent.click(screen.getByRole('button', { name: 'Imprimir' }))
      dialogo = await screen.findByRole('dialog', { name: /Imprimir o romaneio/ })
      await userEvent.click(within(dialogo).getByLabelText('Todas as lojas'))
      await userEvent.click(within(dialogo).getByLabelText('002 · Loja Bairro'))
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Abrir PDF' }))
      await waitFor(() => expect(chamadas(fetch, 'GET', '/pdf')).toHaveLength(2))
      expect(String(chamadas(fetch, 'GET', '/pdf')[1][0])).toMatch(/\/pdf\?lojas=2$/)
    })
  })

  it('diferenças no recebimento: tabela com diferença e motivo; período padrão de 7 dias', async () => {
    const { fetch } = api({ ordem: null }, {
      'GET /distribuicao/divergencias': resposta(200, {
        data_inicio: '2026-10-22', data_fim: hoje,
        divergencias: [{
          data_entrega: '2026-10-27', loja: { id: 1, codigo: '001', nome: 'Loja Centro' },
          produto: { id: 1, codigo: 'INT-007', nome: 'Pão Francês' }, unidade: 'UN', quantidade_enviada: '3.000',
          quantidade_recebida: '2.000', diferenca: '-1.000', motivo: 'avaria', observacao: 'caixa amassada',
          recebido_em: '2026-10-27T13:00:00',
        }],
        totais: [{ unidade: 'UN', enviada: '3.000', recebida: '2.000', diferenca: '-1.000' }],
      }),
    })
    renderizarApp('/distribuicao')
    const tabela = await screen.findByRole('table', { name: 'Diferenças no recebimento' })
    expect(within(tabela).getAllByRole('row')[1].textContent).toMatch(/27\/10\/2026.*001 · Loja Centro.*Pão Francês.*3 un.*2 un.*−1 un.*Avaria.*caixa amassada/)
    const url = String(chamadas(fetch, 'GET', '/divergencias')[0][0])
    const fim = new Date(`${hoje}T12:00:00Z`)
    fim.setUTCDate(fim.getUTCDate() - 6)
    expect(url).toContain(`data_inicio=${fim.toISOString().slice(0, 10)}&data_fim=${hoje}`)
  })

  it('sem diferenças no período: estado vazio que diz o período', async () => {
    api({ ordem: null })
    renderizarApp('/distribuicao')
    expect(await screen.findByText(/Nenhuma diferença confirmada pelas lojas de/)).toBeInTheDocument()
  })
})
