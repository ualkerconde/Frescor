import { act, fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MENSAGEM_SEM_CONEXAO } from '@/lib/api/cliente'
import { salvarTokens } from '@/lib/api/sessao'
import type { RelatorioImportacao } from '@/lib/api/tipos'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

const LIMITE = 5 * 1024 * 1024

function relatorio(parcial: Partial<RelatorioImportacao>): RelatorioImportacao {
  return {
    sucesso: true,
    linhas_lidas: 0,
    inseridas: 0,
    substituidas: 0,
    codificacao: 'utf-8',
    erros: [],
    erros_omitidos: 0,
    avisos: [],
    avisos_omitidos: 0,
    ...parcial,
  }
}

function csv(nome = 'vendas.csv', conteudo = 'data;codigo_loja;codigo_produto;quantidade\r\n01/10/2026;001;INT-001;5\r\n') {
  return new File([conteudo], nome, { type: 'text/csv' })
}

async function escolherEImportar(arquivo: File, rotuloBotao = 'Importar vendas') {
  const usuario = userEvent.setup()
  await usuario.upload(screen.getByLabelText('Arquivo CSV'), arquivo)
  await usuario.click(screen.getByRole('button', { name: rotuloBotao }))
}

let fetchSimulado: ReturnType<typeof simularApi>

beforeEach(() => {
  localStorage.clear()
  salvarTokens('A1', 'R1')
})
afterEach(() => vi.unstubAllGlobals())

