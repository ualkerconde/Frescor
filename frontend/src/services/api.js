/**
 * Camada de comunicação com a API do backend.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

// ---- Tokens ----

export function getTokens() {
  return {
    accessToken: localStorage.getItem('access_token'),
    refreshToken: localStorage.getItem('refresh_token'),
  }
}

export function saveTokens(accessToken, refreshToken) {
  localStorage.setItem('access_token', accessToken)
  if (refreshToken) localStorage.setItem('refresh_token', refreshToken)
}

export function clearTokens() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

// ---- Fetch com refresh automático ----

async function tryRefreshToken() {
  const { refreshToken } = getTokens()
  if (!refreshToken) return false
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return false
    const data = await res.json()
    saveTokens(data.access_token, null)
    return true
  } catch {
    return false
  }
}

export async function apiFetch(path, options = {}) {
  const { accessToken } = getTokens()
  const headers = {
    'Content-Type': 'application/json',
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...(options.headers || {}),
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      const { accessToken: newToken } = getTokens()
      return fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { ...headers, Authorization: `Bearer ${newToken}` },
      })
    }
    clearTokens()
    throw new Error('SESSION_EXPIRED')
  }

  return res
}

// ---- Endpoints ----

export async function login(email, senha) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, senha }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || 'E-mail ou senha incorretos.')
  }
  return res.json()
}

export async function fetchProdutos() {
  const res = await apiFetch('/produtos')
  if (!res.ok) throw new Error('Erro ao carregar produtos.')
  return res.json()
}

export async function sincronizarEstoque(contagens) {
  const res = await apiFetch('/estoque/sincronizar', {
    method: 'POST',
    body: JSON.stringify({ contagens }),
  })
  if (!res.ok) throw new Error('Erro ao sincronizar.')
  return res.json()
}

// ---- Recebimento (Fase 5 / E11, D77) ----
// Só online: a confirmação não entra na fila offline da contagem. Os erros
// viram mensagens em português (o `detail` do backend); o código HTTP nunca
// chega à tela. Falha de rede vira o erro 'SEM_CONEXAO'.

async function chamarRecebimento(path, options) {
  let res
  try {
    res = await apiFetch(path, options)
  } catch (e) {
    if (e.message === 'SESSION_EXPIRED') throw e
    throw new Error('SEM_CONEXAO')
  }
  if (res.ok) return res.json()
  const data = await res.json().catch(() => ({}))
  const erro = new Error(
    typeof data.detail === 'string'
      ? data.detail
      : 'Não foi possível concluir. Confira os dados e tente de novo.'
  )
  // 404/409: a entrega sumiu da lista (já confirmada, prazo encerrado ou de outra loja).
  erro.desatualizado = res.status === 404 || res.status === 409
  throw erro
}

export function fetchRecebimentos() {
  return chamarRecebimento('/recebimentos')
}

/** `diferencas` vazio = "Recebi tudo certo"; senão, só os itens que chegaram diferentes. */
export function confirmarRecebimento(entregaId, diferencas = []) {
  return chamarRecebimento(`/recebimentos/${entregaId}/confirmar`, {
    method: 'POST',
    body: JSON.stringify({ diferencas }),
  })
}

/**
 * Busca unificada: procura o valor `q` em `codigo` (código interno)
 * e `codigo_barras` (scanner) simultaneamente.
 * O app sempre usa esta função, independente do tipo de código do produto.
 */
export async function buscarPorCodigo(q) {
  const res = await apiFetch(`/produtos/buscar?q=${encodeURIComponent(q)}`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error('Erro na busca.')
  return res.json()
}
