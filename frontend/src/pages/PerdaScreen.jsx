import React, { useCallback, useEffect, useRef, useState } from 'react'
import { alterarPerda, apagarPerda, fetchLancamentosPerda, fetchProdutos, lancarPerda } from '../services/api'
import { formatarDia, formatarHora, formatarQuantidade, textoInicial, unidadeCurta } from '../recebimento/regras'
import {
  MOTIVOS_PERDA,
  TAMANHO_OBSERVACAO,
  diaLocal,
  errosDaPerda,
  filtrarProdutos,
  montarCorpo,
  rotuloMotivo,
  temErro,
} from '../perda/regras'
import { BotaoEnviar, Seta, useOnline } from './RecebimentoScreen'
import '../recebimento/recebimento.css'

/**
 * Tela "Perda" do app da loja (D110).
 *
 * Por que existe: o supermercado em geral não registra a perda dos itens
 * produzidos na loja, então ela não vem do PDV como a venda. A loja lança
 * aqui, na hora do descarte (produto, quantidade, motivo), e a soma do dia
 * alimenta previsão, necessidade e o painel do gestor.
 *
 * Regras (do backend): hoje ou ontem; quantidade > 0 na unidade do produto;
 * motivo obrigatório ("Outro" pede uma linha); a loja corrige ou apaga até o
 * fim do dia seguinte, depois só o gestor. Só online, como o Recebimento: o
 * lançamento não entra na fila offline da contagem.
 */

const SEM_CONEXAO = 'Sem internet. O lançamento de perda precisa de conexão: conecte o celular e tente de novo.'

function mensagem(e) {
  return e.message === 'SEM_CONEXAO' ? SEM_CONEXAO : e.message
}

function CardLancamento({ lancamento: l, onAbrir }) {
  const conteudo = (
    <>
      <span className="rcb-card-topo">
        <span className="rcb-card-titulo">{l.produto.nome}</span>
        <span className="rcb-quantidade">{formatarQuantidade(l.quantidade, l.unidade)}</span>
      </span>
      <span className="rcb-apoio">{rotuloMotivo(l.motivo)}{l.observacao ? `: ${l.observacao}` : ''}</span>
      <span className="rcb-apoio">
        {l.lancado_por} às {formatarHora(l.lancado_em)}{l.alterado_em ? ' · corrigido' : ''}
      </span>
      {!l.loja_pode_alterar && <span className="rcb-apoio">Prazo encerrado: só o gestor corrige.</span>}
    </>
  )
  if (!l.loja_pode_alterar) return <li className="rcb-card">{conteudo}</li>
  return (
    <li>
      <button type="button" className="rcb-card" onClick={onAbrir}>{conteudo}</button>
    </li>
  )
}

function ListaDoDia({ titulo, lancamentos, onAbrir }) {
  if (lancamentos.length === 0) return null
  return (
    <section aria-label={titulo}>
      <h2 className="rcb-secao">{titulo}</h2>
      <ul className="rcb-lista">
        {lancamentos.map((l) => <CardLancamento key={l.id} lancamento={l} onAbrir={() => onAbrir(l)} />)}
      </ul>
    </section>
  )
}

