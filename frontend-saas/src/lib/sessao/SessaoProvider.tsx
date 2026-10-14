/*
 * Estado da sessão do gestor para as telas (passo W4).
 *
 * - `autenticado`: há token do SaaS guardado.
 * - `entrar`: chama /auth/web/login; se der certo, marca a sessão.
 * - `sair`: o gestor clicou em "Sair" (sem motivo para mostrar).
 * - `motivoSaida`: por que a sessão terminou sozinha (refresh recusado,
 *   acesso revogado...). A tela de login mostra esse motivo.
 *
 * Ao sair (ou quando a sessão termina sozinha), o cache do TanStack Query é
 * apagado: os dados de um gestor não podem aparecer para o próximo que
 * entrar no mesmo navegador. Por isso este provider fica DENTRO do
 * QueryClientProvider.
 *
 * O hook useSessao fica em ./contexto.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { entrar as entrarNaApi } from "@/lib/api/cliente"
import { aoEncerrarSessao, limparTokens, temSessao } from "@/lib/api/sessao"
import { SessaoContexto } from "./contexto"

export function SessaoProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [autenticado, setAutenticado] = useState(temSessao)
  const [motivoSaida, setMotivoSaida] = useState<string | null>(null)

  useEffect(
    () =>
      aoEncerrarSessao((motivo) => {
        queryClient.clear()
        setAutenticado(false)
        setMotivoSaida(motivo)
      }),
    [queryClient],
  )

  const entrar = useCallback(async (email: string, senha: string) => {
    await entrarNaApi(email, senha)
    setMotivoSaida(null)
    setAutenticado(true)
  }, [])

  const sair = useCallback(() => {
    limparTokens()
    queryClient.clear()
    setMotivoSaida(null)
    setAutenticado(false)
  }, [queryClient])

  const valor = useMemo(() => ({ autenticado, motivoSaida, entrar, sair }), [autenticado, motivoSaida, entrar, sair])
  return <SessaoContexto.Provider value={valor}>{children}</SessaoContexto.Provider>
}
