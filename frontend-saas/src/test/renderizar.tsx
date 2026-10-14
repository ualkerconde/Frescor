/*
 * Ajudantes dos testes de tela: renderizam o App completo (rotas reais,
 * sessão, TanStack Query) e simulam a API por rota.
 */
import { render } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router"
import { vi } from "vitest"
import App from "@/App"
import { SessaoProvider } from "@/lib/sessao/SessaoProvider"

export const ME = {
  usuario: { id: 27, nome: "Gestor Central Teste", email: "gestor@teste.com" },
  central: { id: 1, nome: "Central Principal" },
  negocio: { id: 1, nome: "Rede Padaria Teste" },
}

/** Resposta JSON como o backend devolveria. */
export function resposta(status: number, corpo: unknown = {}): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } })
}

/**
 * Simula a API: `rotas` mapeia "MÉTODO /caminho" (sem o prefixo /backend e
 * sem a query string) para uma resposta ou uma função que a produz.
 * Rota não mapeada responde 404 (o teste falha de forma visível).
 */
export function simularApi(
  rotas: Record<string, Response | ((init: RequestInit, url: URL) => Response | Promise<Response>)> = {},
) {
  const fetchSimulado = vi.fn(async (url: string, init: RequestInit = {}) => {
    const caminho = url.replace(/^\/backend/, "").split("?")[0]
    const chave = `${(init.method ?? "GET").toUpperCase()} ${caminho}`
    const alvo = rotas[chave]
    if (!alvo) return resposta(404, { detail: `rota não simulada no teste: ${chave}` })
    return typeof alvo === "function" ? alvo(init, new URL(url, "http://localhost")) : alvo.clone()
  })
  vi.stubGlobal("fetch", fetchSimulado)
  return fetchSimulado
}

export function renderizarApp(rota = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const resultado = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rota]}>
        <SessaoProvider>
          <App />
        </SessaoProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...resultado, queryClient }
}
