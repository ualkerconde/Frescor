/*
 * Contexto da sessão e o hook useSessao, separados do componente
 * SessaoProvider (um arquivo só com componentes mantém o fast refresh).
 */
import { createContext, useContext } from "react"

export interface Sessao {
  autenticado: boolean
  motivoSaida: string | null
  entrar: (email: string, senha: string) => Promise<void>
  sair: () => void
}

export const SessaoContexto = createContext<Sessao | null>(null)

export function useSessao(): Sessao {
  const sessao = useContext(SessaoContexto)
  if (!sessao) throw new Error("useSessao precisa estar dentro de <SessaoProvider>")
  return sessao
}
