/**
 * Detecta se o app está sendo acessado por um navegador desktop.
 * O app é exclusivo para celular — se detectado desktop, a tela de
 * bloqueio é exibida (ver App.jsx).
 *
 * Não é uma barreira de segurança absoluta (user agents podem ser
 * alterados), mas cobre o objetivo prático: evitar uso casual via
 * desktop por acidente.
 */


import { useState, useEffect } from 'react'

export function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(false)

  useEffect(() => {
    const check = () => {
      const ua = navigator.userAgent.toLowerCase()
      const isMobile = /android|iphone|ipad|ipod|blackberry|windows phone|mobile/i.test(ua)
      // Considera desktop se: não é mobile pelo UA E a tela é larga (> 768px)
      // A combinação evita falsos positivos em tablets ou modo desktop do Safari
      setIsDesktop(!isMobile && window.innerWidth > 768)
    }
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  return isDesktop
}

/*export function useIsDesktop() {
  return false // desabilitado temporariamente para testes no desktop
}*/