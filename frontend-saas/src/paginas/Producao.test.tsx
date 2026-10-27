import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { OrdemDetalhe } from '@/lib/api/tipos'
import { dataIso, somarDias } from '@/lib/formato'
import { ordemDetalhe, resumoDe } from '@/test/producao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

const hoje = dataIso(new Date())
const amanha = somarDias(hoje, 1)

/** API simulada com uma ordem que muda conforme as ações. */
function api(inicial: OrdemDetalhe | null, extras: Record<string, Response | ((init: RequestInit) => Response)> = {}) {
  const estado = { ordem: inicial }
  const fetch = simularApi({
    'GET /web/me': resposta(200, ME),
    'GET /producao/ordens': () =>
      resposta(200, { data_producao: amanha, ordens: estado.ordem ? [resumoDe(estado.ordem)] : [] }),
    'GET /producao/ordens/7': () => (estado.ordem ? resposta(200, estado.ordem) : resposta(404, { detail: 'Ordem de produção não encontrada.' })),
    'POST /producao/ordens/gerar': () => {
      const substituiu = estado.ordem !== null
      estado.ordem = ordemDetalhe(amanha)
      return resposta(200, {
        ordem_id: 7, data_producao: amanha, data_entrega: amanha, itens: 3, linhas: 4, sem_quantidade: 1,
        substituiu_rascunho: substituiu, previsao_atualizada: true,
      })
    },
    ...extras,
  })
  return { estado, fetch }
}

function chamadas(fetch: ReturnType<typeof simularApi>, metodo: string, trecho: string) {
  return fetch.mock.calls.filter(([url, init]) => String(url).includes(trecho) && ((init?.method ?? 'GET') === metodo))
}

