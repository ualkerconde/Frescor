import React, { useEffect, useRef, useState } from 'react'
import { BrowserMultiFormatReader } from '@zxing/browser'

/**
 * Modal fullscreen que usa a câmera do celular (via ZXing) para ler
 * códigos de barras. Ao detectar um código válido, chama onDetected(code)
 * uma única vez e para a leitura — quem usa este componente decide o que
 * fazer com o código (ex.: preencher a busca de produtos).
 */

const s = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: '#000',
    zIndex: 50,
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px',
    color: '#fff',
    flexShrink: 0,
  },
  title: { fontSize: 14, fontWeight: 500 },
  closeBtn: {
    width: 36,
    height: 36,
    border: 'none',
    background: 'rgba(255,255,255,0.15)',
    borderRadius: 8,
    color: '#fff',
    fontSize: 18,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  videoWrap: {
    flex: 1,
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  video: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },
  frame: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    width: '78%',
    maxWidth: 320,
    height: 140,
    border: '2px solid #22C55E',
    borderRadius: 12,
    boxShadow: '0 0 0 2000px rgba(0,0,0,0.35)',
    pointerEvents: 'none',
  },
  dica: {
    position: 'absolute',
    bottom: 24,
    left: 0,
    right: 0,
    textAlign: 'center',
    color: '#fff',
    fontSize: 13,
    padding: '0 24px',
  },
  erroWrap: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    textAlign: 'center',
    color: '#fff',
  },
  erroTexto: { fontSize: 14, marginTop: 12, lineHeight: 1.5, whiteSpace: 'pre-line' },
  retryBtn: {
    marginTop: 20,
    padding: '10px 20px',
    border: 'none',
    borderRadius: 8,
    background: '#2563EB',
    color: '#fff',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
  },
}

const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent)

const INSTRUCOES_PERMISSAO = IS_IOS
  ? 'Para liberar no iPhone: toque em "aA" na barra de endereço → Ajustes do Site → Câmera → Permitir.\n' +
    'Se o app foi instalado na tela inicial: Ajustes do iPhone → Safari → Câmera → Permitir.'
  : 'Para liberar no Android (Chrome): toque no ícone à esquerda do endereço → Permissões → Câmera → Permitir.\n' +
    'Se o app foi instalado na tela inicial: segure o ícone do app → Informações do app → Permissões → Câmera.'

// Traduz o erro do navegador em uma mensagem que diga ao usuário o que fazer.
function mensagemDeErro(e) {
  if (!window.isSecureContext || !navigator.mediaDevices) {
    return 'A câmera só funciona com conexão segura (HTTPS). Acesse o app por um endereço que comece com https://.'
  }
  switch (e?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return `O acesso à câmera foi negado.\n\n${INSTRUCOES_PERMISSAO}\n\nDepois, toque em "Tentar novamente".`
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'Nenhuma câmera foi encontrada neste aparelho.'
    case 'NotReadableError':
    case 'AbortError':
      return 'A câmera está sendo usada por outro aplicativo. Feche-o e toque em "Tentar novamente".'
    default:
      return 'Não foi possível acessar a câmera. Toque em "Tentar novamente".'
  }
}

export function BarcodeScanner({ onDetected, onClose }) {
  const videoRef = useRef(null)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)

  useEffect(() => {
    let ativo = true
    let controls = null
    const reader = new BrowserMultiFormatReader()

    reader
      .decodeFromVideoDevice(undefined, videoRef.current, (result) => {
        if (!ativo || !result) return
        ativo = false
        controls?.stop()
        onDetected(result.getText())
      })
      .then((c) => {
        controls = c
        // O componente pode já ter sido desmontado (ou o código já
        // detectado) enquanto a Promise resolvia — para a câmera nesse caso.
        if (!ativo) controls.stop()
      })
      .catch((e) => {
        if (ativo) setErro(mensagemDeErro(e))
      })

    return () => {
      ativo = false
      controls?.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tentativa])

  function tentarNovamente() {
    setErro('')
    setTentativa((t) => t + 1)
  }

  return (
    <div style={s.overlay} role="dialog" aria-modal="true">
      <div style={s.header}>
        <span style={s.title}>Aponte para o código de barras</span>
        <button style={s.closeBtn} onClick={onClose} aria-label="Fechar leitor de código de barras">
          ✕
        </button>
      </div>

      {erro ? (
        <div style={s.erroWrap}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.7">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <p style={s.erroTexto}>{erro}</p>
          <button style={s.retryBtn} onClick={tentarNovamente}>
            Tentar novamente
          </button>
        </div>
      ) : (
        <div style={s.videoWrap}>
          <video ref={videoRef} style={s.video} muted playsInline />
          <div style={s.frame} />
          <p style={s.dica}>Mantenha o código de barras dentro da área destacada</p>
        </div>
      )}
    </div>
  )
}
