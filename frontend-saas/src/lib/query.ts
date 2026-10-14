/*
 * Configuração do TanStack Query (decisão DF3).
 *
 * Repetição automática só para falha de servidor ou de conexão: um 4xx
 * (401, 403, 404, 422) não muda se repetir. O 401 já tem a renovação de
 * sessão própria no cliente da API.
 */
import { QueryClient } from "@tanstack/react-query"
import { ErroApi } from "@/lib/api/cliente"

export function criarQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (tentativas, erro) => {
          if (erro instanceof ErroApi && erro.status >= 400 && erro.status < 500) return false
          return tentativas < 2
        },
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  })
}
