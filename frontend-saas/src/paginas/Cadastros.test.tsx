import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import type { LojaDoProduto, SetorProducao } from '@/lib/api/tipos'
import { CENTRAL, LISTA, SETORES, lojasDoProduto, produtoDetalhe } from '@/test/cadastros'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

type Fetch = ReturnType<typeof simularApi>

function chamadas(fetch: Fetch, metodo: string, trecho: string) {
  return fetch.mock.calls.filter(([url, init]) => String(url).includes(trecho) && (init?.method ?? 'GET') === metodo)
}

function corpo(fetch: Fetch, metodo: string, trecho: string, n = 0) {
  const init = chamadas(fetch, metodo, trecho)[n][1]
  return init?.body === undefined ? undefined : JSON.parse(String(init.body))
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

describe('cadastros: produtos (C4)', () => {
  it('menu leva à lista de produtos; cada produto abre o cadastro', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME), 'GET /web/produtos': resposta(200, LISTA) })
    renderizarApp('/cadastros')
    const tabela = await screen.findByRole('table', { name: 'Produtos' })
    expect(screen.getByRole('link', { name: /Cadastros/ })).toHaveAttribute('aria-current', 'page')
    expect(within(tabela).getByRole('link', { name: 'Pão Francês' })).toHaveAttribute('href', '/cadastros/produtos/17')
    const linhas = within(tabela).getAllByRole('row')
    expect(linhas[1]).toHaveTextContent('INT-007Pão FrancêskgProduzidoPães2Ativo')
    expect(linhas[2]).toHaveTextContent('INT-020ManteigaunDistribuídoSem setor0Inativo')
    // Uma ação principal: "Novo produto".
    expect(screen.getByRole('link', { name: 'Novo produto' })).toHaveAttribute('data-variant', 'default')
  })

  it('busca vai para a API (e para a URL); sem resultado: mensagem com o termo', async () => {
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /web/produtos': (_init, url) =>
        resposta(200, url.searchParams.get('busca') ? { ...LISTA, total: 0, itens: [] } : LISTA),
    })
    renderizarApp('/cadastros/produtos')
    await screen.findByRole('table', { name: 'Produtos' })
    await userEvent.type(screen.getByLabelText('Buscar produto'), 'pao doce')
    expect(await screen.findByText('Nenhum produto com “pao doce” no código ou no nome.')).toBeInTheDocument()
    const ultima = String(chamadas(fetch, 'GET', '/web/produtos').at(-1)?.[0])
    expect(new URL(ultima, 'http://x').searchParams.get('busca')).toBe('pao doce')
  })

  it('lista vazia: diz o que fazer', async () => {
    simularApi({ 'GET /web/me': resposta(200, ME), 'GET /web/produtos': resposta(200, { ...LISTA, total: 0, itens: [] }) })
    renderizarApp('/cadastros/produtos')
    expect(await screen.findByText('Nenhum produto cadastrado ainda.')).toBeInTheDocument()
  })

  it('novo produto: valida no navegador, envia o corpo certo e abre o produto criado', async () => {
    const criado = produtoDetalhe({ id: 40, codigo: 'PAN-01', nome: 'Panetone', tem_historico: false })
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': resposta(200, SETORES),
      'POST /web/produtos': resposta(201, criado),
      'GET /web/produtos/40': resposta(200, criado),
      'GET /web/produtos/40/lojas': resposta(200, lojasDoProduto()),
    })
    renderizarApp('/cadastros/produtos/novo')
    const salvar = await screen.findByRole('button', { name: 'Cadastrar produto' })
    await userEvent.click(salvar)
    expect(await screen.findByText('Informe o nome do produto.')).toBeInTheDocument()
    expect(screen.getByText(/^Informe o código/)).toBeInTheDocument()
    expect(chamadas(fetch, 'POST', '/web/produtos')).toHaveLength(0)

    await userEvent.type(screen.getByLabelText('Nome do produto'), 'Panetone')
    await userEvent.type(screen.getByLabelText('Código'), 'PAN-01')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sexta' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Segunda' }))
    expect(screen.getByText('A central produz segunda e sexta.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Margem de segurança (opcional)'), '12,5')
    await userEvent.click(screen.getByRole('radio', { name: /Sazonal/ }))
    await userEvent.type(screen.getByLabelText('Início da temporada'), '2026-11-01')
    await userEvent.type(screen.getByLabelText('Fim da temporada'), '2027-01-06')
    await userEvent.click(screen.getByRole('combobox', { name: 'Setor de produção' }))
    // O setor inativo não aparece na escolha.
    expect(screen.queryByRole('option', { name: /Velho/ })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('option', { name: 'Bolos' }))
    expect(screen.getByRole('checkbox', { name: 'Ativar em todas as lojas ativas da central' })).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar produto' }))

    await waitFor(() => expect(chamadas(fetch, 'POST', '/web/produtos')).toHaveLength(1))
    expect(corpo(fetch, 'POST', '/web/produtos')).toEqual({
      nome: 'Panetone', codigo: 'PAN-01', codigo_barras: null, unidade_medida: 'UN', peso_medio_kg: null, ativo: true,
      tipo_abastecimento: 'produzido', dias_validade: null, margem_maxima_percentual: '12.5',
      data_inicio_vigencia: '2026-11-01', data_fim_vigencia: '2027-01-06', vigencia_recorrente: true,
      ciclo_previsao: 'sazonal', setor_producao_id: 2, dias_producao: ['segunda', 'sexta'], habilitar_lojas: true,
    })
    expect(await screen.findByRole('heading', { name: 'PAN-01 · Panetone' })).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Lojas do produto' })).toBeInTheDocument()
  })

  it('novo produto: erro da API aparece em português, sem código', async () => {
    simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': resposta(200, SETORES),
      'POST /web/produtos': resposta(422, { detail: 'O código "PX" já é do produto "Pão Francês".' }),
    })
    renderizarApp('/cadastros/produtos/novo')
    await userEvent.type(await screen.findByLabelText('Nome do produto'), 'Outro')
    await userEvent.type(screen.getByLabelText('Código'), 'PX')
    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar produto' }))
    expect(await screen.findByText('O produto não foi salvo. O código "PX" já é do produto "Pão Francês".')).toBeInTheDocument()
    expect(screen.queryByText(/422/)).not.toBeInTheDocument()
  })

  it('editar: unidade travada com histórico (D98), salva só pelo PATCH e não oferece ativar lojas', async () => {
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': resposta(200, SETORES),
      'GET /web/produtos/17': resposta(200, produtoDetalhe()),
      'GET /web/produtos/17/lojas': resposta(200, lojasDoProduto()),
      'PATCH /web/produtos/17': resposta(200, produtoDetalhe({ nome: 'Pão Francês grande' })),
    })
    renderizarApp('/cadastros/produtos/17')
    const nome = await screen.findByLabelText('Nome do produto')
    expect(nome).toHaveValue('Pão Francês')
    expect(screen.getByRole('combobox', { name: 'Unidade' })).toBeDisabled()
    expect(screen.getByText(/Não muda: o produto já tem vendas/)).toBeInTheDocument()
    expect(screen.getByLabelText('Peso médio de uma peça (opcional)')).toHaveValue('0,05')
    expect(screen.getByRole('checkbox', { name: 'Segunda' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Terça' })).not.toBeChecked()
    expect(screen.queryByRole('checkbox', { name: /Ativar em todas/ })).not.toBeInTheDocument()
    await userEvent.clear(nome)
    await userEvent.type(nome, 'Pão Francês grande')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar produto' }))
    await waitFor(() => expect(chamadas(fetch, 'PATCH', '/web/produtos/17')).toHaveLength(1))
    expect(corpo(fetch, 'PATCH', '/web/produtos/17')).toMatchObject({
      nome: 'Pão Francês grande', codigo: 'INT-007', unidade_medida: 'KG', peso_medio_kg: '0.05', setor_producao_id: 1,
      dias_producao: ['segunda', 'quarta'], ciclo_previsao: 'semanal', vigencia_recorrente: false,
    })
    expect(corpo(fetch, 'PATCH', '/web/produtos/17')).not.toHaveProperty('habilitar_lojas')
    expect(await screen.findByText('Produto salvo. Vale a partir da próxima previsão e da próxima ordem.')).toBeInTheDocument()
  })

  it('editar: produto inexistente mostra o erro e o caminho de volta', async () => {
    simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /web/produtos/99': resposta(404, { detail: 'Produto não encontrado.' }),
    })
    renderizarApp('/cadastros/produtos/99')
    expect(await screen.findByText('Produto não encontrado.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Voltar para a lista de produtos' })).toHaveAttribute('href', '/cadastros/produtos')
  })

  it('lojas do produto: desativar e ativar mudam na hora (D100)', async () => {
    let lojas: LojaDoProduto[] = lojasDoProduto()
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': resposta(200, SETORES),
      'GET /web/produtos/17': resposta(200, produtoDetalhe()),
      'GET /web/produtos/17/lojas': () => resposta(200, lojas),
      'PUT /web/produtos/17/lojas/1': (init) => {
        const ativo = JSON.parse(String(init.body)).ativo
        lojas = lojas.map((l) => (l.loja_id === 1 ? { ...l, ativo } : l))
        return resposta(200, lojas[0])
      },
      'PUT /web/produtos/17/lojas/2': () => {
        lojas = lojas.map((l) => (l.loja_id === 2 ? { ...l, habilitado: true, ativo: true } : l))
        return resposta(200, lojas[1])
      },
    })
    renderizarApp('/cadastros/produtos/17')
    const tabela = await screen.findByRole('table', { name: 'Lojas do produto' })
    expect(within(tabela).getAllByRole('row')[2]).toHaveTextContent('Nunca ativado')
    await userEvent.click(within(tabela).getByRole('button', { name: 'Desativar nesta loja: 001 · Loja Centro' }))
    await waitFor(() => expect(chamadas(fetch, 'PUT', '/lojas/1')).toHaveLength(1))
    expect(corpo(fetch, 'PUT', '/lojas/1')).toEqual({ ativo: false })
    expect(await screen.findByText('Produto desativado em 001 · Loja Centro.')).toBeInTheDocument()
    expect(within(tabela).getAllByRole('row')[1]).toHaveTextContent('Desativado')
    await userEvent.click(within(tabela).getByRole('button', { name: 'Ativar nesta loja: 002 · Loja Bairro' }))
    await waitFor(() => expect(within(tabela).getAllByRole('row')[2]).toHaveTextContent('Ativo'))
    expect(corpo(fetch, 'PUT', '/lojas/2')).toEqual({ ativo: true })
  })

  it('produto inativo: avisa que não aparece em nenhuma loja', async () => {
    simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': resposta(200, SETORES),
      'GET /web/produtos/17': resposta(200, produtoDetalhe({ ativo: false })),
      'GET /web/produtos/17/lojas': resposta(200, lojasDoProduto()),
    })
    renderizarApp('/cadastros/produtos/17')
    expect(await screen.findByText('O produto está inativo.')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Produto ativo' })).not.toBeChecked()
  })
})

