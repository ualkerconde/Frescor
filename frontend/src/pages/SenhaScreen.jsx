import React, { useRef, useState } from 'react'
import { trocarSenha } from '../services/api'
import { BotaoEnviar, Seta, useOnline } from './RecebimentoScreen'
import '../recebimento/recebimento.css'

/**
 * Tela "Trocar senha" do app da loja.
 *
 * Por que existe: o usuário recebe uma senha provisória na implantação
 * (scripts/implantar_cliente.py) e precisa trocá-la pela dele. As regras são
 * as do backend (app/services/senha_service.py): senha atual obrigatória;
 * nova com pelo menos 8 caracteres e diferente da atual. A tela confere o
 * básico antes de enviar (tamanho, repetição igual) e mostra a mensagem do
 * backend para o resto. Só online.
 */

export const TAMANHO_MINIMO = 8

export function errosDaSenha({ atual, nova, repetir }) {
  const erros = {}
  if (!atual) erros.atual = 'Digite a senha atual.'
  if (nova.trim().length === 0) erros.nova = 'Digite a senha nova.'
  else if (nova.length < TAMANHO_MINIMO) erros.nova = `A senha nova precisa ter pelo menos ${TAMANHO_MINIMO} caracteres.`
  else if (nova === atual) erros.nova = 'A senha nova tem de ser diferente da atual.'
  if (!erros.nova && repetir !== nova) erros.repetir = 'As duas senhas novas não são iguais.'
  return erros
}

function Campo({ id, rotulo, valor, erro, autoComplete, onChange }) {
  return (
    <div className={`rcb-campo${erro ? ' rcb-invalido' : ''}`}>
      <label htmlFor={id}>{rotulo}</label>
      <div className="rcb-entrada">
        <input id={id} type="password" autoComplete={autoComplete} value={valor} style={{ maxWidth: 'none', textAlign: 'left' }}
          aria-invalid={erro ? true : undefined} aria-describedby={erro ? `${id}-erro` : undefined}
          onChange={(e) => onChange(e.target.value)} />
      </div>
      {erro && <p id={`${id}-erro`} className="rcb-erro-campo">⚠ {erro}</p>}
    </div>
  )
}

export function SenhaScreen({ onVoltar, onLogout }) {
  const online = useOnline()
  const [campos, setCampos] = useState({ atual: '', nova: '', repetir: '' })
  const [mostrarErros, setMostrarErros] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erroEnvio, setErroEnvio] = useState(null)
  const [trocada, setTrocada] = useState(false)
  const enviandoRef = useRef(false)

  const erros = mostrarErros ? errosDaSenha(campos) : {}
  const mudar = (parte) => { setCampos((c) => ({ ...c, ...parte })); setErroEnvio(null) }

  async function salvar() {
    if (enviandoRef.current) return
    setMostrarErros(true)
    if (Object.keys(errosDaSenha(campos)).length > 0) return
    enviandoRef.current = true
    setEnviando(true)
    try {
      await trocarSenha(campos.atual, campos.nova)
      setTrocada(true)
      setCampos({ atual: '', nova: '', repetir: '' })
      setMostrarErros(false)
    } catch (e) {
      if (e.message === 'SESSION_EXPIRED') { onLogout(); return }
      setErroEnvio(e.message === 'SEM_CONEXAO'
        ? 'Sem internet. A troca de senha precisa de conexão: conecte o celular e tente de novo.'
        : e.message)
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  return (
    <div className="rcb">
      <header className="rcb-cabecalho">
        <button type="button" className="rcb-voltar" onClick={onVoltar}><Seta />Contagem</button>
        <h1>Trocar senha</h1>
      </header>
      <main className="rcb-corpo rcb-corpo-com-rodape">
        {!online && <div className="rcb-alerta rcb-alerta-aviso" role="status">Sem internet. Conecte o celular para trocar a senha.</div>}
        {trocada && (
          <div className="rcb-alerta rcb-alerta-sucesso" role="status">
            Senha trocada. Use a senha nova no próximo login.
          </div>
        )}
        {erroEnvio && <div className="rcb-alerta rcb-alerta-erro" role="alert">{erroEnvio}</div>}
        <Campo id="snh-atual" rotulo="Senha atual" valor={campos.atual} erro={erros.atual} autoComplete="current-password"
          onChange={(v) => mudar({ atual: v })} />
        <Campo id="snh-nova" rotulo={`Senha nova (pelo menos ${TAMANHO_MINIMO} caracteres)`} valor={campos.nova}
          erro={erros.nova} autoComplete="new-password" onChange={(v) => mudar({ nova: v })} />
        <Campo id="snh-repetir" rotulo="Repita a senha nova" valor={campos.repetir} erro={erros.repetir}
          autoComplete="new-password" onChange={(v) => mudar({ repetir: v })} />
      </main>
      <footer className="rcb-rodape">
        <BotaoEnviar enviando={enviando} rotulo="Trocar senha" rotuloEnviando="Trocando…" disabled={!online || enviando}
          onClick={salvar} />
      </footer>
    </div>
  )
}
