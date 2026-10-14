import type { ReactNode } from "react"
import { Navigate } from "react-router"
import { useSessao } from "./contexto"

/** Sem sessão, manda para o login. */
export function RotaProtegida({ children }: { children: ReactNode }) {
  const { autenticado } = useSessao()
  if (!autenticado) return <Navigate to="/entrar" replace />
  return children
}
