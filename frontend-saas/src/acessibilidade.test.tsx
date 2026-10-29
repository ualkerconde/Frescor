/*
 * Verificação automática de acessibilidade (passo W8) com o axe-core, nas
 * telas e nos estados principais: login (vazio e com erro), importação
 * (vazia, com sucesso e com erros), consulta (com dados e vazia), previsão
 * (com dados e a conta aberta, vazia, com erro ao gerar), ordem de produção
 * (rascunho com lojas, conta e diálogo abertos; aprovada; dia sem ordem) e
 * distribuição (produção, rascunho com aprovação bloqueada, aprovado com
 * itens, saída e diferenças).
 *
 * Limitação: no jsdom o axe não calcula contraste de cor (não há
 * renderização real). Os contrastes são garantidos pelo tema.test.ts, que
 * confere as cores da skill Frescor e recalcula a razão de contraste.
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import { dataIso, somarDias } from '@/lib/formato'
import { itemPrevisao } from '@/test/previsao'
import { entregas, ordemComRomaneio, ordemDoDia, romaneioDetalhe } from '@/test/distribuicao'
import { ordemDetalhe, resumoDe } from '@/test/producao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'

async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, {
    rules: { 'color-contrast': { enabled: false } },
  })
  return resultado.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  )
}

const LOJAS = [{ id: 1, codigo: '001', nome: 'Loja Centro', ativo: true }]
const CONSULTA = {
  total: 1,
  limit: 50,
  offset: 0,
  itens: [
    {
      data: '2026-09-01',
      loja: { id: 1, codigo: '001' },
      produto: { id: 17, codigo: 'INT-007', nome: 'Pão Francês' },
      quantidade: '3.750',
      unidade: 'KG',
      origem: 'manual',
    },
  ],
  totais: [{ unidade: 'KG', quantidade: '3.750' }],
}
const RELATORIO_OK = { sucesso: true, linhas_lidas: 2, inseridas: 2, substituidas: 0, codificacao: 'utf-8', erros: [], erros_omitidos: 0, avisos: [{ linha: 2, mensagem: 'produto não habilitado' }], avisos_omitidos: 0 }
const RELATORIO_ERRO = { ...RELATORIO_OK, sucesso: false, inseridas: 0, erros: [{ linha: 3, mensagem: 'data inexistente' }] }

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('acessibilidade (axe-core, WCAG)', () => {
  it('login vazio', async () => {
    simularApi()
    renderizarApp('/entrar')
    expect(await violacoes()).toEqual([])
  })

  it('login com erros de campo e do servidor', async () => {
    simularApi({ 'POST /auth/web/login': resposta(401, { detail: 'E-mail ou senha incorretos.' }) })
    renderizarApp('/entrar')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await violacoes()).toEqual([])
    await userEvent.type(screen.getByLabelText('E-mail'), 'gestor@teste.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await screen.findByRole('alert')
    expect(await violacoes()).toEqual([])
  })

  describe('telas autenticadas', () => {
    beforeEach(() => salvarTokens('A1', 'R1'))

    it('importação: vazia, com sucesso e com erros', async () => {
      let relatorio: { status: number; corpo: unknown } = { status: 200, corpo: RELATORIO_OK }
      simularApi({
        'GET /web/me': resposta(200, ME),
        'POST /vendas/importar': () => resposta(relatorio.status, relatorio.corpo),
      })
      renderizarApp('/importar')
      await screen.findByText('Gestor Central Teste')
      expect(await violacoes()).toEqual([])

      const arquivo = new File(['data;codigo_loja;codigo_produto;quantidade\r\n'], 'v.csv', { type: 'text/csv' })
      await userEvent.upload(screen.getByLabelText('Arquivo CSV'), arquivo)
      await userEvent.click(screen.getByRole('button', { name: 'Importar vendas' }))
      await screen.findByRole('heading', { name: '2 linhas importadas' })
      expect(await violacoes()).toEqual([])

      relatorio = { status: 422, corpo: RELATORIO_ERRO }
      await userEvent.click(screen.getByRole('button', { name: 'Importar vendas' }))
      await screen.findByRole('heading', { name: 'Nada foi gravado: 1 erro' })
      expect(await violacoes()).toEqual([])
    })

    it('consulta com dados', async () => {
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /web/lojas': resposta(200, LOJAS),
        'GET /vendas': resposta(200, CONSULTA),
        'GET /perdas': resposta(200, CONSULTA),
      })
      renderizarApp('/consultar')
      await screen.findByRole('table')
      expect(await violacoes()).toEqual([])
    })

    it('previsão com dados (resumo, tabela, conta aberta e qualidade)', async () => {
      const amanha = somarDias(dataIso(new Date()), 1)
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /web/lojas': resposta(200, LOJAS),
        'GET /previsoes': resposta(200, {
          data: amanha,
          itens: [
            itemPrevisao({ data: amanha }),
            itemPrevisao({
              data: amanha,
              produto: { id: 30, codigo: 'INT-030', nome: 'Bolo de Milho' },
              previsao: null,
              previsao_sem_evento: null,
              previsao_propria: null,
              base: null,
              pouco_historico: true,
              peso_historico: '0',
              eventos: [{ id: 3, nome: 'Feriado', tipo_ajuste: 'multiplicador', valor_ajuste: '1.5000' }],
            }),
          ],
          totais: [{ unidade: 'KG', previsto: '44.0000', vendido_semana_passada: '41.500' }],
        }),
        'GET /previsoes/qualidade': resposta(200, {
          data_inicio: '2026-09-16',
          data_fim: '2026-10-13',
          por_unidade: [{ unidade: 'KG', pares: 10, wape: '0.1', vies: '-0.02', ingenuo_wape: '0.08', ingenuo_vies: '0', vence_ingenuo: false }],
        }),
      })
      renderizarApp('/previsao')
      await screen.findByText('Errou em média 10% do volume')
      await screen.findByRole('table')
      expect(await violacoes()).toEqual([])
      await userEvent.click(screen.getByRole('button', { name: 'Ver a conta de Pão Francês na loja 001' }))
      expect(await violacoes()).toEqual([])
    })

    it('previsão vazia e com erro ao gerar', async () => {
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /web/lojas': resposta(200, LOJAS),
        'GET /previsoes': (_init, url) => resposta(200, { data: url.searchParams.get('data'), itens: [], totais: [] }),
        'GET /previsoes/qualidade': resposta(200, { data_inicio: '2026-09-16', data_fim: '2026-10-13', por_unidade: [] }),
        'POST /previsoes/gerar': resposta(500, 'erro'),
      })
      renderizarApp('/previsao')
      await screen.findByText(/^Nenhuma previsão gerada para/)
      await screen.findByText(/^Ainda não há vendas suficientes/)
      expect(await violacoes()).toEqual([])
      await userEvent.click(screen.getByRole('button', { name: 'Gerar previsão' }))
      await screen.findByRole('alert')
      expect(await violacoes()).toEqual([])
    })

    it('ordem de produção em rascunho (lojas, conta e diálogo de ajuste abertos)', async () => {
      const amanha = somarDias(dataIso(new Date()), 1)
      const ordem = ordemDetalhe(amanha)
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /producao/ordens': resposta(200, { data_producao: amanha, ordens: [resumoDe(ordem)] }),
        'GET /producao/ordens/7': resposta(200, ordem),
      })
      renderizarApp('/producao')
      await screen.findByRole('region', { name: 'Resumo da ordem' })
      expect(await violacoes()).toEqual([])
      await userEvent.click(screen.getByRole('button', { name: 'Ver as lojas de Pão Francês' }))
      await userEvent.click(screen.getByRole('button', { name: 'Ver a conta de Pão Francês na loja 001' }))
      expect(await violacoes()).toEqual([])
      await userEvent.click(screen.getByRole('button', { name: 'Ajustar Pão Francês na loja 001' }))
      await screen.findByRole('dialog')
      expect(await violacoes()).toEqual([])
    })

    it('ordem de produção aprovada e dia sem ordem', async () => {
      const amanha = somarDias(dataIso(new Date()), 1)
      const ordem = ordemDetalhe(amanha, { status: 'aprovada', aprovado_em: '2026-10-16T01:00:00', aprovado_por: 'Gestor', linhas_sem_quantidade: 0 })
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /producao/ordens': (_init, url) =>
          resposta(200, { data_producao: url.searchParams.get('data'), ordens: url.searchParams.get('data') === amanha ? [resumoDe(ordem)] : [] }),
        'GET /producao/ordens/7': resposta(200, ordem),
        'GET /producao/setores': resposta(200, [{ id: 1, nome: 'Pães', ordem: 1, ativo: true }]),
      })
      const { unmount } = renderizarApp('/producao')
      await screen.findByText('Ordem aprovada: só leitura.')
      expect(await violacoes()).toEqual([])
      await userEvent.click(screen.getByRole('button', { name: 'Imprimir' }))
      await screen.findByLabelText('Pães')
      expect(await violacoes()).toEqual([])
      unmount()
      renderizarApp(`/producao?data=${somarDias(amanha, 1)}`)
      await screen.findByText(/^Nenhuma ordem gerada para/)
      expect(await violacoes()).toEqual([])
    })

    it('distribuição: sem romaneio (diálogo de produção), rascunho (aprovar bloqueado) e aprovado (itens, saída)', async () => {
      const hoje = dataIso(new Date())
      const rascunho = romaneioDetalhe(hoje)
      rascunho.producao[0] = { ...rascunho.producao[0], total_final: '11.000' }
      const e = entregas()
      e[1] = {
        ...e[1], situacao: { situacao: 'sem_confirmacao', pode_confirmar: true, com_diferenca: false },
        expedido_em: '2026-10-27T09:00:00',
      }
      const aprovado = romaneioDetalhe(hoje, { status: 'aprovado', entregas: e })
      let estado: { ordem: ReturnType<typeof ordemDoDia>; romaneio: typeof rascunho | null } = { ordem: ordemDoDia(hoje), romaneio: null }
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /distribuicao/romaneios': () => resposta(200, { data_entrega: hoje, ordens: [estado.ordem] }),
        'GET /distribuicao/romaneios/30': () => resposta(200, estado.romaneio),
        'GET /distribuicao/divergencias': resposta(200, {
          data_inicio: hoje, data_fim: hoje, totais: [{ unidade: 'UN', enviada: '3.000', recebida: '2.000', diferenca: '-1.000' }],
          divergencias: [{
            data_entrega: hoje, loja: { id: 1, codigo: '001', nome: 'Loja Centro' }, produto: { id: 1, codigo: 'INT-007', nome: 'Pão Francês' },
            unidade: 'UN', quantidade_enviada: '3.000', quantidade_recebida: '2.000', diferenca: '-1.000', motivo: 'falta',
            observacao: null, recebido_em: `${hoje}T13:00:00`,
          }],
        }),
      })
      let tela = renderizarApp('/distribuicao')
      await userEvent.click(await screen.findByRole('button', { name: 'Registrar produção' }))
      await screen.findByRole('dialog')
      expect(await violacoes()).toEqual([])
      tela.unmount()

      estado = { ordem: ordemComRomaneio(rascunho), romaneio: rascunho }
      tela = renderizarApp('/distribuicao')
      await userEvent.click(await screen.findByRole('button', { name: 'Aprovar romaneio' }))
      await screen.findByText(/Mais do que o produzido/)
      expect(await violacoes()).toEqual([])
      tela.unmount()

      estado = { ordem: ordemComRomaneio(aprovado), romaneio: aprovado }
      renderizarApp('/distribuicao')
      await screen.findByRole('table', { name: 'Diferenças no recebimento' })
      await userEvent.click(await screen.findByRole('button', { name: 'Ver os itens da loja 002' }))
      expect(await violacoes()).toEqual([])
      await userEvent.click(screen.getByRole('button', { name: 'Registrar saída' }))
      await screen.findByRole('dialog')
      expect(await violacoes()).toEqual([])
    })

    it('consulta vazia', async () => {
      const vazia = { ...CONSULTA, total: 0, itens: [], totais: [] }
      simularApi({
        'GET /web/me': resposta(200, ME),
        'GET /web/lojas': resposta(200, LOJAS),
        'GET /vendas': resposta(200, vazia),
        'GET /perdas': resposta(200, vazia),
      })
      renderizarApp('/consultar')
      await screen.findByText('Nenhuma venda importada neste período.')
      expect(await violacoes()).toEqual([])
    })
  })
})
