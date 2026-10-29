import React, { useCallback, useEffect, useRef, useState } from 'react'
import { confirmarRecebimento, fetchRecebimentos } from '../services/api'
import {
  MOTIVOS,
  erroDoItem,
  formatarDia,
  formatarHora,
  formatarQuantidade,
  lerQuantidade,
  montarDiferencas,
  textoInicial,
  unidadeCurta,
} from '../recebimento/regras'
import '../recebimento/recebimento.css'

/**
 * Tela "Recebimento" do app da loja (Fase 5 / E11, D77, D78, D91).
 *
 * Por que existe: a loja confirma o que chegou da central, e o recebimento
 * alimenta o trânsito da necessidade (D79). Sem a confirmação, a entrega
 * conta como recebida pelo que foi enviado e fica marcada "sem confirmação"
 * para o gestor.
 *
 * Só online (D77): a confirmação não entra na fila offline da contagem, e
 * depois de confirmada a entrega não muda mais. Por isso a confirmação pede
 * um segundo toque, e o botão bloqueia o envio duplo.
 */

const SEM_CONEXAO = 'Sem internet. A confirmação do recebimento precisa de conexão: conecte o celular e tente de novo.'

function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const ligar = () => setOnline(true)
    const desligar = () => setOnline(false)
    window.addEventListener('online', ligar)
    window.addEventListener('offline', desligar)
    return () => {
      window.removeEventListener('online', ligar)
      window.removeEventListener('offline', desligar)
    }
  }, [])
  return online
}

function Seta() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

function BotaoEnviar({ enviando, rotulo, rotuloEnviando, ...props }) {
  return (
    <button type="button" className="rcb-botao rcb-botao-primario" disabled={enviando || props.disabled}
      aria-busy={enviando || undefined} {...props}>
      {enviando && <span className="rcb-girando" aria-hidden="true" />}
      {enviando ? rotuloEnviando : rotulo}
    </button>
  )
}

function Situacao({ situacao }) {
  if (situacao.situacao === 'sem_confirmacao') {
    return <span className="rcb-badge rcb-badge-aviso">Sem confirmação</span>
  }
  return <span className="rcb-badge rcb-badge-caminho">A caminho</span>
}

function CardEntrega({ entrega, onAbrir }) {
  const n = entrega.itens.length
  return (
    <button type="button" className="rcb-card" onClick={onAbrir}>
      <span className="rcb-card-topo">
        <span className="rcb-card-titulo">Entrega de {formatarDia(entrega.data_entrega)}</span>
        <Situacao situacao={entrega.situacao} />
      </span>
      <span className="rcb-apoio">
        {entrega.expedido_em ? `Saiu da central às ${formatarHora(entrega.expedido_em)} · ` : ''}
        {n} {n === 1 ? 'produto' : 'produtos'}
      </span>
      {entrega.situacao.situacao === 'sem_confirmacao' && (
        <span className="rcb-apoio">Confirme até o fim de hoje.</span>
      )}
    </button>
  )
}

function CampoItem({ item, campo, erro, onChange }) {
  const id = `rcb-item-${item.id}`
  const q = lerQuantidade(campo.texto)
  const diferente = q !== null && q !== Number(item.quantidade_expedida)
  return (
    <div className={`rcb-card${erro ? ' rcb-invalido' : ''}`}>
      <div className="rcb-item-linha">
        <span className="rcb-card-titulo">{item.produto.nome}</span>
        <span className="rcb-apoio">{item.produto.codigo}</span>
      </div>
      <span className="rcb-apoio">Enviado: {formatarQuantidade(item.quantidade_expedida, item.unidade)}</span>
      <div className="rcb-campo">
        <label htmlFor={id}>Chegou ({unidadeCurta(item.unidade)})</label>
        <div className="rcb-entrada">
          <input id={id} type="text" inputMode="decimal" autoComplete="off" value={campo.texto}
            aria-invalid={erro ? true : undefined} aria-describedby={erro ? `${id}-erro` : undefined}
            onChange={(e) => onChange({ texto: e.target.value })} />
          <span aria-hidden="true">{unidadeCurta(item.unidade)}</span>
        </div>
      </div>
      {diferente && (
        <fieldset className="rcb-motivos">
          <legend className="rcb-legenda">Motivo da diferença em {item.produto.nome}</legend>
          <div className="rcb-motivos-opcoes">
            {MOTIVOS.map((m) => (
              <label key={m.valor} className={`rcb-motivo${campo.motivo === m.valor ? ' rcb-motivo-marcado' : ''}`}>
                <input type="radio" name={`${id}-motivo`} value={m.valor} checked={campo.motivo === m.valor}
                  onChange={() => onChange({ motivo: m.valor })} />
                {m.rotulo}
              </label>
            ))}
          </div>
          {campo.motivo === 'outro' && (
            <div className="rcb-campo">
              <label htmlFor={`${id}-obs`}>O que aconteceu?</label>
              <textarea id={`${id}-obs`} rows={2} maxLength={255} value={campo.observacao}
                onChange={(e) => onChange({ observacao: e.target.value })} />
            </div>
          )}
        </fieldset>
      )}
      {erro && (
        <p id={`${id}-erro`} className="rcb-erro-campo">⚠ {erro}</p>
      )}
    </div>
  )
}

