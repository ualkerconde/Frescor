// Montadores de dados e mock de fetch para os testes do Recebimento.
import { vi } from 'vitest'

export function entrega(extra = {}) {
  return {
    id: 10,
    data_entrega: '2026-10-28',
    expedido_em: '2026-10-28T09:15:00',
    recebido_em: null,
    situacao: { situacao: 'a_caminho', pode_confirmar: true, com_diferenca: false },
    itens: [
      {
        id: 101, produto: { id: 1, codigo: 'PRD-01', nome: 'Pão Francês' }, unidade: 'KG',
        quantidade_expedida: '18.200', quantidade_recebida: null, motivo_divergencia: null, observacao_divergencia: null,
      },
      {
        id: 102, produto: { id: 2, codigo: 'PRD-02', nome: 'Bolo de Cenoura' }, unidade: 'UN',
        quantidade_expedida: '24.000', quantidade_recebida: null, motivo_divergencia: null, observacao_divergencia: null,
      },
    ],
    ...extra,
  }
}

export function resposta(status, corpo) {
  return Promise.resolve(new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } }))
}

/**
 * Mock de fetch por rota. `rotas` = { 'GET /recebimentos': fn | valor, 'POST /recebimentos/10/confirmar': ... }.
 * Cada valor é uma função (init) => Promise<Response> ou uma lista delas (uma por chamada).
 */
export function mockFetch(rotas) {
  const chamadas = []
  const fn = vi.fn((url, init = {}) => {
    const metodo = init.method ?? 'GET'
    const caminho = new URL(url, 'http://x').pathname
    const chave = `${metodo} ${caminho}`
    chamadas.push({ chave, corpo: init.body ? JSON.parse(init.body) : undefined })
    let r = rotas[chave]
    if (Array.isArray(r)) r = r.length > 1 ? r.shift() : r[0]
    if (!r) return resposta(500, { detail: `rota sem mock: ${chave}` })
    return r(init)
  })
  vi.stubGlobal('fetch', fn)
  return { fn, chamadas, de: (chave) => chamadas.filter((c) => c.chave === chave) }
}
