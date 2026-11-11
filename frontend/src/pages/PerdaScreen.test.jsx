import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PerdaScreen } from './PerdaScreen'
import { Drawer } from '../components/Drawer'
import { mockFetch, resposta } from '../test/recebimento'
import { diaLocal } from '../perda/regras'

const HOJE = diaLocal(0)
const ONTEM = diaLocal(-1)
const LISTA = 'GET /perdas/lancamentos'
const LANCAR = 'POST /perdas/lancamentos'

function produtos() {
  return [
    { id: 1, nome: 'Pão Francês', codigo: 'PRD-01', codigo_barras: null, unidade_medida: 'KG' },
    { id: 2, nome: 'Bolo de Cenoura', codigo: 'PRD-02', codigo_barras: '7890000000002', unidade_medida: 'UN' },
  ]
}

function lancamento(extra = {}) {
  return {
    id: 50, data: HOJE, loja: { id: 1, codigo: 'L1', nome: 'Loja 1' },
    produto: { id: 2, codigo: 'PRD-02', nome: 'Bolo de Cenoura' }, unidade: 'UN', quantidade: '3.000',
    motivo: 'vencido', observacao: null, lancado_por: 'Ana', lancado_em: '2026-11-11T12:30:00',
    alterado_por: null, alterado_em: null, loja_pode_alterar: true,
    ...extra,
  }
}

function montar() {
  const onVoltar = vi.fn()
  const onLogout = vi.fn()
  render(<PerdaScreen onVoltar={onVoltar} onLogout={onLogout} />)
  return { onVoltar, onLogout, user: userEvent.setup() }
}

beforeEach(() => {
  localStorage.setItem('access_token', 'token-de-teste')
})

describe('Perda: lista', () => {
  it('estado vazio explica para que serve', async () => {
    mockFetch({ [LISTA]: () => resposta(200, []) })
    montar()
    expect(await screen.findByText(/Nenhuma perda lançada hoje nem ontem/)).toBeInTheDocument()
  })

  it('separa hoje e ontem e mostra quantidade, motivo e quem lançou', async () => {
    mockFetch({
      [LISTA]: () => resposta(200, [
        lancamento(),
        lancamento({ id: 51, data: ONTEM, produto: { id: 1, codigo: 'PRD-01', nome: 'Pão Francês' }, unidade: 'KG',
          quantidade: '1.500', motivo: 'outro', observacao: 'caiu no chão' }),
      ]),
    })
    montar()
    const hoje = await screen.findByRole('region', { name: /^Hoje/ })
    expect(within(hoje).getByText('3 un')).toBeInTheDocument()
    expect(within(hoje).getByText('Vencido')).toBeInTheDocument()
    expect(within(hoje).getByText(/Ana às \d\d:\d\d/)).toBeInTheDocument()
    const ontem = screen.getByRole('region', { name: /^Ontem/ })
    expect(within(ontem).getByText('1,5 kg')).toBeInTheDocument()
    expect(within(ontem).getByText('Outro: caiu no chão')).toBeInTheDocument()
  })

  it('erro de sessão leva ao login', async () => {
    mockFetch({ [LISTA]: () => resposta(401, { detail: 'expirou' }), 'POST /auth/refresh': () => resposta(401, {}) })
    const { onLogout } = montar()
    await waitFor(() => expect(onLogout).toHaveBeenCalled())
  })
})

