import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fetchProdutos, clearTokens } from '../services/api'
import {
  salvarCacheProdutos,
  lerCacheProdutos,
  lerPendentes,
  salvarPendente,
} from '../services/storage'
import { useSync } from '../hooks/useSync'
import { SyncBanner } from '../components/SyncBanner'
import { ProdutoItem } from '../components/ProdutoItem'
import { Drawer } from '../components/Drawer'
import { BarcodeScanner } from '../components/BarcodeScanner'
import { FiltroClassificacao } from '../components/FiltroClassificacao'

const s = {
  screen: { display: 'flex', flexDirection: 'column', height: '100vh', background: '#FAFAFA' },
  header: {
    position: 'sticky', top: 0, zIndex: 10,
    background: '#fff', borderBottom: '1px solid #E5E5E5',
    padding: '0 16px', flexShrink: 0,
  },
  headerInner: { display: 'flex', alignItems: 'center', height: 56, gap: 12 },
  headerTitle: { flex: 1 },
  headerH2: { fontSize: 16, fontWeight: 600, color: '#1A1A1A' },
  headerDate: { fontSize: 12, color: '#6B6B6B' },
  iconBtn: {
    width: 36, height: 36, border: 'none', background: 'none',
    borderRadius: 8, cursor: 'pointer', display: 'flex',
    alignItems: 'center', justifyContent: 'center', color: '#6B6B6B',
    position: 'relative', flexShrink: 0,
  },
  iconBtnSyncing: { color: '#2563EB' },
  iconBtnPendente: { color: '#D97706' },
  iconSpin: { animation: 'spin 1s linear infinite' },
  syncBadge: {
    position: 'absolute', top: 2, right: 2,
    minWidth: 15, height: 15, padding: '0 3px',
    borderRadius: 8, background: '#D97706', color: '#fff',
    fontSize: 9, fontWeight: 700, lineHeight: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  searchBar: { padding: '10px 16px', background: '#fff', borderBottom: '1px solid #E5E5E5', flexShrink: 0 },
  searchWrap: { position: 'relative' },
  searchInput: {
    width: '100%', padding: '9px 12px 9px 36px',
    border: '1.5px solid #E5E5E5', borderRadius: 8,
    fontSize: 14, fontFamily: 'inherit', background: '#F8F8F8',
    color: '#1A1A1A', outline: 'none', transition: 'all 0.15s',
  },
  searchIcon: { position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9CA3AF', pointerEvents: 'none' },
  statsBar: { display: 'flex', padding: '10px 16px', background: '#FAFAFA', borderBottom: '1px solid #E5E5E5', flexShrink: 0 },
  stat: { flex: 1, textAlign: 'center' },
  statNum: { fontSize: 18, fontWeight: 600, color: '#1A1A1A' },
  statLabel: { fontSize: 11, color: '#9CA3AF', marginTop: 1 },
  statDivider: { borderLeft: '1px solid #E5E5E5' },
  list: { flex: 1, overflowY: 'auto', WebkitOverflowScrolling: 'touch' },
  empty: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, textAlign: 'center', color: '#9CA3AF' },
  emptyText: { fontSize: 14, marginTop: 12 },
}

function formatDate(date) {
  return new Intl.DateTimeFormat('pt-BR', {
    weekday: 'long', day: 'numeric', month: 'long'
  }).format(date)
}

export function MainScreen({ onLogout, onAbrirRecebimento }) {
  const [produtos, setProdutos] = useState([])
  const [pendentes, setPendentes] = useState({})
  const [busca, setBusca] = useState('')
  const [filtros, setFiltros] = useState({})
  const [loading, setLoading] = useState(true)
  const [drawerAberto, setDrawerAberto] = useState(false)
  const [scannerAberto, setScannerAberto] = useState(false)
  const inputsRef = useRef([])

  const recarregarPendentes = useCallback(() => {
    setPendentes(lerPendentes())
  }, [])

  const recarregarProdutos = useCallback(async () => {
    try {
      const data = await fetchProdutos()
      setProdutos(data)
      salvarCacheProdutos(data)
    } catch (e) {
      if (e.message === 'SESSION_EXPIRED') { onLogout(); return }
    }
  }, [onLogout])

  const { syncStatus, syncMessage, agendarSync, executarSync } = useSync(() => {
    recarregarPendentes()
    recarregarProdutos()
  })

  useEffect(() => {
    async function init() {
      setLoading(true)
      const cache = lerCacheProdutos()
      if (cache) setProdutos(cache)
      setPendentes(lerPendentes())
      await recarregarProdutos()
      setPendentes(lerPendentes())
      setLoading(false)
    }
    init()
  }, [recarregarProdutos, recarregarPendentes])

  function handleQtyChange(produtoId, quantidade, pesoInformadoKg = null) {
    const novos = salvarPendente(produtoId, quantidade, pesoInformadoKg)
    setPendentes({ ...novos })
    agendarSync()
  }

  function focusNext(index) {
    const visiveis = inputsRef.current.filter(Boolean)
    if (index < visiveis.length - 1) visiveis[index + 1].focus()
  }

  // Chamado quando o leitor de código de barras (câmera) detecta um
  // código: reaproveita o mesmo filtro de busca textual já existente
  // (funciona até offline, sem precisar de uma chamada extra à API).
  function handleCodigoDetectado(codigo) {
    setScannerAberto(false)
    setBusca(codigo)
  }

  // Filtra por classificação (níveis configurados pelo negócio) E por
  // busca textual (nome, código interno, código de barras ou classificação).
  const produtosFiltrados = produtos.filter(p => {
    const passaFiltros = Object.entries(filtros).every(([nivel, valor]) => {
      if (!valor) return true
      return (p.classificacao || []).some(c => c.nivel === nivel && c.valor === valor)
    })
    if (!passaFiltros) return false

    if (!busca) return true
    const q = busca.toLowerCase()
    return (
      p.nome.toLowerCase().includes(q) ||
      (p.codigo && p.codigo.toLowerCase().includes(q)) ||
      (p.codigo_barras && p.codigo_barras.includes(q)) ||
      (p.classificacao || []).some(c => c.valor.toLowerCase().includes(q))
    )
  })

  const total = produtos.length
  const contados = produtos.filter(p => {
    if (p.requer_peso_informado) {
      const peso = pendentes[p.id]?.peso_informado_kg ?? p.peso_informado_kg
      return peso != null && peso > 0
    }
    const qty = pendentes[p.id]?.quantidade ?? p.quantidade_inventariada
    return qty > 0
  }).length
  const numPendentes = Object.keys(pendentes).length

  return (
    <div style={s.screen}>
      <div style={s.header}>
        <div style={s.headerInner}>
          <button style={s.iconBtn} onClick={() => setDrawerAberto(true)} title="Menu" aria-label="Abrir menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <div style={s.headerTitle}>
            <h2 style={s.headerH2}>Contagem de Estoque</h2>
            <p style={s.headerDate}>{formatDate(new Date())}</p>
          </div>
          <button style={s.iconBtn} onClick={() => setScannerAberto(true)} title="Ler código de barras" aria-label="Ler código de barras">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/>
              <path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/>
              <line x1="7" y1="12" x2="17" y2="12"/>
            </svg>
          </button>
          <button
            style={{
              ...s.iconBtn,
              ...(syncStatus === 'syncing' ? s.iconBtnSyncing : {}),
              ...(syncStatus !== 'syncing' && numPendentes > 0 ? s.iconBtnPendente : {}),
            }}
            onClick={executarSync}
            title="Sincronizar agora (envia contagens pendentes e atualiza a lista)"
            aria-label="Sincronizar agora"
          >
            <svg
              width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              style={syncStatus === 'syncing' ? s.iconSpin : {}}
            >
              <polyline points="23 4 23 10 17 10"/>
              <polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            {numPendentes > 0 && <span style={s.syncBadge}>{numPendentes}</span>}
          </button>
        </div>
      </div>

      <style>{'@keyframes spin { to { transform: rotate(360deg); } }'}</style>

      <SyncBanner status={syncStatus} message={syncMessage} />

      <div style={s.searchBar}>
        <div style={s.searchWrap}>
          <svg style={s.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            type="text"
            placeholder="Buscar por nome, código, cód. de barras ou categoria..."
            value={busca}
            onChange={e => setBusca(e.target.value)}
            style={s.searchInput}
          />
        </div>
      </div>

      <FiltroClassificacao produtos={produtos} filtros={filtros} onChange={setFiltros} />

      <div style={s.statsBar}>
        <div style={s.stat}>
          <div style={s.statNum}>{total}</div>
          <div style={s.statLabel}>produtos</div>
        </div>
        <div style={{ ...s.stat, ...s.statDivider }}>
          <div style={{ ...s.statNum, color: contados > 0 ? '#16A34A' : '#1A1A1A' }}>{contados}</div>
          <div style={s.statLabel}>contados</div>
        </div>
        <div style={{ ...s.stat, ...s.statDivider }}>
          <div style={{ ...s.statNum, color: numPendentes > 0 ? '#D97706' : '#1A1A1A' }}>{numPendentes}</div>
          <div style={s.statLabel}>a sincronizar</div>
        </div>
      </div>

      <div style={s.list}>
        {loading && produtos.length === 0 ? (
          <div style={s.empty}><p style={s.emptyText}>Carregando produtos...</p></div>
        ) : produtosFiltrados.length === 0 ? (
          <div style={s.empty}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3">
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
            </svg>
            <p style={s.emptyText}>
              {busca ? 'Nenhum produto encontrado.' : 'Nenhum produto disponível.'}
            </p>
          </div>
        ) : (
          produtosFiltrados.map((produto, idx) => {
            const qty = pendentes[produto.id]?.quantidade ?? produto.quantidade_inventariada
            const peso = pendentes[produto.id]?.peso_informado_kg ?? produto.peso_informado_kg
            const isPending = !!pendentes[produto.id]
            return (
              <ProdutoItem
                key={produto.id}
                produto={produto}
                quantidade={qty}
                pesoInformadoKg={peso}
                isPending={isPending}
                onQtyChange={handleQtyChange}
                onFocusNext={() => focusNext(idx)}
              />
            )
          })
        )}
      </div>

      <Drawer
        aberto={drawerAberto}
        onClose={() => setDrawerAberto(false)}
        onAbrirRecebimento={onAbrirRecebimento}
        onLogout={() => { clearTokens(); onLogout() }}
      />

      {scannerAberto && (
        <BarcodeScanner
          onDetected={handleCodigoDetectado}
          onClose={() => setScannerAberto(false)}
        />
      )}
    </div>
  )
}
