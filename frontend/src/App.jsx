import React, { useState, useEffect } from 'react'
import { clearTokens, getTokens } from './services/api'
import { LoginScreen } from './pages/LoginScreen'
import { MainScreen } from './pages/MainScreen'
import { RecebimentoScreen } from './pages/RecebimentoScreen'
import { DesktopBlockScreen } from './pages/DesktopBlockScreen'
import { useIsDesktop } from './hooks/useIsDesktop'

export default function App() {
  const isDesktop = useIsDesktop()
  const [autenticado, setAutenticado] = useState(false)
  const [verificando, setVerificando] = useState(true)
  const [tela, setTela] = useState('contagem') // contagem | recebimento

  useEffect(() => {
    // Verifica se já tem tokens salvos (sessão persistente)
    const { accessToken } = getTokens()
    setAutenticado(!!accessToken)
    setVerificando(false)
  }, [])

  // Bloqueia acesso via desktop
  if (isDesktop) return <DesktopBlockScreen />

  // Aguarda verificação inicial de sessão
  if (verificando) return null

  if (!autenticado) {
    return <LoginScreen onLoginSuccess={() => setAutenticado(true)} />
  }

  // Recebimento (Fase 5): tela separada, aberta pelo menu; a contagem não muda.
  if (tela === 'recebimento') {
    return (
      <RecebimentoScreen
        onVoltar={() => setTela('contagem')}
        onLogout={() => { clearTokens(); setTela('contagem'); setAutenticado(false) }}
      />
    )
  }

  return (
    <MainScreen
      onLogout={() => setAutenticado(false)}
      onAbrirRecebimento={() => setTela('recebimento')}
    />
  )
}
