import React from 'react'

const styles = {
  base: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 16px',
    fontSize: 12,
    fontWeight: 500,
    transition: 'all 0.2s',
  },
  syncing: { background: '#EFF6FF', color: '#2563EB' },
  ok: { background: '#F0FDF4', color: '#16A34A' },
  error: { background: '#FEF2F2', color: '#DC2626' },
}

const icons = {
  syncing: '↻',
  ok: '✓',
  error: '⚠',
}

export function SyncBanner({ status, message }) {
  if (status === 'idle') return null

  return (
    <div style={{ ...styles.base, ...styles[status] }}>
      <span style={status === 'syncing' ? { display: 'inline-block', animation: 'spin 1s linear infinite' } : {}}>
        {icons[status]}
      </span>
      <span>{message}</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