describe('Perda: lançar', () => {
  it('busca o produto sem acento, valida e envia o dia, a quantidade e o motivo', async () => {
    const api = mockFetch({
      [LISTA]: [() => resposta(200, []), () => resposta(200, [lancamento()])],
      'GET /produtos': () => resposta(200, produtos()),
      [LANCAR]: () => resposta(201, lancamento()),
    })
    const { user } = montar()
    await user.click(await screen.findByRole('button', { name: 'Lançar perda' }))
    await user.type(await screen.findByLabelText('Qual produto foi perdido?'), 'cenoura')
    expect(screen.queryByRole('button', { name: /Pão Francês/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Bolo de Cenoura/ }))

    // Sem nada preenchido: avisa e não envia.
    await user.click(screen.getByRole('button', { name: 'Lançar perda' }))
    expect(screen.getByText(/Informe quanto foi perdido/)).toBeInTheDocument()
    expect(screen.getByText(/Escolha o motivo/)).toBeInTheDocument()
    expect(api.de(LANCAR)).toHaveLength(0)

    // Unidade: só inteiro.
    await user.type(screen.getByLabelText('Quantidade perdida (un)'), '2,5')
    await user.click(screen.getByRole('radio', { name: 'Vencido' }))
    await user.click(screen.getByRole('button', { name: 'Lançar perda' }))
    expect(screen.getByText(/informe um número inteiro/)).toBeInTheDocument()
    expect(api.de(LANCAR)).toHaveLength(0)

    await user.clear(screen.getByLabelText('Quantidade perdida (un)'))
    await user.type(screen.getByLabelText('Quantidade perdida (un)'), '3')
    await user.click(screen.getByRole('radio', { name: /^Ontem/ }))
    await user.click(screen.getByRole('button', { name: 'Lançar perda' }))

    await waitFor(() => expect(api.de(LANCAR)).toHaveLength(1))
    expect(api.de(LANCAR)[0].corpo).toEqual({ produto_id: 2, quantidade: '3', motivo: 'vencido', observacao: null, data: ONTEM })
    expect(await screen.findByText('Perda lançada. Bolo de Cenoura: 3 un.')).toBeInTheDocument()
    expect(api.de(LISTA)).toHaveLength(2)
  })

  it('motivo "Outro" pede o que aconteceu', async () => {
    const api = mockFetch({
      [LISTA]: () => resposta(200, []),
      'GET /produtos': () => resposta(200, produtos()),
      [LANCAR]: () => resposta(201, lancamento()),
    })
    const { user } = montar()
    await user.click(await screen.findByRole('button', { name: 'Lançar perda' }))
    await user.click(await screen.findByRole('button', { name: /Pão Francês/ }))
    await user.type(screen.getByLabelText('Quantidade perdida (kg)'), '1,25')
    await user.click(screen.getByRole('radio', { name: 'Outro' }))
    await user.click(screen.getByRole('button', { name: 'Lançar perda' }))
    expect(screen.getByText(/escreva numa linha o que aconteceu/)).toBeInTheDocument()
    expect(api.de(LANCAR)).toHaveLength(0)
    await user.type(screen.getByLabelText('O que aconteceu?'), 'Forno queimou')
    await user.click(screen.getByRole('button', { name: 'Lançar perda' }))
    await waitFor(() => expect(api.de(LANCAR)).toHaveLength(1))
    expect(api.de(LANCAR)[0].corpo).toMatchObject({ produto_id: 1, quantidade: '1.25', motivo: 'outro', observacao: 'Forno queimou', data: HOJE })
  })

  it('mostra o erro do backend em português e não fecha o formulário', async () => {
    mockFetch({
      [LISTA]: () => resposta(200, []),
      'GET /produtos': () => resposta(200, produtos()),
      [LANCAR]: () => resposta(422, { detail: 'Este produto está desativado.' }),
    })
    const { user } = montar()
    await user.click(await screen.findByRole('button', { name: 'Lançar perda' }))
    await user.click(await screen.findByRole('button', { name: /Bolo de Cenoura/ }))
    await user.type(screen.getByLabelText('Quantidade perdida (un)'), '1')
    await user.click(screen.getByRole('radio', { name: 'Avariado' }))
    await user.click(screen.getByRole('button', { name: 'Lançar perda' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Este produto está desativado.')
    expect(screen.getByRole('heading', { name: 'Lançar perda' })).toBeInTheDocument()
  })
})

describe('Perda: corrigir e apagar', () => {
  it('corrige quantidade e motivo, sem trocar produto nem dia', async () => {
    const api = mockFetch({
      [LISTA]: () => resposta(200, [lancamento()]),
      'PUT /perdas/lancamentos/50': () => resposta(200, lancamento({ quantidade: '4.000' })),
    })
    const { user } = montar()
    await user.click(await screen.findByRole('button', { name: /Bolo de Cenoura/ }))
    expect(screen.getByRole('heading', { name: 'Corrigir perda' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Trocar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /^Hoje/ })).not.toBeInTheDocument()
    const campo = screen.getByLabelText('Quantidade perdida (un)')
    expect(campo).toHaveValue('3')
    await user.clear(campo)
    await user.type(campo, '4')
    await user.click(screen.getByRole('radio', { name: 'Avariado' }))
    await user.click(screen.getByRole('button', { name: 'Salvar correção' }))
    await waitFor(() => expect(api.de('PUT /perdas/lancamentos/50')).toHaveLength(1))
    expect(api.de('PUT /perdas/lancamentos/50')[0].corpo).toEqual({ quantidade: '4', motivo: 'avariado', observacao: null })
  })

  it('apagar pede confirmação', async () => {
    const api = mockFetch({
      [LISTA]: [() => resposta(200, [lancamento()]), () => resposta(200, [])],
      'DELETE /perdas/lancamentos/50': () => Promise.resolve(new Response(null, { status: 204 })),
    })
    const { user } = montar()
    await user.click(await screen.findByRole('button', { name: /Bolo de Cenoura/ }))
    await user.click(screen.getByRole('button', { name: 'Apagar lançamento' }))
    const dialogo = screen.getByRole('dialog', { name: 'Apagar este lançamento?' })
    expect(api.de('DELETE /perdas/lancamentos/50')).toHaveLength(0)
    await user.click(within(dialogo).getByRole('button', { name: 'Apagar lançamento' }))
    await waitFor(() => expect(api.de('DELETE /perdas/lancamentos/50')).toHaveLength(1))
    expect(await screen.findByText(/Lançamento apagado/)).toBeInTheDocument()
    expect(await screen.findByText(/Nenhuma perda lançada/)).toBeInTheDocument()
  })

  it('prazo encerrado (409) volta para a lista com o motivo', async () => {
    mockFetch({
      [LISTA]: () => resposta(200, [lancamento()]),
      'PUT /perdas/lancamentos/50': () => resposta(409, { detail: 'O prazo da loja para corrigir acabou.' }),
    })
    const { user } = montar()
    await user.click(await screen.findByRole('button', { name: /Bolo de Cenoura/ }))
    await user.click(screen.getByRole('button', { name: 'Salvar correção' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('O prazo da loja para corrigir acabou.')
    expect(screen.getByRole('heading', { name: 'Perda' })).toBeInTheDocument()
  })

  it('lançamento fora do prazo da loja não abre para edição', async () => {
    mockFetch({ [LISTA]: () => resposta(200, [lancamento({ loja_pode_alterar: false })]) })
    montar()
    expect(await screen.findByText(/só o gestor corrige/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Bolo de Cenoura/ })).not.toBeInTheDocument()
  })
})

describe('Perda: menu', () => {
  it('o menu abre a tela de perda', async () => {
    const onAbrirPerda = vi.fn()
    const user = userEvent.setup()
    render(<Drawer aberto onClose={() => {}} onLogout={() => {}} onAbrirPerda={onAbrirPerda} />)
    await user.click(screen.getByRole('button', { name: 'Perda' }))
    expect(onAbrirPerda).toHaveBeenCalled()
  })
})
