import React, { useState, useEffect } from 'react'
import { getTokens } from './services/api'
import { LoginScreen } from './pages/LoginScreen'
import { MainScreen } from './pages/MainScreen'
import { DesktopBlockScreen } from './pages/DesktopBlockScreen'
import { useIsDesktop } from './hooks/useIsDesktop'

export default function App() {
  const isDesktop = useIsDesktop()
  const [autenticado, setAutenticado] = useState(false)
  const [verificando, setVerificando] = useState(true)

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

  return <MainScreen onLogout={() => setAutenticado(false)} />
}