function EscolherProduto({ produtos, erro, carregando, onEscolher, onTentar }) {
  const [busca, setBusca] = useState('')
  if (erro) {
    return (
      <>
        <div className="rcb-alerta rcb-alerta-erro" role="alert">{erro}</div>
        <button type="button" className="rcb-botao rcb-botao-secundario" onClick={onTentar}>Tentar de novo</button>
      </>
    )
  }
  if (produtos === null) return carregando ? <p className="rcb-apoio">Carregando produtos…</p> : null
  const achados = filtrarProdutos(produtos, busca)
  return (
    <>
      <div className="rcb-campo">
        <label htmlFor="prd-busca">Qual produto foi perdido?</label>
        <div className="rcb-entrada">
          <input id="prd-busca" type="search" autoComplete="off" placeholder="Nome ou código" value={busca}
            onChange={(e) => setBusca(e.target.value)} />
        </div>
      </div>
      {achados.length === 0 ? (
        <p className="rcb-apoio">Nenhum produto da loja com "{busca}".</p>
      ) : (
        <ul className="rcb-lista" aria-label="Produtos">
          {achados.map((p) => (
            <li key={p.id}>
              <button type="button" className="rcb-card" onClick={() => onEscolher(p)}>
                <span className="rcb-card-topo">
                  <span className="rcb-card-titulo">{p.nome}</span>
                  <span className="rcb-apoio">{unidadeCurta(p.unidade_medida)}</span>
                </span>
                {p.codigo && <span className="rcb-apoio">{p.codigo}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function DialogoApagar({ lancamento, enviando, erro, onConfirmar, onVoltar }) {
  const voltarRef = useRef(null)
  useEffect(() => { voltarRef.current?.focus() }, [])
  useEffect(() => {
    function tecla(e) {
      if (e.key === 'Escape' && !enviando) onVoltar()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [enviando, onVoltar])
  return (
    <div className="rcb-fundo-dialogo">
      <div className="rcb-dialogo" role="dialog" aria-modal="true" aria-labelledby="prd-dialogo-titulo">
        <h2 id="prd-dialogo-titulo">Apagar este lançamento?</h2>
        <p>
          {lancamento.produto.nome}: {formatarQuantidade(lancamento.quantidade, lancamento.unidade)} de{' '}
          {formatarDia(lancamento.data)} ({rotuloMotivo(lancamento.motivo).toLowerCase()}).
        </p>
        {erro && <div className="rcb-alerta rcb-alerta-erro" role="alert">{erro}</div>}
        <button type="button" className="rcb-botao rcb-botao-perigo" disabled={enviando} aria-busy={enviando || undefined}
          onClick={onConfirmar}>
          {enviando ? 'Apagando…' : 'Apagar lançamento'}
        </button>
        <button ref={voltarRef} type="button" className="rcb-botao rcb-botao-secundario" disabled={enviando}
          onClick={onVoltar}>
          Voltar
        </button>
      </div>
    </div>
  )
}

function formularioVazio() {
  return { produto: null, dia: diaLocal(0), texto: '', motivo: null, observacao: '' }
}

export function PerdaScreen({ onVoltar, onLogout }) {
  const online = useOnline()
  const [lancamentos, setLancamentos] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erroLista, setErroLista] = useState(null)
  const [aviso, setAviso] = useState('')
  // null = lista; { editando: lancamento | null, ...campos } = formulário aberto.
  const [form, setForm] = useState(null)
  const [produtos, setProdutos] = useState(null)
  const [erroProdutos, setErroProdutos] = useState(null)
  const [mostrarErros, setMostrarErros] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erroEnvio, setErroEnvio] = useState(null)
  const [dialogoApagar, setDialogoApagar] = useState(false)
  const enviandoRef = useRef(false)

  const sair = useCallback((e) => {
    if (e.message === 'SESSION_EXPIRED') { onLogout(); return true }
    return false
  }, [onLogout])

  const carregar = useCallback(async () => {
    setCarregando(true)
    try {
      setLancamentos(await fetchLancamentosPerda())
      setErroLista(null)
    } catch (e) {
      if (!sair(e)) setErroLista(mensagem(e))
    } finally {
      setCarregando(false)
    }
  }, [sair])

  const carregarProdutos = useCallback(async () => {
    setErroProdutos(null)
    try {
      setProdutos(await fetchProdutos())
    } catch (e) {
      if (!sair(e)) setErroProdutos(navigator.onLine ? 'Não foi possível carregar os produtos. Tente de novo.' : SEM_CONEXAO)
    }
  }, [sair])

  useEffect(() => { carregar() }, [carregar])

  const onlineAntes = useRef(online)
  useEffect(() => {
    const voltou = online && !onlineAntes.current
    onlineAntes.current = online
    if (!voltou) return
    setErroLista((atual) => (atual === SEM_CONEXAO ? null : atual))
    if (lancamentos === null) carregar()
  }, [online, lancamentos, carregar])

  const hoje = diaLocal(0)
  const ontem = diaLocal(-1)

  function novo() {
    setForm({ editando: null, ...formularioVazio() })
    setMostrarErros(false)
    setErroEnvio(null)
    setAviso('')
    if (produtos === null) carregarProdutos()
  }

  function editar(l) {
    setForm({
      editando: l, produto: { id: l.produto.id, nome: l.produto.nome, codigo: l.produto.codigo, unidade_medida: l.unidade },
      dia: l.data, texto: textoInicial(l.quantidade), motivo: l.motivo, observacao: l.observacao ?? '',
    })
    setMostrarErros(false)
    setErroEnvio(null)
    setAviso('')
  }

  function fechar() {
    setForm(null)
    setDialogoApagar(false)
    setErroEnvio(null)
  }

  function mudar(mudanca) {
    setForm((atual) => ({ ...atual, ...mudanca }))
    setErroEnvio(null)
  }

  async function enviar(acao, textoSucesso) {
    if (enviandoRef.current) return
    if (!navigator.onLine) { setErroEnvio(SEM_CONEXAO); return }
    enviandoRef.current = true
    setEnviando(true)
    setErroEnvio(null)
    try {
      await acao()
      fechar()
      setAviso(textoSucesso)
      await carregar()
    } catch (e) {
      if (sair(e)) return
      if (e.desatualizado) {
        fechar()
        await carregar()
        setErroLista(e.message)
        return
      }
      setErroEnvio(mensagem(e))
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  const erros = form?.produto ? errosDaPerda(form.produto.unidade_medida, form) : null

  function salvar() {
    setMostrarErros(true)
    if (temErro(erros)) return
    const corpo = montarCorpo(form)
    const resumo = `${form.produto.nome}: ${formatarQuantidade(corpo.quantidade, form.produto.unidade_medida)}`
    if (form.editando) {
      const id = form.editando.id
      enviar(() => alterarPerda(id, corpo), `Lançamento corrigido. ${resumo}.`)
    } else {
      const dados = { ...corpo, produto_id: form.produto.id, data: form.dia }
      enviar(() => lancarPerda(dados), `Perda lançada. ${resumo}.`)
    }
  }

  const avisoOffline = !online && <div className="rcb-alerta rcb-alerta-aviso" role="status">{SEM_CONEXAO}</div>

  if (form) {
    const unidade = form.produto ? unidadeCurta(form.produto.unidade_medida) : ''
    const e = mostrarErros && erros ? erros : {}
    return (
      <div className="rcb">
        <header className="rcb-cabecalho">
          <button type="button" className="rcb-voltar" onClick={fechar}><Seta />Perdas</button>
          <h1>{form.editando ? 'Corrigir perda' : 'Lançar perda'}</h1>
        </header>
        <main className={`rcb-corpo${form.produto ? ' rcb-corpo-com-rodape' : ''}`}>
          {avisoOffline}
          {!form.produto ? (
            <EscolherProduto produtos={produtos} erro={erroProdutos} carregando={!erroProdutos}
              onTentar={carregarProdutos} onEscolher={(p) => mudar({ produto: p })} />
          ) : (
            <>
              <div className="rcb-card">
                <div className="rcb-item-linha" style={{ alignItems: 'center' }}>
                  <span className="rcb-card-titulo">{form.produto.nome}</span>
                  {!form.editando && (
                    <button type="button" className="rcb-voltar" onClick={() => mudar({ produto: null })}>Trocar</button>
                  )}
                </div>
                {form.editando && (
                  <span className="rcb-apoio">Perda de {formatarDia(form.dia)}. Produto e dia não mudam: para isso, apague e lance de novo.</span>
                )}
              </div>

              {!form.editando && (
                <fieldset className="rcb-motivos">
                  <legend className="rcb-legenda">Quando foi?</legend>
                  <div className="rcb-motivos-opcoes">
                    {[{ valor: hoje, rotulo: `Hoje (${formatarDia(hoje)})` }, { valor: ontem, rotulo: `Ontem (${formatarDia(ontem)})` }].map((d) => (
                      <label key={d.valor} className={`rcb-motivo${form.dia === d.valor ? ' rcb-motivo-marcado' : ''}`}>
                        <input type="radio" name="prd-dia" value={d.valor} checked={form.dia === d.valor}
                          onChange={() => mudar({ dia: d.valor })} />
                        {d.rotulo}
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}

              <div className={`rcb-campo${e.quantidade ? ' rcb-invalido' : ''}`}>
                <label htmlFor="prd-quantidade">Quantidade perdida ({unidade})</label>
                <div className="rcb-entrada">
                  <input id="prd-quantidade" type="text" inputMode="decimal" autoComplete="off" value={form.texto}
                    aria-invalid={e.quantidade ? true : undefined}
                    aria-describedby={e.quantidade ? 'prd-quantidade-erro' : undefined}
                    onChange={(ev) => mudar({ texto: ev.target.value })} />
                  <span aria-hidden="true">{unidade}</span>
                </div>
                {e.quantidade && <p id="prd-quantidade-erro" className="rcb-erro-campo">⚠ {e.quantidade}</p>}
              </div>

              <fieldset className="rcb-motivos" aria-describedby={e.motivo ? 'prd-motivo-erro' : undefined}>
                <legend className="rcb-legenda">Motivo</legend>
                <div className="rcb-motivos-opcoes rcb-motivos-opcoes-3">
                  {MOTIVOS_PERDA.map((m) => (
                    <label key={m.valor} className={`rcb-motivo${form.motivo === m.valor ? ' rcb-motivo-marcado' : ''}`}>
                      <input type="radio" name="prd-motivo" value={m.valor} checked={form.motivo === m.valor}
                        onChange={() => mudar({ motivo: m.valor })} />
                      {m.rotulo}
                    </label>
                  ))}
                </div>
                {e.motivo && <p id="prd-motivo-erro" className="rcb-erro-campo">⚠ {e.motivo}</p>}
              </fieldset>

              <div className={`rcb-campo${e.observacao ? ' rcb-invalido' : ''}`}>
                <label htmlFor="prd-obs">
                  {form.motivo === 'outro' ? 'O que aconteceu?' : 'Observação (opcional)'}
                </label>
                <textarea id="prd-obs" rows={2} maxLength={TAMANHO_OBSERVACAO} value={form.observacao}
                  aria-invalid={e.observacao ? true : undefined}
                  aria-describedby={e.observacao ? 'prd-obs-erro' : undefined}
                  onChange={(ev) => mudar({ observacao: ev.target.value })} />
                {e.observacao && <p id="prd-obs-erro" className="rcb-erro-campo">⚠ {e.observacao}</p>}
              </div>

              {erroEnvio && !dialogoApagar && <div className="rcb-alerta rcb-alerta-erro" role="alert">{erroEnvio}</div>}
            </>
          )}
        </main>
        {form.produto && (
          <footer className="rcb-rodape">
            <BotaoEnviar enviando={enviando && !dialogoApagar} rotulo={form.editando ? 'Salvar correção' : 'Lançar perda'}
              rotuloEnviando="Enviando…" disabled={!online || enviando} onClick={salvar} />
            {form.editando && (
              <button type="button" className="rcb-botao rcb-botao-perigo" disabled={!online || enviando}
                onClick={() => { setErroEnvio(null); setDialogoApagar(true) }}>
                Apagar lançamento
              </button>
            )}
          </footer>
        )}
        {dialogoApagar && (
          <DialogoApagar lancamento={form.editando} enviando={enviando} erro={erroEnvio}
            onVoltar={() => setDialogoApagar(false)}
            onConfirmar={() => {
              const l = form.editando
              enviar(() => apagarPerda(l.id), `Lançamento apagado. ${l.produto.nome}: ${formatarQuantidade(l.quantidade, l.unidade)}.`)
            }} />
        )}
      </div>
    )
  }

  const deHoje = (lancamentos ?? []).filter((l) => l.data === hoje)
  const deOntem = (lancamentos ?? []).filter((l) => l.data !== hoje)
  return (
    <div className="rcb">
      <header className="rcb-cabecalho">
        <button type="button" className="rcb-voltar" onClick={onVoltar}><Seta />Contagem</button>
        <h1>Perda</h1>
      </header>
      <main className="rcb-corpo rcb-corpo-com-rodape">
        <div aria-live="polite" className={aviso ? 'rcb-alerta rcb-alerta-sucesso' : 'rcb-so-leitor'}>{aviso}</div>
        {avisoOffline}
        {erroLista && !(erroLista === SEM_CONEXAO && !online) && (
          <div className="rcb-alerta rcb-alerta-erro" role="alert">{erroLista}</div>
        )}
        {lancamentos === null ? (
          carregando ? <p className="rcb-apoio">Carregando lançamentos…</p> : null
        ) : lancamentos.length === 0 ? (
          <div className="rcb-vazio">
            <p>
              Nenhuma perda lançada hoje nem ontem. Quando descartar um produto (vencido, avariado), lance aqui:
              a central usa isso para acertar a produção.
            </p>
          </div>
        ) : (
          <>
            <p className="rcb-apoio">Toque num lançamento para corrigir ou apagar (até o fim do dia seguinte).</p>
            <ListaDoDia titulo={`Hoje (${formatarDia(hoje)})`} lancamentos={deHoje} onAbrir={editar} />
            <ListaDoDia titulo={`Ontem (${formatarDia(ontem)})`} lancamentos={deOntem} onAbrir={editar} />
          </>
        )}
      </main>
      <footer className="rcb-rodape">
        <button type="button" className="rcb-botao rcb-botao-primario" onClick={novo} disabled={!online}>
          Lançar perda
        </button>
      </footer>
    </div>
  )
}
