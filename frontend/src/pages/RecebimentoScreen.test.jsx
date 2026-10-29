import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RecebimentoScreen } from './RecebimentoScreen'
import { Drawer } from '../components/Drawer'
import { entrega, mockFetch, resposta } from '../test/recebimento'

const CONFIRMAR = 'POST /recebimentos/10/confirmar'

function montar(props = {}) {
  const onVoltar = vi.fn()
  const onLogout = vi.fn()
  render(<RecebimentoScreen onVoltar={onVoltar} onLogout={onLogout} {...props} />)
  return { onVoltar, onLogout, user: userEvent.setup() }
}

async function abrirEntrega(user) {
  await user.click(await screen.findByRole('button', { name: /Entrega de 28\/10/ }))
}

function semInternet() {
  vi.spyOn(Navigator.prototype, 'onLine', 'get').mockReturnValue(false)
}

beforeEach(() => {
  localStorage.setItem('access_token', 'token-de-teste')
})

describe('Recebimento: lista', () => {
  it('estado vazio explica o que aparece ali e oferece atualizar', async () => {
    const api = mockFetch({ 'GET /recebimentos': () => resposta(200, []) })
    const { user } = montar()
    expect(await screen.findByText(/Nenhuma entrega para confirmar/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(api.de('GET /recebimentos')).toHaveLength(2))
  })

  it('mostra a entrega com a saída, o número de produtos e a situação', async () => {
    mockFetch({ 'GET /recebimentos': () => resposta(200, [entrega()]) })
    montar()
    const card = await screen.findByRole('button', { name: /Entrega de 28\/10/ })
    expect(card).toHaveTextContent('2 produtos')
    expect(card).toHaveTextContent('A caminho')
    expect(card).toHaveTextContent(/Saiu da central às \d\d:\d\d/)
  })

  it('entrega do dia anterior aparece como sem confirmação, com o prazo', async () => {
    mockFetch({
      'GET /recebimentos': () => resposta(200, [
        entrega({ situacao: { situacao: 'sem_confirmacao', pode_confirmar: true, com_diferenca: false } }),
      ]),
    })
    montar()
    const card = await screen.findByRole('button', { name: /Entrega de 28\/10/ })
    expect(card).toHaveTextContent('Sem confirmação')
    expect(card).toHaveTextContent('Confirme até o fim de hoje.')
  })

  it('voltar leva para a contagem', async () => {
    mockFetch({ 'GET /recebimentos': () => resposta(200, []) })
    const { user, onVoltar } = montar()
    await user.click(screen.getByRole('button', { name: /Contagem/ }))
    expect(onVoltar).toHaveBeenCalled()
  })
})

describe('Recebimento: tudo certo', () => {
  it('"Recebi tudo certo" pede confirmação e envia sem diferenças', async () => {
    const api = mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => resposta(200, entrega({ situacao: { situacao: 'recebida', pode_confirmar: false, com_diferenca: false } })),
    })
    const { user } = montar()
    await abrirEntrega(user)
    expect(screen.getByText('18,2 kg')).toBeInTheDocument()
    expect(screen.getByText('24 un')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    expect(api.de(CONFIRMAR)).toHaveLength(0)
    const dialogo = screen.getByRole('dialog', { name: 'Chegou tudo certo?' })
    expect(dialogo).toHaveTextContent('não dá para alterar')
    await user.click(within(dialogo).getByRole('button', { name: 'Confirmar recebimento' }))

    expect(await screen.findByText(/confirmado: chegou tudo certo/)).toBeInTheDocument()
    expect(api.de(CONFIRMAR)).toEqual([{ chave: CONFIRMAR, corpo: { diferencas: [] } }])
    expect(screen.queryByRole('button', { name: /Entrega de 28\/10/ })).not.toBeInTheDocument()
  })

  it('"Voltar" no diálogo não envia nada', async () => {
    const api = mockFetch({ 'GET /recebimentos': () => resposta(200, [entrega()]) })
    const { user } = montar()
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Voltar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.de(CONFIRMAR)).toHaveLength(0)
  })

  it('não envia duas vezes: o botão mostra "Enviando…" e fica bloqueado', async () => {
    let liberar
    const api = mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => new Promise((r) => { liberar = () => r(new Response(JSON.stringify(entrega()), { status: 200 })) }),
    })
    const { user } = montar()
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    const botao = within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmar recebimento' })
    await user.click(botao)
    const enviando = within(screen.getByRole('dialog')).getByRole('button', { name: 'Enviando…' })
    expect(enviando).toBeDisabled()
    await user.click(enviando)
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Voltar' })).toBeDisabled()
    expect(api.de(CONFIRMAR)).toHaveLength(1)
    liberar()
    expect(await screen.findByText(/confirmado: chegou tudo certo/)).toBeInTheDocument()
    expect(api.de(CONFIRMAR)).toHaveLength(1)
  })
})

