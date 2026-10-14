/*
 * Estado da sessão do gestor para as telas (passo W4).
 *
 * - `autenticado`: há token do SaaS guardado.
 * - `entrar`: chama /auth/web/login; se der certo, marca a sessão.
 * - `sair`: o gestor clicou em "Sair" (sem motivo para mostrar).
 * - `motivoSaida`: por que a sessão terminou sozinha (refresh recusado,
 *   acesso revogado...). A tela de login mostra esse motivo.
 *
 * O hook useSessao fica em ./contexto.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { entrar as entrarNaApi } from "@/lib/api/cliente"
import { aoEncerrarSessao, limparTokens, temSessao } from "@/lib/api/sessao"
import { SessaoContexto } from "./contexto"

export function SessaoProvider({ children }: { children: ReactNode }) {
  const [autenticado, setAutenticado] = useState(temSessao)
  const [motivoSaida, setMotivoSaida] = useState<string | null>(null)

  useEffect(
    () =>
      aoEncerrarSessao((motivo) => {
        setAutenticado(false)
        setMotivoSaida(motivo)
      }),
    [],
  )

  const entrar = useCallback(async (email: string, senha: string) => {
    await entrarNaApi(email, senha)
    setMotivoSaida(null)
    setAutenticado(true)
  }, [])

  const sair = useCallback(() => {
    limparTokens()
    setMotivoSaida(null)
    setAutenticado(false)
  }, [])

  const valor = useMemo(() => ({ autenticado, motivoSaida, entrar, sair }), [autenticado, motivoSaida, entrar, sair])
  return <SessaoContexto.Provider value={valor}>{children}</SessaoContexto.Provider>
}
