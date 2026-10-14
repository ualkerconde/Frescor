/*
 * Tokens da sessão do gestor no SaaS (decisão DF2: localStorage no V1).
 *
 * Chaves próprias do SaaS, diferentes das do app mobile: as duas portas de
 * entrada têm tokens diferentes (claim "porta": "web", decisão D10) e não
 * devem se misturar se rodarem no mesmo navegador.
 *
 * Endurecimento previsto antes da produção (STATUS, DF2): refresh token em
 * cookie httpOnly + proteção CSRF (exige mudança no backend).
 */

const CHAVE_ACCESS = 'frescor_web_access_token'
const CHAVE_REFRESH = 'frescor_web_refresh_token'

export interface Tokens {
  accessToken: string | null
  refreshToken: string | null
}

export function lerTokens(): Tokens {
  return {
    accessToken: localStorage.getItem(CHAVE_ACCESS),
    refreshToken: localStorage.getItem(CHAVE_REFRESH),
  }
}

export function salvarTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(CHAVE_ACCESS, accessToken)
  if (refreshToken) localStorage.setItem(CHAVE_REFRESH, refreshToken)
}

export function limparTokens(): void {
  localStorage.removeItem(CHAVE_ACCESS)
  localStorage.removeItem(CHAVE_REFRESH)
}

export function temSessao(): boolean {
  return lerTokens().accessToken !== null
}

/*
 * Aviso de "sessão encerrada" (ex.: refresh recusado, acesso revogado).
 * O cliente da API avisa aqui; a tela (provedor de sessão) escuta para
 * voltar ao login mostrando o motivo.
 */
type OuvinteFimDeSessao = (motivo: string) => void
const ouvintes = new Set<OuvinteFimDeSessao>()

export function aoEncerrarSessao(ouvinte: OuvinteFimDeSessao): () => void {
  ouvintes.add(ouvinte)
  return () => {
    ouvintes.delete(ouvinte)
  }
}

export function encerrarSessao(motivo: string): void {
  limparTokens()
  for (const ouvinte of ouvintes) ouvinte(motivo)
}
