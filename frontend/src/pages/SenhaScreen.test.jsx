import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SenhaScreen, errosDaSenha } from './SenhaScreen'
import { Drawer } from '../components/Drawer'
import { mockFetch, resposta } from '../test/recebimento'

const TROCAR = 'POST /auth/senha'

function montar() {
  const onVoltar = vi.fn()
  const onLogout = vi.fn()
  render(<SenhaScreen onVoltar={onVoltar} onLogout={onLogout} />)
  return { onVoltar, onLogout, user: userEvent.setup() }
}

async function preencher(user, atual, nova, repetir = nova) {
  await user.type(screen.getByLabelText('Senha atual'), atual)
  await user.type(screen.getByLabelText(/Senha nova \(pelo menos/), nova)
  await user.type(screen.getByLabelText('Repita a senha nova'), repetir)
}

beforeEach(() => {
  localStorage.setItem('access_token', 'token-de-teste')
})

describe('Trocar senha', () => {
  it('regras locais: atual vazia, curta, igual à atual, repetição diferente', () => {
    expect(errosDaSenha({ atual: '', nova: 'abcdefgh', repetir: 'abcdefgh' }).atual).toBeTruthy()
    expect(errosDaSenha({ atual: 'x', nova: 'curta', repetir: 'curta' }).nova).toMatch(/8 caracteres/)
    expect(errosDaSenha({ atual: 'abcdefgh', nova: 'abcdefgh', repetir: 'abcdefgh' }).nova).toMatch(/diferente/)
    expect(errosDaSenha({ atual: 'x', nova: 'abcdefgh', repetir: 'abcdefgX' }).repetir).toMatch(/não são iguais/)
    expect(errosDaSenha({ atual: 'x', nova: 'abcdefgh', repetir: 'abcdefgh' })).toEqual({})
  })

  it('envia senha atual e nova e mostra o sucesso', async () => {
    const api = mockFetch({ [TROCAR]: () => resposta(204) })
    const { user } = montar()
    await preencher(user, 'antiga123', 'novasenha1')
    await user.click(screen.getByRole('button', { name: 'Trocar senha' }))
    expect(await screen.findByText(/Senha trocada/)).toBeInTheDocument()
    expect(api.de(TROCAR)[0].corpo).toEqual({ senha_atual: 'antiga123', senha_nova: 'novasenha1' })
    expect(screen.getByLabelText('Senha atual')).toHaveValue('')
  })

  it('erro de regra local não chama a API', async () => {
    const api = mockFetch({ [TROCAR]: () => resposta(204) })
    const { user } = montar()
    await preencher(user, 'antiga123', 'novasenha1', 'outra-coisa')
    await user.click(screen.getByRole('button', { name: 'Trocar senha' }))
    expect(await screen.findByText(/não são iguais/)).toBeInTheDocument()
    expect(api.de(TROCAR)).toHaveLength(0)
  })

  it('senha atual errada: mostra a mensagem do backend', async () => {
    mockFetch({ [TROCAR]: () => resposta(400, { detail: 'A senha atual não confere.' }) })
    const { user } = montar()
    await preencher(user, 'errada999', 'novasenha1')
    await user.click(screen.getByRole('button', { name: 'Trocar senha' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A senha atual não confere.')
  })

  it('o menu tem "Trocar senha"', async () => {
    const onAbrirSenha = vi.fn()
    render(<Drawer aberto onClose={() => {}} onLogout={() => {}} onAbrirSenha={onAbrirSenha} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Trocar senha' }))
    expect(onAbrirSenha).toHaveBeenCalled()
  })
})
