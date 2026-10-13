import React, { useEffect, useRef, useState } from 'react'
import { BrowserMultiFormatReader } from '@zxing/browser'

/**
 * Modal fullscreen que usa a câmera do celular (via ZXing) para ler
 * códigos de barras. Ao detectar um código válido, chama onDetected(code)
 * uma única vez e para a leitura — quem usa este componente decide o que
 * fazer com o código (ex.: preencher a busca de produtos).
 *
 * Por que a câmera é controlada aqui e não só pelo ZXing (bug de tela
 * preta no iPhone, 2026-10-13 — ver docs/STATUS.md):
 * - Cada abertura cria o PRÓPRIO elemento <video>. Antes, todas usavam o
 *   mesmo <video>; com o StrictMode (efeito montado duas vezes em dev), a
 *   primeira abertura, ao ser parada, zerava o vídeo da segunda e a tela
 *   ficava preta sem erro.
 * - O stream é pedido aqui (getUserMedia) e desligado aqui, em qualquer
 *   saída: fechar, detectar, erro, tempo esgotado, app em segundo plano, ou
 *   câmera liberada depois de o leitor já ter sido fechado. Assim a luz da
 *   câmera nunca fica acesa.
 * - Há limites de tempo próprios: o ZXing pode esperar para sempre se o
 *   video.play() não responder, e então nada aparecia na tela.
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
  videoBox: {
    position: 'absolute',
    inset: 0,
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

// Tempo máximo para a câmera ser liberada (inclui o usuário responder ao
// pedido de permissão) e, depois de liberada, para a imagem aparecer.
const LIMITE_LIBERACAO_MS = 20000
const LIMITE_IMAGEM_MS = 8000

// Nome técnico do erro, mostrado ao usuário para facilitar o suporte.
function detalheTecnico(e) {
  if (!e) return ''
  const nome = e.name || 'Erro'
  return e.message ? `${nome}: ${e.message}` : nome
}

// Traduz o erro do navegador em uma mensagem que diga ao usuário o que fazer.
function mensagemDeErro(e) {
  let texto
  switch (e?.name) {
    case 'ContextoInseguro':
      texto = 'A câmera só funciona com conexão segura (HTTPS). Acesse o app por um endereço que comece com https://.'
      break
    case 'NotAllowedError':
    case 'SecurityError':
      texto = `O acesso à câmera foi negado.\n\n${INSTRUCOES_PERMISSAO}\n\nDepois, toque em "Tentar novamente".`
      break
    case 'NotFoundError':
    case 'OverconstrainedError':
      texto = 'Nenhuma câmera foi encontrada neste aparelho.'
      break
    case 'NotReadableError':
    case 'AbortError':
      texto = 'A câmera está sendo usada por outro aplicativo. Feche-o e toque em "Tentar novamente".'
      break
    case 'LiberacaoEsgotada':
      texto = 'A câmera não foi liberada a tempo. Se apareceu um pedido de permissão, toque em "Permitir" e depois em "Tentar novamente".'
      break
    case 'ImagemEsgotada':
      texto = 'A câmera não respondeu. Toque em "Tentar novamente". Se continuar, feche e abra o app.'
      break
    case 'AppEmSegundoPlano':
      texto = 'A leitura foi pausada porque o app saiu da tela. Toque em "Tentar novamente".'
      break
    default:
      texto = 'Não foi possível acessar a câmera. Toque em "Tentar novamente".'
  }
  const detalhe = detalheTecnico(e)
  return detalhe ? `${texto}\n\n(Detalhe técnico: ${detalhe})` : texto
}

function erroComNome(nome, message = '') {
  const e = new Error(message)
  e.name = nome
  return e
}

function criarVideo() {
  const video = document.createElement('video')
  // muted + playsinline + autoplay como atributos E propriedades: o Safari
  // do iPhone só toca vídeo inline e sem gesto do usuário nessas condições.
  video.muted = true
  video.playsInline = true
  video.autoplay = true
  video.setAttribute('muted', '')
  video.setAttribute('playsinline', '')
  video.setAttribute('autoplay', '')
  Object.assign(video.style, { width: '100%', height: '100%', objectFit: 'cover', display: 'block' })
  return video
}

function videoEstaTocando(video) {
  return video.readyState >= 2 && !video.paused && video.currentTime > 0
}

export function BarcodeScanner({ onDetected, onClose }) {
  const containerRef = useRef(null)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)

  useEffect(() => {
    // Cada execução deste efeito é uma "abertura" independente, com seu
    // próprio vídeo, stream e timers. Nada é compartilhado entre aberturas.
    let ativo = true
    let stream = null
    let controls = null
    let timer = null
    const video = criarVideo()
    containerRef.current?.appendChild(video)

    function desligarStream(s) {
      s?.getTracks().forEach((t) => t.stop())
    }

    // Desliga tudo desta abertura. Seguro de chamar mais de uma vez.
    function encerrar() {
      ativo = false
      clearTimeout(timer)
      try {
        controls?.stop()
      } catch {
        // controls.stop() também desliga o stream; se falhar, desligamos abaixo.
      }
      desligarStream(stream)
      desligarStream(video.srcObject)
      video.srcObject = null
      video.remove()
    }

    function falhar(e) {
      if (!ativo) return
      encerrar()
      setErro(mensagemDeErro(e))
    }

    function aoMudarVisibilidade() {
      if (document.hidden) falhar(erroComNome('AppEmSegundoPlano'))
    }
    document.addEventListener('visibilitychange', aoMudarVisibilidade)
    window.addEventListener('pagehide', aoMudarVisibilidade)

    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      falhar(erroComNome('ContextoInseguro', 'window.isSecureContext = ' + window.isSecureContext))
    } else {
      timer = setTimeout(
        () => falhar(erroComNome('LiberacaoEsgotada', `sem resposta do getUserMedia em ${LIMITE_LIBERACAO_MS / 1000} s`)),
        LIMITE_LIBERACAO_MS,
      )

      navigator.mediaDevices
        .getUserMedia({ video: { facingMode: 'environment' }, audio: false })
        .then((s) => {
          // A câmera pode chegar depois de o leitor ter sido fechado (ou de
          // o StrictMode ter desmontado esta abertura): desliga na hora.
          if (!ativo) {
            desligarStream(s)
            return
          }
          stream = s
          clearTimeout(timer)
          timer = setTimeout(() => {
            if (ativo && !videoEstaTocando(video)) {
              falhar(erroComNome('ImagemEsgotada', `vídeo sem imagem após ${LIMITE_IMAGEM_MS / 1000} s (readyState=${video.readyState}, paused=${video.paused})`))
            }
          }, LIMITE_IMAGEM_MS)

          const reader = new BrowserMultiFormatReader()
          return reader
            .decodeFromStream(s, video, (result) => {
              if (!ativo || !result) return
              const texto = result.getText()
              encerrar()
              onDetected(texto)
            })
            .then((c) => {
              controls = c
              if (!ativo) {
                try {
                  c.stop()
                } catch {
                  // o stream já foi desligado em encerrar()
                }
              }
            })
        })
        .catch(falhar)
    }

    return () => {
      document.removeEventListener('visibilitychange', aoMudarVisibilidade)
      window.removeEventListener('pagehide', aoMudarVisibilidade)
      encerrar()
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
          {/* O <video> é criado e removido pelo efeito acima, um por abertura. */}
          <div ref={containerRef} style={s.videoBox} />
          <div style={s.frame} />
          <p style={s.dica}>Mantenha o código de barras dentro da área destacada</p>
        </div>
      )}
    </div>
  )
}
