import React, { useState } from 'react'
import { login, saveTokens } from '../services/api'

const s = {
  wrap: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    padding: '32px 24px',
    minHeight: '100vh',
  },
  logo: { marginBottom: 40 },
  logoTitle: { fontSize: 22, fontWeight: 600, color: '#1A1A1A', letterSpacing: '-0.5px' },
  logoSub: { fontSize: 14, color: '#6B6B6B', marginTop: 4 },
  field: { marginBottom: 16 },
  label: { display: 'block', fontSize: 13, fontWeight: 500, color: '#6B6B6B', marginBottom: 6 },
  input: {
    width: '100%',
    padding: '13px 14px',
    border: '1.5px solid #E5E5E5',
    borderRadius: 10,
    fontSize: 16,
    fontFamily: 'inherit',
    background: '#fff',
    color: '#1A1A1A',
    outline: 'none',
    transition: 'border-color 0.15s',
  },
  inputFocus: { borderColor: '#2563EB' },
  error: { fontSize: 13, color: '#DC2626', marginTop: 8, textAlign: 'center', minHeight: 20 },
  btn: {
    width: '100%',
    padding: 14,
    background: '#2563EB',
    color: '#fff',
    border: 'none',
    borderRadius: 10,
    fontSize: 16,
    fontWeight: 600,
    fontFamily: 'inherit',
    cursor: 'pointer',
    marginTop: 8,
    transition: 'background 0.15s',
  },
  btnDisabled: { background: '#93B4F0', cursor: 'not-allowed' },
}

export function LoginScreen({ onLoginSuccess }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState('')
  const [loading, setLoading] = useState(false)
  const [emailFocused, setEmailFocused] = useState(false)
  const [senhaFocused, setSenhaFocused] = useState(false)

  async function handleLogin() {
    setErro('')
    if (!email.trim() || !senha) { setErro('Preencha e-mail e senha.'); return }
    setLoading(true)
    try {
      const data = await login(email.trim(), senha)
      saveTokens(data.access_token, data.refresh_token)
      onLoginSuccess()
    } catch (e) {
      setErro(e.message || 'Erro ao fazer login.')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleLogin()
  }

  return (
    <div style={s.wrap}>
      <div style={s.logo}>
        <h1 style={s.logoTitle}>Inventário</h1>
        <p style={s.logoSub}>Acesse para iniciar a contagem</p>
      </div>

      <div style={s.field}>
        <label style={s.label}>E-mail</label>
        <input
          type="email"
          placeholder="seu@email.com"
          autoComplete="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setEmailFocused(true)}
          onBlur={() => setEmailFocused(false)}
          style={{ ...s.input, ...(emailFocused ? s.inputFocus : {}) }}
        />
      </div>

      <div style={s.field}>
        <label style={s.label}>Senha</label>
        <input
          type="password"
          placeholder="••••••••"
          autoComplete="current-password"
          value={senha}
          onChange={e => setSenha(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setSenhaFocused(true)}
          onBlur={() => setSenhaFocused(false)}
          style={{ ...s.input, ...(senhaFocused ? s.inputFocus : {}) }}
        />
      </div>

      <div style={s.error}>{erro}</div>

      <button
        style={{ ...s.btn, ...(loading ? s.btnDisabled : {}) }}
        onClick={handleLogin}
        disabled={loading}
      >
        {loading ? 'Entrando...' : 'Entrar'}
      </button>
    </div>
  )
}
