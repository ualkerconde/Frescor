import React from 'react'

/**
 * Menu lateral (drawer) que esconde ações secundárias — hoje apenas
 * "Sair", mas é o lugar natural para futuras opções (ex.: configurações,
 * dados do usuário) sem disputar espaço com a lista de produtos.
 */

const s = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.4)',
    zIndex: 40,
    opacity: 0,
    pointerEvents: 'none',
    transition: 'opacity 0.2s ease',
  },
  overlayOpen: { opacity: 1, pointerEvents: 'auto' },
  panel: {
    position: 'fixed',
    top: 0,
    left: 0,
    bottom: 0,
    width: 260,
    maxWidth: '80vw',
    background: '#fff',
    zIndex: 41,
    boxShadow: '2px 0 20px rgba(0,0,0,0.15)',
    transform: 'translateX(-100%)',
    transition: 'transform 0.25s ease',
    display: 'flex',
    flexDirection: 'column',
  },
  panelOpen: { transform: 'translateX(0)' },
  header: { padding: '24px 16px 16px', borderBottom: '1px solid #E5E5E5' },
  title: { fontSize: 16, fontWeight: 600, color: '#1A1A1A' },
  sub: { fontSize: 12, color: '#9CA3AF', marginTop: 2 },
  body: { flex: 1, padding: 8 },
  item: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '12px',
    background: 'none',
    border: 'none',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 500,
    color: '#1A1A1A',
    cursor: 'pointer',
    textAlign: 'left',
    fontFamily: 'inherit',
  },
  logoutItem: { color: '#DC2626' },
}

export function Drawer({ aberto, onClose, onLogout, onAbrirRecebimento }) {
  return (
    <>
      <div
        style={{ ...s.overlay, ...(aberto ? s.overlayOpen : {}) }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        style={{ ...s.panel, ...(aberto ? s.panelOpen : {}) }}
        role="dialog"
        aria-modal="true"
        aria-hidden={!aberto}
      >
        <div style={s.header}>
          <div style={s.title}>Inventário</div>
          <div style={s.sub}>Contagem de estoque</div>
        </div>
        <div style={s.body}>
          {onAbrirRecebimento && (
            <button style={s.item} onClick={onAbrirRecebimento}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="1" y="3" width="15" height="13" />
                <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
                <circle cx="5.5" cy="18.5" r="2.5" />
                <circle cx="18.5" cy="18.5" r="2.5" />
              </svg>
              Recebimento
            </button>
          )}
          <button style={{ ...s.item, ...s.logoutItem }} onClick={onLogout}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Sair
          </button>
        </div>
      </div>
    </>
  )
}