async function abrirLojas(produto: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Ver as lojas de ${produto}` }))
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

describe('tela de ordem de produção (N9)', () => {
  it('sem ordem: estado vazio com "Gerar ordem"; gerar manda a data e mostra a ordem', async () => {
    const { fetch } = api(null)
    renderizarApp('/producao')
    expect(await screen.findByText(/Nenhuma ordem gerada para/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Gerar ordem' }))
    const [, init] = chamadas(fetch, 'POST', '/producao/ordens/gerar')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ data_producao: amanha })
    expect(await screen.findByRole('heading', { name: /Produção de .*/ })).toBeInTheDocument()
    expect(await screen.findByText(/A previsão estava desatualizada e foi calculada de novo/)).toBeInTheDocument()
  })

  it('rascunho: resumo, produção e a distribuir, "sem quantidade" pelo nome, uma ação principal', async () => {
    api(ordemDetalhe(amanha))
    renderizarApp('/producao')
    const resumo = await screen.findByRole('region', { name: 'Resumo da ordem' })
    expect(within(resumo).getByText('Rascunho')).toBeInTheDocument()
    expect(within(resumo).getByText('Produzir em unidades')).toBeInTheDocument()
    expect(within(resumo).getByText('88 un')).toBeInTheDocument()
    expect(within(resumo).getByText('Distribuir em unidades')).toBeInTheDocument()
    expect(within(resumo).getByText(/1 linha está sem quantidade: Bolo de Chocolate \(001\)/)).toBeInTheDocument()
    expect(within(resumo).getByText(/Sem contagem/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Produção' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'A distribuir' })).toBeInTheDocument()
    // Uma ação principal: "Aprovar ordem"; "Gerar de novo" e "Apagar rascunho" secundárias.
    expect(screen.getByRole('button', { name: /Aprovar ordem/ })).toHaveAttribute('data-variant', 'default')
    expect(screen.getByRole('button', { name: /Gerar de novo/ })).toHaveAttribute('data-variant', 'secondary')
    expect(screen.getByRole('button', { name: /Apagar rascunho/ })).toHaveAttribute('data-variant', 'secondary')
  })

  it('lojas do produto: perda nas 4 faixas, avisos e "Ver a conta"', async () => {
    api(ordemDetalhe(amanha))
    renderizarApp('/producao')
    await abrirLojas('Pão Francês')
    const lojas = screen.getByRole('table', { name: 'Lojas de Pão Francês' })
    expect(within(lojas).getByText('2% · perda baixa')).toBeInTheDocument()
    expect(within(lojas).getByText('4% · normal')).toBeInTheDocument()
    expect(within(lojas).getByText('Sem contagem')).toBeInTheDocument()
    await abrirLojas('Bolo de Chocolate')
    expect(within(screen.getByRole('table', { name: 'Lojas de Bolo de Chocolate' })).getByText('6% · perda alta')).toBeInTheDocument()
    await abrirLojas('Manteiga')
    expect(within(screen.getByRole('table', { name: 'Lojas de Manteiga' })).getByText('9% · perda muito alta')).toBeInTheDocument()
    await userEvent.click(within(lojas).getByRole('button', { name: 'Ver a conta de Pão Francês na loja 001' }))
    expect(screen.getByText('Margem de 10% (padrão): alvo de 44 un.')).toBeInTheDocument()
  })

  it('ajustar: valida no navegador e manda quantidade e motivo', async () => {
    const { fetch } = api(ordemDetalhe(amanha), {
      'PATCH /producao/ordens/7/linhas/101': resposta(200, {}),
    })
    renderizarApp('/producao')
    await abrirLojas('Pão Francês')
    await userEvent.click(screen.getByRole('button', { name: 'Ajustar Pão Francês na loja 001' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Ajustar Pão Francês' })
    const campo = within(dialogo).getByLabelText('Quantidade para a loja')
    await userEvent.clear(campo)
    await userEvent.type(campo, '12,5')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Salvar quantidade' }))
    expect(within(dialogo).getByText('Este produto é vendido por unidade: informe um número inteiro.')).toBeInTheDocument()
    expect(chamadas(fetch, 'PATCH', '/linhas/')).toHaveLength(0)
    await userEvent.clear(campo)
    await userEvent.type(campo, '50')
    await userEvent.type(within(dialogo).getByLabelText('Motivo (opcional)'), 'festa no bairro')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Salvar quantidade' }))
    await waitFor(() => expect(chamadas(fetch, 'PATCH', '/linhas/101')).toHaveLength(1))
    const [, init] = chamadas(fetch, 'PATCH', '/linhas/101')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ quantidade_final: '50', motivo: 'festa no bairro' })
    expect(await screen.findByText('Quantidade salva.')).toBeInTheDocument()
  })

  it('D58: gerar de novo com ajustes pede confirmação com o número de linhas perdidas', async () => {
    const { fetch } = api(ordemDetalhe(amanha, { linhas_editadas: 2 }))
    renderizarApp('/producao')
    await userEvent.click(await screen.findByRole('button', { name: /Gerar de novo/ }))
    const dialogo = await screen.findByRole('dialog', { name: 'Gerar a ordem de novo?' })
    expect(within(dialogo).getByText(/2 linhas ajustadas serão perdidas/)).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/gerar')).toHaveLength(0)
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Gerar de novo' }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/gerar')).toHaveLength(1))
  })

  it('gerar de novo sem ajustes não pede confirmação', async () => {
    const { fetch } = api(ordemDetalhe(amanha, { linhas_editadas: 0 }))
    renderizarApp('/producao')
    await userEvent.click(await screen.findByRole('button', { name: /Gerar de novo/ }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/gerar')).toHaveLength(1))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('aprovar com linha sem quantidade: o diálogo explica e não deixa aprovar', async () => {
    const { fetch } = api(ordemDetalhe(amanha))
    renderizarApp('/producao')
    await userEvent.click(await screen.findByRole('button', { name: /Aprovar ordem/ }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/Ainda 1 linha está sem quantidade/)).toBeInTheDocument()
    expect(within(dialogo).queryByRole('button', { name: 'Aprovar ordem' })).not.toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/aprovar')).toHaveLength(0)
  })

  it('aprovar: confirma e chama a API; erro 409 aparece em português, sem código', async () => {
    const { fetch } = api(ordemDetalhe(amanha, { linhas_sem_quantidade: 0 }), {
      'POST /producao/ordens/7/aprovar': resposta(409, { detail: 'A ordem já foi aprovada.' }),
    })
    renderizarApp('/producao')
    await userEvent.click(await screen.findByRole('button', { name: /Aprovar ordem/ }))
    const dialogo = await screen.findByRole('dialog')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Aprovar ordem' }))
    expect(await within(dialogo).findByText('A ordem já foi aprovada.')).toBeInTheDocument()
    expect(within(dialogo).queryByText(/409/)).not.toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/aprovar')).toHaveLength(1)
  })

  it('apagar rascunho: diálogo de perigo e DELETE', async () => {
    const { fetch } = api(ordemDetalhe(amanha), {
      'DELETE /producao/ordens/7': new Response(null, { status: 204 }),
    })
    renderizarApp('/producao')
    await userEvent.click(await screen.findByRole('button', { name: /Apagar rascunho/ }))
    const dialogo = await screen.findByRole('dialog', { name: /Apagar o rascunho/ })
    const botao = within(dialogo).getByRole('button', { name: 'Apagar rascunho' })
    expect(botao).toHaveAttribute('data-variant', 'destructive')
    await userEvent.click(botao)
    await waitFor(() => expect(chamadas(fetch, 'DELETE', '/producao/ordens/7')).toHaveLength(1))
  })

  it('ordem aprovada fica só leitura', async () => {
    api(
      ordemDetalhe(amanha, {
        status: 'aprovada', aprovado_em: '2026-10-16T01:00:00', aprovado_por: 'Gestor Central Teste', linhas_sem_quantidade: 0,
      }),
    )
    renderizarApp('/producao')
    expect(await screen.findByText('Ordem aprovada: só leitura.')).toBeInTheDocument()
    expect(screen.getByText('Aprovada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Aprovar ordem/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Gerar de novo/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Apagar rascunho/ })).not.toBeInTheDocument()
    await abrirLojas('Pão Francês')
    expect(screen.queryByRole('button', { name: /^Ajustar/ })).not.toBeInTheDocument()
    expect(screen.getByText(/aprovada em .* por Gestor Central Teste/)).toBeInTheDocument()
  })

  describe('imprimir (N9b, D67)', () => {
    const SETORES = [
      { id: 1, nome: 'Pães', ordem: 1, ativo: true },
      { id: 2, nome: 'Bolos e doces', ordem: 2, ativo: true },
      { id: 3, nome: 'Antigo', ordem: 3, ativo: false },
    ]
    const aprovada = () =>
      ordemDetalhe(amanha, { status: 'aprovada', aprovado_em: '2026-10-16T01:00:00', aprovado_por: 'Gestor', linhas_sem_quantidade: 0 })

    function abrirAba() {
      const aba = { location: { href: '' }, close: vi.fn() }
      const open = vi.fn(() => aba)
      vi.stubGlobal('open', open)
      URL.createObjectURL = vi.fn(() => 'blob:pdf-teste')
      return { aba, open }
    }

    function apiImpressao(pdf: Response | (() => Response) = () => new Response('%PDF-1.4', { status: 200, headers: { 'Content-Type': 'application/pdf' } })) {
      return api(aprovada(), {
        'GET /producao/setores': resposta(200, SETORES),
        'GET /producao/ordens/7/pdf': typeof pdf === 'function' ? pdf : () => pdf.clone(),
      })
    }

    it('rascunho não tem "Imprimir"', async () => {
      api(ordemDetalhe(amanha))
      renderizarApp('/producao')
      await screen.findByRole('button', { name: /Aprovar ordem/ })
      expect(screen.queryByRole('button', { name: /^Imprimir$/ })).not.toBeInTheDocument()
    })

    it('aprovada: "Imprimir" é a ação principal; "Todos" marcado abre o PDF de todos os setores', async () => {
      const { fetch } = apiImpressao()
      const { aba, open } = abrirAba()
      renderizarApp('/producao')
      const botao = await screen.findByRole('button', { name: 'Imprimir' })
      expect(botao).toHaveAttribute('data-variant', 'default')
      await userEvent.click(botao)
      const dialogo = await screen.findByRole('dialog', { name: /Imprimir a ordem/ })
      expect(within(dialogo).getByLabelText('Todos os setores')).toBeChecked()
      expect(await within(dialogo).findByLabelText('Pães')).toBeChecked()
      expect(within(dialogo).getByLabelText('Sem setor')).toBeChecked()
      expect(within(dialogo).queryByLabelText('Antigo')).not.toBeInTheDocument() // inativo não aparece
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Abrir PDF' }))
      await waitFor(() => expect(aba.location.href).toBe('blob:pdf-teste'))
      expect(open).toHaveBeenCalledTimes(1)
      const [url] = chamadas(fetch, 'GET', '/pdf')[0]
      expect(String(url)).toMatch(/\/producao\/ordens\/7\/pdf$/)
    })

    it('escolher setores manda só os escolhidos (com "sem")', async () => {
      const { fetch } = apiImpressao()
      abrirAba()
      renderizarApp('/producao')
      await userEvent.click(await screen.findByRole('button', { name: 'Imprimir' }))
      const dialogo = await screen.findByRole('dialog')
      await userEvent.click(within(dialogo).getByLabelText('Todos os setores'))
      await userEvent.click(await within(dialogo).findByLabelText('Bolos e doces'))
      await userEvent.click(within(dialogo).getByLabelText('Sem setor'))
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Abrir PDF' }))
      await waitFor(() => expect(chamadas(fetch, 'GET', '/pdf')).toHaveLength(1))
      expect(String(chamadas(fetch, 'GET', '/pdf')[0][0])).toMatch(/\/pdf\?setores=2,sem$/)
    })

    it('nenhum setor escolhido: pede um, sem chamar a API', async () => {
      const { fetch } = apiImpressao()
      abrirAba()
      renderizarApp('/producao')
      await userEvent.click(await screen.findByRole('button', { name: 'Imprimir' }))
      const dialogo = await screen.findByRole('dialog')
      await within(dialogo).findByLabelText('Pães')
      await userEvent.click(within(dialogo).getByLabelText('Todos os setores'))
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Abrir PDF' }))
      expect(within(dialogo).getByText('Escolha pelo menos um setor.')).toBeInTheDocument()
      expect(chamadas(fetch, 'GET', '/pdf')).toHaveLength(0)
    })

    it('erro da API (409) aparece em português e a aba aberta é fechada', async () => {
      apiImpressao(() => resposta(409, { detail: 'Só a ordem aprovada pode ser impressa. Aprove a ordem antes de imprimir.' }))
      const { aba } = abrirAba()
      renderizarApp('/producao')
      await userEvent.click(await screen.findByRole('button', { name: 'Imprimir' }))
      const dialogo = await screen.findByRole('dialog')
      await within(dialogo).findByLabelText('Pães')
      await userEvent.click(within(dialogo).getByRole('button', { name: 'Abrir PDF' }))
      expect(await within(dialogo).findByText(/Só a ordem aprovada pode ser impressa/)).toBeInTheDocument()
      expect(within(dialogo).queryByText(/409/)).not.toBeInTheDocument()
      expect(aba.close).toHaveBeenCalled()
    })
  })

  it('erro 422 ao gerar aparece com a frase do backend', async () => {
    api(null, {
      'POST /producao/ordens/gerar': resposta(422, { detail: 'A ordem pode ser gerada para até 6 dias à frente.' }),
    })
    renderizarApp('/producao')
    await userEvent.click(await screen.findByRole('button', { name: 'Gerar ordem' }))
    expect(await screen.findByText(/A ordem não foi gerada\. A ordem pode ser gerada para até 6 dias à frente\./)).toBeInTheDocument()
    expect(screen.queryByText(/422/)).not.toBeInTheDocument()
  })

  it('dia fora do período: sem botão de gerar, com a explicação', async () => {
    api(null)
    renderizarApp(`/producao?data=${somarDias(hoje, 9)}`)
    expect(await screen.findByText(/A ordem pode ser gerada de hoje até/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Gerar ordem' })).not.toBeInTheDocument()
  })
})