describe('cadastros: setores (C4)', () => {
  function apiSetores(inicial: SetorProducao[] = SETORES) {
    let setores = inicial.map((s) => ({ ...s }))
    const patch = (id: number) => (init: RequestInit) => {
      const mud = JSON.parse(String(init.body))
      setores = setores.map((s) => (s.id === id ? { ...s, ...mud } : s)).sort((a, b) => a.ordem - b.ordem)
      return resposta(200, setores.find((s) => s.id === id))
    }
    return simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': () => resposta(200, setores),
      'POST /producao/setores': (init) => {
        const novo = { id: 9, nome: JSON.parse(String(init.body)).nome, ordem: 4, ativo: true }
        setores = [...setores, novo]
        return resposta(201, novo)
      },
      'PATCH /producao/setores/1': patch(1),
      'PATCH /producao/setores/2': patch(2),
      'PATCH /producao/setores/3': patch(3),
    })
  }

  it('lista na ordem das folhas; "Novo setor" cria pelo diálogo (nome obrigatório)', async () => {
    const fetch = apiSetores()
    renderizarApp('/cadastros/setores')
    const tabela = await screen.findByRole('table', { name: 'Setores de produção' })
    expect(within(tabela).getAllByRole('row').map((r) => r.textContent)).toEqual([
      expect.stringContaining('Folha'),
      expect.stringContaining('1PãesAtivo'),
      expect.stringContaining('2BolosAtivo'),
      expect.stringContaining('3VelhoDesativado'),
    ])
    await userEvent.click(screen.getByRole('button', { name: 'Novo setor' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Novo setor de produção' })
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Criar setor' }))
    expect(within(dialogo).getByText('Informe o nome do setor.')).toBeInTheDocument()
    await userEvent.type(within(dialogo).getByLabelText('Nome do setor'), ' Salgados ')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Criar setor' }))
    await waitFor(() => expect(chamadas(fetch, 'POST', '/producao/setores')).toHaveLength(1))
    expect(corpo(fetch, 'POST', '/producao/setores')).toEqual({ nome: 'Salgados' })
    expect(await screen.findByText('Setor “Salgados” criado.')).toBeInTheDocument()
    expect(await within(tabela).findByText('Salgados')).toBeInTheDocument()
  })

  it('nome repetido: o erro da API fica no diálogo', async () => {
    simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /producao/setores': resposta(200, SETORES),
      'PATCH /producao/setores/2': resposta(422, { detail: 'Já existe um setor chamado "Pães" nesta central.' }),
    })
    renderizarApp('/cadastros/setores')
    await userEvent.click(await screen.findByRole('button', { name: 'Renomear: Bolos' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Renomear “Bolos”' })
    const campo = within(dialogo).getByLabelText('Nome do setor')
    expect(campo).toHaveValue('Bolos')
    await userEvent.clear(campo)
    await userEvent.type(campo, 'Pães')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Salvar nome' }))
    expect(await within(dialogo).findByText('O setor não foi salvo. Já existe um setor chamado "Pães" nesta central.')).toBeInTheDocument()
  })

  it('"Descer" troca a ordem e grava só os que mudaram; "Desativar" grava ativo = false', async () => {
    const fetch = apiSetores()
    renderizarApp('/cadastros/setores')
    const tabela = await screen.findByRole('table', { name: 'Setores de produção' })
    expect(within(tabela).getByRole('button', { name: 'Subir: Pães' })).toBeDisabled()
    expect(within(tabela).getByRole('button', { name: 'Descer: Velho' })).toBeDisabled()
    await userEvent.click(within(tabela).getByRole('button', { name: 'Descer: Pães' }))
    await waitFor(() => expect(within(tabela).getAllByRole('row')[1]).toHaveTextContent('Bolos'))
    expect(chamadas(fetch, 'PATCH', '/producao/setores/')).toHaveLength(2)
    expect(corpo(fetch, 'PATCH', '/producao/setores/2')).toEqual({ ordem: 1 })
    expect(corpo(fetch, 'PATCH', '/producao/setores/1')).toEqual({ ordem: 2 })
    await userEvent.click(within(tabela).getByRole('button', { name: 'Desativar: Bolos' }))
    await waitFor(() => expect(chamadas(fetch, 'PATCH', '/producao/setores/2')).toHaveLength(2))
    expect(corpo(fetch, 'PATCH', '/producao/setores/2', 1)).toEqual({ ativo: false })
    expect(await screen.findByText('Setor “Bolos” desativado.')).toBeInTheDocument()
  })

  it('sem setores: estado vazio explica para que servem', async () => {
    apiSetores([])
    renderizarApp('/cadastros/setores')
    expect(await screen.findByText('Nenhum setor cadastrado ainda.')).toBeInTheDocument()
  })
})

describe('cadastros: central (C4)', () => {
  it('mostra seção e lojas só para leitura; salva nome e prazo', async () => {
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'GET /web/central': resposta(200, CENTRAL),
      'PATCH /web/central': resposta(200, { ...CENTRAL, nome: 'Central Norte', prazo_entrega_dias: 1 }),
    })
    renderizarApp('/cadastros/central')
    const nome = await screen.findByLabelText('Nome da central')
    expect(screen.getByText('Padaria')).toBeInTheDocument()
    expect(screen.getByText('2 lojas')).toBeInTheDocument()
    await userEvent.clear(nome)
    await userEvent.click(screen.getByRole('button', { name: 'Salvar central' }))
    expect(screen.getByText('Informe o nome da central.')).toBeInTheDocument()
    expect(chamadas(fetch, 'PATCH', '/web/central')).toHaveLength(0)
    await userEvent.type(nome, 'Central Norte')
    await userEvent.click(screen.getByRole('combobox', { name: 'Entrega nas lojas' }))
    await userEvent.click(await screen.findByRole('option', { name: 'No dia seguinte (1 dia)' }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar central' }))
    await waitFor(() => expect(chamadas(fetch, 'PATCH', '/web/central')).toHaveLength(1))
    expect(corpo(fetch, 'PATCH', '/web/central')).toEqual({ nome: 'Central Norte', prazo_entrega_dias: 1 })
    expect(await screen.findByText('Central salva. O prazo vale para as próximas ordens de produção.')).toBeInTheDocument()
  })
})