function DialogoConfirmar({ titulo, children, rotulo, enviando, erro, onConfirmar, onVoltar }) {
  const voltarRef = useRef(null)
  useEffect(() => {
    voltarRef.current?.focus()
  }, [])
  useEffect(() => {
    function tecla(e) {
      if (e.key === 'Escape' && !enviando) onVoltar()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [enviando, onVoltar])
  return (
    <div className="rcb-fundo-dialogo">
      <div className="rcb-dialogo" role="dialog" aria-modal="true" aria-labelledby="rcb-dialogo-titulo">
        <h2 id="rcb-dialogo-titulo">{titulo}</h2>
        {children}
        <p className="rcb-apoio">Depois de confirmar, não dá para alterar.</p>
        {erro && <div className="rcb-alerta rcb-alerta-erro" role="alert">{erro}</div>}
        <BotaoEnviar enviando={enviando} rotulo={rotulo} rotuloEnviando="Enviando…" onClick={onConfirmar} />
        <button ref={voltarRef} type="button" className="rcb-botao rcb-botao-secundario" disabled={enviando}
          onClick={onVoltar}>
          Voltar
        </button>
      </div>
    </div>
  )
}

function camposIniciais(entrega) {
  return Object.fromEntries(
    entrega.itens.map((i) => [i.id, { texto: textoInicial(i.quantidade_expedida), motivo: null, observacao: '' }])
  )
}

export function RecebimentoScreen({ onVoltar, onLogout }) {
  const online = useOnline()
  const [entregas, setEntregas] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erroLista, setErroLista] = useState(null)
  const [aviso, setAviso] = useState('')
  const [abertaId, setAbertaId] = useState(null)
  const [modo, setModo] = useState('ver')
  const [campos, setCampos] = useState({})
  const [mostrarErros, setMostrarErros] = useState(false)
  const [erroForm, setErroForm] = useState(null)
  const [dialogo, setDialogo] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [erroEnvio, setErroEnvio] = useState(null)
  const enviandoRef = useRef(false)

  const carregar = useCallback(async () => {
    setCarregando(true)
    try {
      setEntregas(await fetchRecebimentos())
      setErroLista(null)
    } catch (e) {
      if (e.message === 'SESSION_EXPIRED') { onLogout(); return }
      setErroLista(e.message === 'SEM_CONEXAO' ? SEM_CONEXAO : e.message)
    } finally {
      setCarregando(false)
    }
  }, [onLogout])

  useEffect(() => { carregar() }, [carregar])
  // Conexão voltou (só na passagem de sem para com): some o aviso e, se a
  // lista nunca carregou, tenta de novo.
  const onlineAntes = useRef(online)
  useEffect(() => {
    const voltou = online && !onlineAntes.current
    onlineAntes.current = online
    if (!voltou) return
    setErroLista((atual) => (atual === SEM_CONEXAO ? null : atual))
    if (entregas === null) carregar()
  }, [online, entregas, carregar])

  const aberta = entregas?.find((e) => e.id === abertaId) ?? null

  function abrir(entrega) {
    setAbertaId(entrega.id)
    setModo('ver')
    setCampos(camposIniciais(entrega))
    setMostrarErros(false)
    setErroForm(null)
    setAviso('')
  }

  function fechar() {
    setAbertaId(null)
    setDialogo(null)
    setErroEnvio(null)
  }

  function mudarCampo(itemId, mudanca) {
    setCampos((atual) => ({ ...atual, [itemId]: { ...atual[itemId], ...mudanca } }))
    setErroForm(null)
  }

  const errosItens = aberta && modo === 'diferenca'
    ? Object.fromEntries(aberta.itens.map((i) => [i.id, erroDoItem(i, campos[i.id])]))
    : {}

  function pedirEnvioDiferenca() {
    setMostrarErros(true)
    if (Object.values(errosItens).some(Boolean)) {
      setErroForm('Confira os produtos marcados antes de enviar.')
      return
    }
    if (montarDiferencas(aberta.itens, campos).length === 0) {
      setErroForm('Nenhum produto ficou diferente do enviado. Se chegou tudo certo, volte e use "Recebi tudo certo".')
      return
    }
    setErroEnvio(null)
    setDialogo('diferenca')
  }

  async function enviar() {
    if (enviandoRef.current) return
    if (!navigator.onLine) { setErroEnvio(SEM_CONEXAO); return }
    enviandoRef.current = true
    setEnviando(true)
    setErroEnvio(null)
    const diferencas = dialogo === 'diferenca' ? montarDiferencas(aberta.itens, campos) : []
    try {
      await confirmarRecebimento(aberta.id, diferencas)
      setEntregas((atual) => atual.filter((e) => e.id !== aberta.id))
      setAviso(diferencas.length
        ? `Recebimento da entrega de ${formatarDia(aberta.data_entrega)} confirmado com diferença em ${diferencas.length} ${diferencas.length === 1 ? 'produto' : 'produtos'}.`
        : `Recebimento da entrega de ${formatarDia(aberta.data_entrega)} confirmado: chegou tudo certo.`)
      fechar()
    } catch (e) {
      if (e.message === 'SESSION_EXPIRED') { onLogout(); return }
      if (e.desatualizado) {
        fechar()
        setAviso('')
        await carregar()
        setErroLista(e.message)
        return
      }
      setErroEnvio(e.message === 'SEM_CONEXAO' ? SEM_CONEXAO : e.message)
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  const avisoOffline = !online && (
    <div className="rcb-alerta rcb-alerta-aviso" role="status">{SEM_CONEXAO}</div>
  )

  if (aberta) {
    const diferencasResumo = dialogo === 'diferenca' ? montarDiferencas(aberta.itens, campos) : []
    return (
      <div className="rcb">
        <header className="rcb-cabecalho">
          <button type="button" className="rcb-voltar" onClick={fechar}><Seta />Entregas</button>
          <h1>Entrega de {formatarDia(aberta.data_entrega)}</h1>
        </header>
        <main className="rcb-corpo rcb-corpo-com-rodape">
          {avisoOffline}
          {modo === 'ver' ? (
            <>
              <p className="rcb-apoio">Confira o que chegou. Se algum produto veio diferente, use "Recebi com diferença".</p>
              <ul className="rcb-lista" aria-label="Produtos enviados">
                {aberta.itens.map((item) => (
                  <li key={item.id} className="rcb-card">
                    <div className="rcb-item-linha">
                      <span>{item.produto.nome}</span>
                      <span className="rcb-quantidade">{formatarQuantidade(item.quantidade_expedida, item.unidade)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <p className="rcb-apoio">Corrija só o que chegou diferente e escolha o motivo. O resto fica como enviado.</p>
              {aberta.itens.map((item) => (
                <CampoItem key={item.id} item={item} campo={campos[item.id]}
                  erro={mostrarErros ? errosItens[item.id] : null}
                  onChange={(m) => mudarCampo(item.id, m)} />
              ))}
            </>
          )}
          {erroForm && <div className="rcb-alerta rcb-alerta-erro" role="alert">{erroForm}</div>}
          {erroEnvio && !dialogo && <div className="rcb-alerta rcb-alerta-erro" role="alert">{erroEnvio}</div>}
        </main>
        <footer className="rcb-rodape">
          {modo === 'ver' ? (
            <>
              <BotaoEnviar enviando={false} rotulo="Recebi tudo certo" disabled={!online}
                onClick={() => { setErroEnvio(null); setDialogo('tudo') }} />
              <button type="button" className="rcb-botao rcb-botao-secundario"
                onClick={() => { setModo('diferenca'); setMostrarErros(false) }}>
                Recebi com diferença
              </button>
            </>
          ) : (
            <>
              <BotaoEnviar enviando={false} rotulo="Enviar recebimento" disabled={!online} onClick={pedirEnvioDiferenca} />
              <button type="button" className="rcb-botao rcb-botao-secundario"
                onClick={() => { setModo('ver'); setCampos(camposIniciais(aberta)); setErroForm(null) }}>
                Cancelar diferença
              </button>
            </>
          )}
        </footer>
        {dialogo === 'tudo' && (
          <DialogoConfirmar titulo="Chegou tudo certo?" rotulo="Confirmar recebimento" enviando={enviando}
            erro={erroEnvio} onConfirmar={enviar} onVoltar={() => setDialogo(null)}>
            <p>
              {aberta.itens.length} {aberta.itens.length === 1 ? 'produto' : 'produtos'} da entrega de{' '}
              {formatarDia(aberta.data_entrega)}, nas quantidades enviadas.
            </p>
          </DialogoConfirmar>
        )}
        {dialogo === 'diferenca' && (
          <DialogoConfirmar titulo="Enviar recebimento com diferença?" rotulo="Enviar recebimento"
            enviando={enviando} erro={erroEnvio} onConfirmar={enviar} onVoltar={() => setDialogo(null)}>
            <ul style={{ paddingLeft: 20 }}>
              {diferencasResumo.map((d) => {
                const item = aberta.itens.find((i) => i.id === d.item_id)
                const motivo = MOTIVOS.find((m) => m.valor === d.motivo).rotulo
                return (
                  <li key={d.item_id}>
                    {item.produto.nome}: enviado {formatarQuantidade(item.quantidade_expedida, item.unidade)},
                    chegou {formatarQuantidade(d.quantidade_recebida, item.unidade)} ({motivo})
                  </li>
                )
              })}
            </ul>
            <p className="rcb-apoio">Os outros produtos ficam como enviados.</p>
          </DialogoConfirmar>
        )}
      </div>
    )
  }

  return (
    <div className="rcb">
      <header className="rcb-cabecalho">
        <button type="button" className="rcb-voltar" onClick={onVoltar}><Seta />Contagem</button>
        <h1>Recebimento</h1>
      </header>
      <main className="rcb-corpo">
        <div aria-live="polite" className={aviso ? 'rcb-alerta rcb-alerta-sucesso' : 'rcb-so-leitor'}>{aviso}</div>
        {avisoOffline}
        {erroLista && erroLista !== SEM_CONEXAO && (
          <div className="rcb-alerta rcb-alerta-erro" role="alert">{erroLista}</div>
        )}
        {erroLista === SEM_CONEXAO && online && (
          <div className="rcb-alerta rcb-alerta-aviso" role="alert">{SEM_CONEXAO}</div>
        )}
        {entregas === null ? (
          carregando ? <p className="rcb-apoio">Carregando entregas…</p> : null
        ) : entregas.length === 0 ? (
          <div className="rcb-vazio">
            <p>
              Nenhuma entrega para confirmar. Quando a central registrar a saída de uma entrega para esta loja,
              ela aparece aqui.
            </p>
            <button type="button" className="rcb-botao rcb-botao-secundario" onClick={carregar} disabled={carregando}>
              {carregando ? 'Atualizando…' : 'Atualizar'}
            </button>
          </div>
        ) : (
          <>
            <p className="rcb-apoio">Toque na entrega para conferir o que chegou.</p>
            {entregas.map((e) => <CardEntrega key={e.id} entrega={e} onAbrir={() => abrir(e)} />)}
          </>
        )}
      </main>
    </div>
  )
}
