/**
 * Serviço de armazenamento offline.
 *
 * Guarda localmente:
 * - Cache dos produtos (para exibir mesmo sem internet)
 * - Contagens pendentes de sincronização (feitas offline)
 *
 * Usa localStorage por simplicidade — o volume de dados é pequeno
 * (até ~200 produtos por loja). Se no futuro o volume crescer muito,
 * pode ser migrado para IndexedDB com Dexie.js sem afetar o resto do app.
 */

const KEYS = {
  PRODUTOS_CACHE: 'cache_produtos',
  PENDING_SYNC: 'pending_sync',
}

// ---- Cache de produtos ----

export function salvarCacheProdutos(produtos) {
  try {
    localStorage.setItem(KEYS.PRODUTOS_CACHE, JSON.stringify(produtos))
  } catch (e) {
    console.warn('Não foi possível salvar cache de produtos:', e)
  }
}

export function lerCacheProdutos() {
  try {
    const raw = localStorage.getItem(KEYS.PRODUTOS_CACHE)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

// ---- Contagens pendentes de sincronização ----

export function lerPendentes() {
  try {
    const raw = localStorage.getItem(KEYS.PENDING_SYNC)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function salvarPendente(produtoId, quantidade, pesoInformadoKg = null) {
  const pendentes = lerPendentes()
  pendentes[produtoId] = {
    quantidade,
    peso_informado_kg: pesoInformadoKg,
    registrado_em_local: new Date().toISOString(),
  }
  localStorage.setItem(KEYS.PENDING_SYNC, JSON.stringify(pendentes))
  return pendentes
}

export function removerSincronizados(produtoIds) {
  const pendentes = lerPendentes()
  produtoIds.forEach(id => delete pendentes[id])
  localStorage.setItem(KEYS.PENDING_SYNC, JSON.stringify(pendentes))
  return pendentes
}

export function limparPendentes() {
  localStorage.removeItem(KEYS.PENDING_SYNC)
}

export function limparTudo() {
  localStorage.removeItem(KEYS.PRODUTOS_CACHE)
  localStorage.removeItem(KEYS.PENDING_SYNC)
}
