import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { salvarTokens } from '@/lib/api/sessao'
import { ME, renderizarApp, resposta, simularApi } from '@/test/renderizar'
import { errosDaSenha } from './Senha'

/* Trocar senha do gestor (POST /auth/web/senha). */

async function violacoes(): Promise<string[]> {
  const resultado = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } })
  return resultado.violations.map((v) => `${v.id}: ${v.help}`)
}

beforeEach(() => {
  localStorage.clear()
  salvarTokens('access', 'refresh')
})
afterEach(() => vi.unstubAllGlobals())

async function preencher(atual: string, nova: string, repetir = nova) {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Senha atual'), atual)
  await user.type(screen.getByLabelText(/Senha nova \(pelo menos/), nova)
  await user.type(screen.getByLabelText('Repita a senha nova'), repetir)
  await user.click(screen.getByRole('button', { name: 'Trocar senha' }))
}

describe('trocar senha', () => {
  it('regras locais', () => {
    expect(errosDaSenha({ atual: '', nova: 'abcdefgh', repetir: 'abcdefgh' }).atual).toBeTruthy()
    expect(errosDaSenha({ atual: 'x', nova: 'curta', repetir: 'curta' }).nova).toMatch(/8 caracteres/)
    expect(errosDaSenha({ atual: 'abcdefgh', nova: 'abcdefgh', repetir: 'abcdefgh' }).nova).toMatch(/diferente/)
    expect(errosDaSenha({ atual: 'x', nova: 'abcdefgh', repetir: 'outra123' }).repetir).toMatch(/não são iguais/)
  })

  it('o rodapé da barra leva à tela, que envia e confirma; sem violações de acessibilidade', async () => {
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /auth/web/senha': () => new Response(null, { status: 204 }),
    })
    renderizarApp('/senha')
    expect(within(screen.getByRole('banner')).getByRole('link', { name: 'Trocar senha' })).toHaveAttribute('href', '/senha')
    await screen.findByRole('heading', { name: 'Trocar senha', level: 1 })
    expect(await violacoes()).toEqual([])
    await preencher('antiga123', 'novasenha1')
    expect(await screen.findByText(/Senha trocada/)).toBeInTheDocument()
    const chamada = fetch.mock.calls.find(([url]) => String(url).includes('/auth/web/senha'))
    expect(JSON.parse(String(chamada?.[1]?.body))).toEqual({ senha_atual: 'antiga123', senha_nova: 'novasenha1' })
  })

  it('senha atual errada: mostra a mensagem do backend; repetição diferente não chama a API', async () => {
    const fetch = simularApi({
      'GET /web/me': resposta(200, ME),
      'POST /auth/web/senha': resposta(400, { detail: 'A senha atual não confere.' }),
    })
    renderizarApp('/senha')
    await preencher('antiga123', 'novasenha1', 'diferente1')
    expect(await screen.findByText('As duas senhas novas não são iguais.')).toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/auth/web/senha'))).toBe(false)
    await userEvent.setup().clear(screen.getByLabelText('Repita a senha nova'))
    await userEvent.setup().type(screen.getByLabelText('Repita a senha nova'), 'novasenha1')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Trocar senha' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A senha atual não confere.')
  })
})
