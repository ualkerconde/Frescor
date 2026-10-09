/**
 * Hook que gerencia a sincronização automática de contagens pendentes.
 *
 * Comportamento:
 * - Tenta sincronizar 1.5s depois de qualquer alteração (debounce)
 * - Verifica conexão antes de tentar — se offline, guarda e aguarda
 * - Ao voltar online (evento 'online' do navegador), tenta de novo
 * - Expõe o estado de sincronização para a UI mostrar feedback visual
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { sincronizarEstoque } from '../services/api'
import {
  lerPendentes,
  removerSincronizados,
} from '../services/storage'

export function useSync(onSyncSuccess) {
  const [syncStatus, setSyncStatus] = useState('idle') // idle | syncing | ok | error
  const [syncMessage, setSyncMessage] = useState('')
  const timerRef = useRef(null)
  const syncingRef = useRef(false)

  const executarSync = useCallback(async () => {
    const pendentes = lerPendentes()
    if (Object.keys(pendentes).length === 0) return
    if (syncingRef.current) return
    if (!navigator.onLine) {
      setSyncStatus('error')
      setSyncMessage('Sem conexão — dados salvos localmente')
      return
    }

    syncingRef.current = true
    setSyncStatus('syncing')
    setSyncMessage('Sincronizando...')

    try {
      const contagens = Object.entries(pendentes).map(([id, entry]) => ({
        produto_id: parseInt(id),
        quantidade: entry.quantidade,
        peso_informado_kg: entry.peso_informado_kg ?? null,
        registrado_em_local: entry.registrado_em_local,
      }))

      const resultado = await sincronizarEstoque(contagens)
      const sincronizados = removerSincronizados(resultado.produto_ids)

      setSyncStatus('ok')
      setSyncMessage(`${resultado.sincronizados} item(ns) sincronizado(s)`)

      if (onSyncSuccess) onSyncSuccess()

      // Esconde o banner de ok após 3s
      setTimeout(() => setSyncStatus('idle'), 3000)
    } catch (e) {
      if (e.message === 'SESSION_EXPIRED') {
        setSyncStatus('error')
        setSyncMessage('Sessão expirada — faça login novamente')
      } else {
        setSyncStatus('error')
        setSyncMessage('Sem conexão — tentando depois')
        setTimeout(() => setSyncStatus('idle'), 3000)
      }
    } finally {
      syncingRef.current = false
    }
  }, [onSyncSuccess])

  // Agenda sincronização com debounce de 1.5s
  const agendarSync = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(executarSync, 1500)
  }, [executarSync])

  // Tenta sincronizar ao voltar online
  useEffect(() => {
    const handleOnline = () => {
      setSyncStatus('idle')
      executarSync()
    }
    window.addEventListener('online', handleOnline)
    return () => window.removeEventListener('online', handleOnline)
  }, [executarSync])

  return { syncStatus, syncMessage, agendarSync, executarSync }
}
