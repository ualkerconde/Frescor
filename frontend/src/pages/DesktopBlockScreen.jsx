import React from 'react'

export function DesktopBlockScreen() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 48,
      textAlign: 'center',
      background: '#FAFAFA',
    }}>
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#9CA3AF" strokeWidth="1.5" style={{ marginBottom: 24 }}>
        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
        <path d="M12 18h.01"/>
      </svg>
      <h1 style={{ fontSize: 20, fontWeight: 600, color: '#1A1A1A', marginBottom: 8 }}>
        Acesso exclusivo pelo celular
      </h1>
      <p style={{ fontSize: 14, color: '#6B6B6B', lineHeight: 1.6, maxWidth: 320 }}>
        Este aplicativo foi desenvolvido para uso em dispositivos móveis.
        Acesse pelo seu smartphone para utilizar.
      </p>
    </div>
  )
}