describe('Recebimento: com diferença', () => {
  async function abrirDiferenca(user) {
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi com diferença' }))
  }

  it('diferença sem motivo não é enviada; com motivo, envia só o item diferente', async () => {
    const api = mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => resposta(200, entrega()),
    })
    const { user } = montar()
    await abrirDiferenca(user)
    const campo = screen.getByLabelText('Chegou (kg)')
    expect(campo).toHaveValue('18,2')
    await user.clear(campo)
    await user.type(campo, '16,5')

    await user.click(screen.getByRole('button', { name: 'Enviar recebimento' }))
    expect(campo).toHaveAccessibleDescription(/Chegou diferente do enviado: escolha o motivo/)
    expect(screen.getByRole('alert')).toHaveTextContent('Confira os produtos marcados')
    expect(campo).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.de(CONFIRMAR)).toHaveLength(0)

    await user.click(screen.getByRole('radio', { name: 'Faltou' }))
    await user.click(screen.getByRole('button', { name: 'Enviar recebimento' }))
    const dialogo = screen.getByRole('dialog', { name: /com diferença/ })
    expect(dialogo).toHaveTextContent('Pão Francês: enviado 18,2 kg, chegou 16,5 kg (Faltou)')
    await user.click(within(dialogo).getByRole('button', { name: 'Enviar recebimento' }))

    expect(await screen.findByText(/confirmado com diferença em 1 produto/)).toBeInTheDocument()
    expect(api.de(CONFIRMAR)[0].corpo).toEqual({
      diferencas: [{ item_id: 101, quantidade_recebida: '16.5', motivo: 'falta', observacao: null }],
    })
  })

  it('motivo "Outro" exige a descrição', async () => {
    const api = mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => resposta(200, entrega()),
    })
    const { user } = montar()
    await abrirDiferenca(user)
    const campo = screen.getByLabelText('Chegou (un)')
    await user.clear(campo)
    await user.type(campo, '26')
    await user.click(screen.getByRole('radio', { name: 'Outro' }))
    await user.click(screen.getByRole('button', { name: 'Enviar recebimento' }))
    expect(screen.getByText(/descreva o que aconteceu/)).toBeInTheDocument()
    expect(api.de(CONFIRMAR)).toHaveLength(0)

    await user.type(screen.getByLabelText('O que aconteceu?'), 'Veio caixa trocada')
    await user.click(screen.getByRole('button', { name: 'Enviar recebimento' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Enviar recebimento' }))
    await screen.findByText(/confirmado com diferença/)
    expect(api.de(CONFIRMAR)[0].corpo.diferencas).toEqual([
      { item_id: 102, quantidade_recebida: '26', motivo: 'outro', observacao: 'Veio caixa trocada' },
    ])
  })

  it('produto por unidade não aceita número quebrado', async () => {
    mockFetch({ 'GET /recebimentos': () => resposta(200, [entrega()]) })
    const { user } = montar()
    await abrirDiferenca(user)
    const campo = screen.getByLabelText('Chegou (un)')
    await user.clear(campo)
    await user.type(campo, '20,5')
    await user.click(screen.getByRole('radio', { name: 'Avaria' }))
    await user.click(screen.getByRole('button', { name: 'Enviar recebimento' }))
    expect(screen.getByText(/informe um número inteiro/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('sem nenhum produto diferente, orienta usar "Recebi tudo certo"', async () => {
    const api = mockFetch({ 'GET /recebimentos': () => resposta(200, [entrega()]) })
    const { user } = montar()
    await abrirDiferenca(user)
    await user.click(screen.getByRole('button', { name: 'Enviar recebimento' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/Nenhum produto ficou diferente/)
    expect(api.de(CONFIRMAR)).toHaveLength(0)
  })

  it('"Cancelar diferença" volta ao enviado', async () => {
    mockFetch({ 'GET /recebimentos': () => resposta(200, [entrega()]) })
    const { user } = montar()
    await abrirDiferenca(user)
    await user.clear(screen.getByLabelText('Chegou (kg)'))
    await user.type(screen.getByLabelText('Chegou (kg)'), '10')
    await user.click(screen.getByRole('button', { name: 'Cancelar diferença' }))
    await user.click(screen.getByRole('button', { name: 'Recebi com diferença' }))
    expect(screen.getByLabelText('Chegou (kg)')).toHaveValue('18,2')
  })
})

describe('Recebimento: conexão e erros', () => {
  it('sem conexão ao abrir: explica que precisa de internet', async () => {
    semInternet()
    mockFetch({ 'GET /recebimentos': () => Promise.reject(new TypeError('Failed to fetch')) })
    montar()
    expect(await screen.findByText(/Sem internet\. A confirmação do recebimento precisa de conexão/)).toBeInTheDocument()
  })

  it('sem conexão com a entrega aberta: confirmar fica bloqueado', async () => {
    mockFetch({ 'GET /recebimentos': () => resposta(200, [entrega()]) })
    const { user } = montar()
    await abrirEntrega(user)
    semInternet()
    window.dispatchEvent(new Event('offline'))
    expect(await screen.findByText(/Sem internet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recebi tudo certo' })).toBeDisabled()
  })

  it('a rede cai durante o envio: mostra a mensagem e deixa tentar de novo', async () => {
    mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => Promise.reject(new TypeError('Failed to fetch')),
    })
    const { user } = montar()
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    const dialogo = screen.getByRole('dialog')
    await user.click(within(dialogo).getByRole('button', { name: 'Confirmar recebimento' }))
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(/Sem internet/)
    expect(within(dialogo).getByRole('button', { name: 'Confirmar recebimento' })).toBeEnabled()
  })

  it('erro do servidor aparece em português, sem o código', async () => {
    mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => resposta(422, { detail: 'Pão Francês: informe no máximo 3 casas decimais.' }),
    })
    const { user } = montar()
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    const dialogo = screen.getByRole('dialog')
    await user.click(within(dialogo).getByRole('button', { name: 'Confirmar recebimento' }))
    const alerta = await within(dialogo).findByRole('alert')
    expect(alerta).toHaveTextContent('Pão Francês: informe no máximo 3 casas decimais.')
    expect(document.body.textContent).not.toMatch(/422|Erro \d/)
  })

  it('erro sem texto do servidor vira mensagem genérica, sem código', async () => {
    mockFetch({
      'GET /recebimentos': () => resposta(200, [entrega()]),
      [CONFIRMAR]: () => resposta(500, {}),
    })
    const { user } = montar()
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    const dialogo = screen.getByRole('dialog')
    await user.click(within(dialogo).getByRole('button', { name: 'Confirmar recebimento' }))
    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Não foi possível concluir')
    expect(document.body.textContent).not.toMatch(/500/)
  })

  it('entrega já confirmada (409): volta para a lista atualizada com a explicação', async () => {
    const api = mockFetch({
      'GET /recebimentos': [() => resposta(200, [entrega()]), () => resposta(200, [])],
      [CONFIRMAR]: () => resposta(409, { detail: 'Esta entrega já foi confirmada e não pode ser alterada.' }),
    })
    const { user } = montar()
    await abrirEntrega(user)
    await user.click(screen.getByRole('button', { name: 'Recebi tudo certo' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmar recebimento' }))
    expect(await screen.findByText('Esta entrega já foi confirmada e não pode ser alterada.')).toBeInTheDocument()
    expect(screen.getByText(/Nenhuma entrega para confirmar/)).toBeInTheDocument()
    expect(api.de('GET /recebimentos')).toHaveLength(2)
  })

  it('sessão expirada leva ao login', async () => {
    mockFetch({
      'GET /recebimentos': () => resposta(401, { detail: 'Token inválido.' }),
    })
    const { onLogout } = montar()
    await waitFor(() => expect(onLogout).toHaveBeenCalled())
  })
})

describe('Menu do app', () => {
  it('tem o item "Recebimento" ao lado de "Sair"', async () => {
    const onAbrirRecebimento = vi.fn()
    const user = userEvent.setup()
    render(<Drawer aberto onClose={() => {}} onLogout={() => {}} onAbrirRecebimento={onAbrirRecebimento} />)
    await user.click(screen.getByRole('button', { name: 'Recebimento' }))
    expect(onAbrirRecebimento).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Sair' })).toBeInTheDocument()
  })
})