describe('tela de importação (W6)', () => {
  beforeEach(() => {
    fetchSimulado = simularApi({ 'GET /web/me': resposta(200, ME) })
  })

  it('uma única ação principal ("Importar vendas"); o modelo de CSV é secundário', () => {
    renderizarApp('/importar')
    const area = screen.getByRole('main')
    const primarios = within(area).getAllByRole('button').filter((b) => b.className.includes('bg-primary'))
    expect(primarios.map((b) => b.textContent)).toEqual(['Importar vendas'])
    expect(within(area).getByRole('button', { name: 'Baixar modelo de CSV' }).className).toContain('border-primary')
    expect(screen.getByRole('radio', { name: 'Vendas' })).toBeChecked()
  })

  it('sem arquivo: pede para escolher o arquivo e não envia', async () => {
    renderizarApp('/importar')
    await userEvent.click(screen.getByRole('button', { name: 'Importar vendas' }))
    expect(screen.getByText('Escolha o arquivo CSV antes de importar.')).toBeInTheDocument()
    expect(screen.getByLabelText('Arquivo CSV')).toHaveAttribute('aria-invalid', 'true')
    expect(fetchSimulado.mock.calls.some(([url]) => String(url).includes('/importar'))).toBe(false)
  })

  it('arquivo acima de 5 MB: recusado no navegador, sem enviar', async () => {
    renderizarApp('/importar')
    const grande = new File([new Uint8Array(LIMITE + 1)], 'grande.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText('Arquivo CSV'), grande)
    expect(screen.getByText(/o máximo é 5 MB\. Divida em arquivos menores/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Importar vendas' }))
    expect(fetchSimulado.mock.calls.some(([url]) => String(url).includes('/importar'))).toBe(false)
  })

  it('mostra o nome e o tamanho do arquivo escolhido', async () => {
    renderizarApp('/importar')
    await userEvent.upload(screen.getByLabelText('Arquivo CSV'), csv('vendas_setembro.csv'))
    expect(screen.getByText('vendas_setembro.csv')).toBeInTheDocument()
    expect(screen.getByText(/bytes · clique para trocar/)).toBeInTheDocument()
  })

  it('sucesso: resumo grande "1.232 linhas importadas" e o detalhe novas/substituídas', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': resposta(200, relatorio({ linhas_lidas: 1232, inseridas: 1200, substituidas: 32 })),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())

    expect(await screen.findByRole('heading', { level: 2, name: '1.232 linhas importadas' })).toBeInTheDocument()
    expect(screen.getByText('Importação concluída')).toBeInTheDocument()
    expect(screen.getByText(/1\.200 novas · 32 substituídas/)).toBeInTheDocument()
    // Nada técnico na tela: nem a codificação, nem código HTTP.
    expect(document.body.textContent).not.toMatch(/utf-8|windows-1252|HTTP|Erro \d{3}/i)
  })

  it('envia o arquivo no campo "arquivo" para /vendas/importar, com o token', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': resposta(200, relatorio({ inseridas: 1 })),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv('meu.csv'))
    await screen.findByRole('heading', { level: 2, name: '1 linha importada' })

    const chamada = fetchSimulado.mock.calls.find(([url]) => String(url).endsWith('/vendas/importar'))!
    const init = chamada[1] as RequestInit
    expect((init.body as FormData).get('arquivo')).toBeInstanceOf(File)
    expect(((init.body as FormData).get('arquivo') as File).name).toBe('meu.csv')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer A1')
    expect(screen.getByText('É uma linha nova.')).toBeInTheDocument()
  })

  it('perdas: o botão vira "Importar perdas" e envia para /perdas/importar', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /perdas/importar': resposta(200, relatorio({ inseridas: 2 })),
    })
    renderizarApp('/importar')
    await userEvent.click(screen.getByRole('radio', { name: 'Perdas' }))
    await escolherEImportar(csv('perdas.csv'), 'Importar perdas')
    expect(await screen.findByRole('heading', { level: 2, name: '2 linhas importadas' })).toBeInTheDocument()
    expect(fetchSimulado.mock.calls.some(([url]) => String(url).endsWith('/perdas/importar'))).toBe(true)
  })

  it('arquivo com erros (422): "Nada foi gravado: 3 erros", a lista por linha e os avisos', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': resposta(
        422,
        relatorio({
          sucesso: false,
          linhas_lidas: 5,
          erros: [
            { linha: 3, mensagem: "data inexistente '31/02/2026'" },
            { linha: 4, mensagem: "produto 'X' não encontrado no seu negócio" },
          ],
          erros_omitidos: 1,
          avisos: [{ linha: 2, mensagem: "produto 'P-NH' não está habilitado na loja '001'" }],
        }),
      ),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())

    expect(await screen.findByRole('heading', { level: 2, name: 'Nada foi gravado: 3 erros' })).toBeInTheDocument()
    expect(screen.getByText('Corrija as linhas abaixo no arquivo e envie de novo.')).toBeInTheDocument()
    const tabelas = screen.getAllByRole('table')
    expect(within(tabelas[0]).getByRole('row', { name: /Linha 3 data inexistente/ })).toBeInTheDocument()
    expect(within(tabelas[0]).getByRole('row', { name: /Linha 4 produto 'X'/ })).toBeInTheDocument()
    expect(screen.getByText(/E mais 1 erro não listado/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: '1 aviso' })).toBeInTheDocument()
    expect(within(tabelas[1]).getByRole('row', { name: /Linha 2 produto 'P-NH'/ })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\b422\b/)
  })

  it('erro no arquivo como um todo (linha 0): mostra "Arquivo" em vez de "Linha 0"', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': resposta(
        422,
        relatorio({ sucesso: false, erros: [{ linha: 0, mensagem: 'arquivo vazio' }] }),
      ),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())
    expect(await screen.findByRole('heading', { level: 2, name: 'Nada foi gravado: 1 erro' })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Arquivo arquivo vazio/ })).toBeInTheDocument()
    expect(screen.queryByText('Linha 0')).not.toBeInTheDocument()
    expect(screen.getByText('Corrija a linha abaixo no arquivo e envie de novo.')).toBeInTheDocument()
  })

  it('sucesso com avisos: "A importação foi feita, mas vale conferir"', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': resposta(
        200,
        relatorio({ inseridas: 2, avisos: [{ linha: 2, mensagem: "produto 'P-OFF' está desabilitado na loja '001'" }] }),
      ),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())
    expect(await screen.findByText('A importação foi feita, mas vale conferir:')).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Linha 2 produto 'P-OFF'/ })).toBeInTheDocument()
  })

  it('413 do servidor: mensagem da API num alerta', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': resposta(413, { detail: 'Arquivo maior que 5 MB. Divida em arquivos menores.' }),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('Arquivo maior que 5 MB. Divida em arquivos menores.')
  })

  it('sem conexão: mensagem de conexão', async () => {
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': () => {
        throw new TypeError('Failed to fetch')
      },
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())
    expect(await screen.findByRole('alert')).toHaveTextContent(MENSAGEM_SEM_CONEXAO)
  })

  it('enquanto envia: "Importando…" desabilitado (sem envio duplo)', async () => {
    let liberar: (r: Response) => void = () => {}
    fetchSimulado = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /vendas/importar': () => new Promise<Response>((r) => (liberar = r)),
    })
    renderizarApp('/importar')
    await escolherEImportar(csv())
    const botao = screen.getByRole('button', { name: 'Importando…' })
    expect(botao).toBeDisabled()
    await userEvent.click(botao)
    expect(fetchSimulado.mock.calls.filter(([url]) => String(url).endsWith('/vendas/importar'))).toHaveLength(1)
    await act(async () => liberar(resposta(200, relatorio({ inseridas: 1 }))))
  })

  it('arrastar e soltar o arquivo na área também funciona', async () => {
    renderizarApp('/importar')
    const area = screen.getByText('Escolher arquivo').closest('label')!
    fireEvent.drop(area, { dataTransfer: { files: [csv('arrastado.csv')] } })
    expect(screen.getByText('arrastado.csv')).toBeInTheDocument()
  })

  it('"Baixar modelo de CSV": arquivo com BOM, ";" e o cabeçalho certo', async () => {
    let blobGerado: Blob | null = null
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn((b: Blob) => {
        blobGerado = b
        return 'blob:modelo'
      }),
      revokeObjectURL: vi.fn(),
    })
    const clique = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('modelo_vendas.csv')
    })
    renderizarApp('/importar')
    await userEvent.click(screen.getByRole('button', { name: 'Baixar modelo de CSV' }))

    expect(clique).toHaveBeenCalledTimes(1)
    // Bytes crus: o blob.text() remove o BOM ao decodificar (regra do UTF-8).
    const bytes = new Uint8Array(await blobGerado!.arrayBuffer())
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf])
    const texto = new TextDecoder('utf-8', { ignoreBOM: true }).decode(bytes.slice(3))
    expect(texto.split('\r\n')[0]).toBe('data;codigo_loja;codigo_produto;quantidade')
    expect(texto.split('\r\n')[1]).toMatch(/^\d{2}\/\d{2}\/\d{4};001;INT-\d{3};\d+(,\d+)?$/)
    clique.mockRestore()
  })
})
