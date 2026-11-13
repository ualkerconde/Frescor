/*
 * Visão geral: a primeira tela depois do login. Desenho do visual "Comando"
 * azul-noite e âmbar (D117, escolhido pelo Ualker em 13/11/2026, protótipo
 * em visual-d117/v3/v2-noite-painel), com SÓ dados reais.
 *
 * Só LÊ endpoints que já existem; nenhuma regra de negócio nova:
 *   - GET /producao/ordens?data=amanhã e /producao/ordens/{id}  -> manchete, ordem e produção por setor
 *   - GET /web/produtos?limit=200                               -> setor de cada produto
 *   - GET /web/acompanhamento (7 dias até ontem; e por loja)    -> acerto, perda, ruptura, previsto × vendido
 *   - GET /distribuicao/romaneios?data_entrega=hoje             -> entregas de hoje
 *   - GET /vendas e /perdas (7 dias, só os totais)              -> aviso de "nenhuma venda chegou"
 *   - GET /distribuicao/divergencias (7 dias)                   -> "Precisa de você"
 *
 * O que o protótipo tinha e ainda NÃO existe no sistema foi trocado por algo
 * real, sem inventar número:
 *   - Gantt de horário por setor: o sistema não guarda horário de produção.
 *     Virou "Produção de amanhã por setor" (quantidade por setor).
 *   - Mapa de calor loja × dia: o acerto do dia somado mistura os erros dos
 *     produtos (um a mais compensa outro a menos). Virou "Acerto por loja"
 *     na semana, com a mesma conta da tela de acompanhamento (1 − WAPE).
 *
 * Cada bloco carrega e falha sozinho: um erro num número não derruba a tela.
 * UN e KG nunca se somam (cada total mostra uma linha por unidade).
 */
import { useState, type ReactNode } from "react"
import { useQueries, useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { ArrowRight, CircleAlert, Factory, Info, TriangleAlert } from "lucide-react"
import { Link } from "react-router"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { apiJson } from "@/lib/api/cliente"
import type {
  Acompanhamento,
  ConsultaDiaria,
  DistribuicaoDoDia,
  Divergencias,
  LojaWeb,
  Me,
  OrdemDetalhe,
  OrdemResumo,
  OrdensDoDia,
  ProdutosWeb,
  SituacaoEntrega,
  Unidade,
} from "@/lib/api/tipos"
import {
  contar,
  dataIso,
  diaDaSemana,
  formatarData,
  formatarPercentual,
  formatarQuantidade,
  somarDias,
} from "@/lib/formato"
import { COR_VENDIDO, GraficoDias } from "./acompanhamento/GraficoDias"

const dataPorExtenso = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })

/** Lojas consultadas uma a uma no "Acerto por loja" (o piloto tem poucas). */
const MAXIMO_LOJAS = 12

function saudacao(hora: number): string {
  if (hora < 12) return "Bom dia"
  if (hora < 18) return "Boa tarde"
  return "Boa noite"
}

/** Ordem das situações na barra de entregas e o que cada cor quer dizer (cor nunca sozinha: há legenda). */
const SITUACOES: { chave: SituacaoEntrega; rotulo: string; cor: string }[] = [
  { chave: "recebida", rotulo: "Recebidas", cor: "bg-success" },
  { chave: "confirmada_com_atraso", rotulo: "Confirmadas com atraso", cor: "bg-primary" },
  { chave: "a_caminho", rotulo: "A caminho", cor: "bg-azul" },
  { chave: "aguardando_saida", rotulo: "Aguardando saída", cor: "bg-input-border" },
  { chave: "sem_confirmacao", rotulo: "Sem confirmação", cor: "bg-warning" },
]

type UnidadeAcomp = Acompanhamento["unidades"][number]

/** UN primeiro (é a unidade da maioria dos itens de padaria); KG em seguida. */
function principal<T extends { unidade: Unidade }>(lista: T[]): T | undefined {
  return lista.find((u) => u.unidade === "UN") ?? lista[0]
}

function acertoDe(u: UnidadeAcomp | undefined): number | null {
  if (!u?.erro.wape) return null
  return Math.max(0, 1 - Number(u.erro.wape))
}

/* ------------------------------------------------------------ peças visuais */

function Cartao({
  titulo,
  detalhe,
  className,
  children,
}: {
  titulo: string
  detalhe?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section aria-label={titulo} className={cn("painel flex h-full min-w-0 flex-col rounded-2xl px-5 py-4", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-sans text-[15px] font-semibold text-foreground">{titulo}</h2>
        {detalhe && <span className="text-right text-[13px] text-muted-foreground">{detalhe}</span>}
      </div>
      {children}
    </section>
  )
}

function Estado({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground">{children}</p>
}

/** Linha curta (sparkline) só para dar a forma da semana; o número exato está no cartão e nas telas. */
function Faisca({ valores, cor = "var(--fr-primary)" }: { valores: (number | null)[]; cor?: string }) {
  const pontos = valores.map((v, i) => ({ v, i })).filter((p): p is { v: number; i: number } => p.v !== null)
  if (pontos.length < 2) return null
  const max = Math.max(...pontos.map((p) => p.v))
  const min = Math.min(...pontos.map((p) => p.v))
  const faixa = max - min || 1
  const n = valores.length - 1 || 1
  const linha = pontos.map((p) => `${(p.i / n) * 220},${40 - ((p.v - min) / faixa) * 32}`).join(" ")
  return (
    <svg aria-hidden="true" className="mt-3 h-9 w-full" viewBox="0 0 220 44" preserveAspectRatio="none">
      <polyline fill="none" stroke={cor} strokeWidth="2" vectorEffect="non-scaling-stroke" points={linha} />
    </svg>
  )
}

function Valor({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("numero-destaque text-[34px] leading-tight", className)}>{children}</p>
}

/* ------------------------------------------------------------------ cartões */

function CartaoAcerto({ consulta }: { consulta: { data?: Acompanhamento; isPending: boolean; isError: boolean } }) {
  const u = principal(consulta.data?.unidades ?? [])
  const acerto = acertoDe(u)
  const vies = u?.erro.vies ? Number(u.erro.vies) : null
  return (
    <Cartao titulo="Acerto da previsão" detalhe="7 dias" className="lg:col-span-3">
      {consulta.isPending ? (
        <Estado>Carregando…</Estado>
      ) : consulta.isError ? (
        <Estado>Não foi possível carregar.</Estado>
      ) : acerto === null || !u ? (
        <Estado>Sem previsão com venda na semana.</Estado>
      ) : (
        <>
          <Valor>{formatarPercentual(acerto)}</Valor>
          <p className="text-[13px] text-muted-foreground">
            {vies === null || Math.abs(vies) < 0.005
              ? "sem viés: não previu a mais nem a menos"
              : `previu ${formatarPercentual(Math.abs(vies))} a ${vies > 0 ? "mais" : "menos"}`}{" "}
            · em {u.unidade === "KG" ? "kg" : "un"}
          </p>
          {/* Barra de acerto: 0 a 100%, sem cor de status (o número é que fala). */}
          <div aria-hidden="true" className="mt-4 h-2 overflow-hidden rounded-full bg-surface">
            <span className="block h-full rounded-full bg-primary" style={{ width: `${acerto * 100}%` }} />
          </div>
        </>
      )}
    </Cartao>
  )
}

function CartaoPerda({ consulta }: { consulta: { data?: Acompanhamento; isPending: boolean; isError: boolean } }) {
  const u = principal(consulta.data?.unidades ?? [])
  const perda = u?.totais.perda ? Number(u.totais.perda) : null
  const vendido = u?.totais.vendido ? Number(u.totais.vendido) : null
  return (
    <Cartao titulo="Perda" detalhe="% do vendido" className="lg:col-span-3">
      {consulta.isPending ? (
        <Estado>Carregando…</Estado>
      ) : consulta.isError ? (
        <Estado>Não foi possível carregar.</Estado>
      ) : perda === null || !u ? (
        <Estado>Nenhuma perda lançada na semana.</Estado>
      ) : (
        <>
          <Valor>{vendido ? formatarPercentual(perda / vendido) : formatarQuantidade(perda, u.unidade)}</Valor>
          <p className="text-[13px] text-muted-foreground">
            {formatarQuantidade(perda, u.unidade)} perdidos em 7 dias
          </p>
          <Faisca valores={u.dias.map((d) => (d.perda === null ? null : Number(d.perda)))} cor={COR_VENDIDO} />
        </>
      )}
    </Cartao>
  )
}

function CartaoRuptura({ consulta }: { consulta: { data?: Acompanhamento; isPending: boolean; isError: boolean } }) {
  const unidades = consulta.data?.unidades ?? []
  const rupturas = unidades.reduce((s, u) => s + u.rupturas, 0)
  const balancos = unidades.reduce((s, u) => s + u.balancos, 0)
  const produtos = (consulta.data?.produtos ?? [])
    .filter((p) => p.rupturas > 0)
    .sort((a, b) => b.rupturas - a.rupturas)
    .slice(0, 2)
  return (
    <Cartao titulo="Ruptura" detalhe="produto acabou na loja" className="lg:col-span-3">
      {consulta.isPending ? (
        <Estado>Carregando…</Estado>
      ) : consulta.isError ? (
        <Estado>Não foi possível carregar.</Estado>
      ) : balancos === 0 ? (
        <Estado>Sem contagem para medir na semana.</Estado>
      ) : (
        <>
          <Valor>{rupturas}</Valor>
          <p className="text-[13px] text-muted-foreground">
            {rupturas === 0
              ? `nenhuma em ${contar(balancos, "contagem", "contagens")}`
              : produtos.map((p, i) => (
                  <span key={p.produto.id}>
                    {i > 0 && " · "}
                    <span className="font-semibold text-error">{p.produto.nome}</span> {contar(p.rupturas, "vez", "vezes")}
                  </span>
                ))}
          </p>
          <div aria-hidden="true" className="mt-4 flex h-2 gap-1">
            <span className="rounded-full bg-error" style={{ flexGrow: rupturas }} />
            <span className="rounded-full bg-surface" style={{ flexGrow: balancos - rupturas }} />
          </div>
        </>
      )}
    </Cartao>
  )
}

function CartaoEntregas({ consulta }: { consulta: { data?: DistribuicaoDoDia; isPending: boolean; isError: boolean } }) {
  const romaneios = (consulta.data?.ordens ?? []).flatMap((o) => (o.romaneio ? [o.romaneio] : []))
  const total = romaneios.reduce((s, r) => s + r.entregas, 0)
  const contagem = SITUACOES.map((s) => ({
    ...s,
    quantidade: romaneios.reduce((soma, r) => soma + (r.situacoes[s.chave] ?? 0), 0),
  })).filter((s) => s.quantidade > 0)
  const recebidas = contagem
    .filter((s) => s.chave === "recebida" || s.chave === "confirmada_com_atraso")
    .reduce((soma, s) => soma + s.quantidade, 0)

  return (
    <Cartao titulo="Entregas de hoje" detalhe="romaneios" className="lg:col-span-3">
      {consulta.isPending ? (
        <Estado>Carregando…</Estado>
      ) : consulta.isError ? (
        <Estado>Não foi possível carregar as entregas.</Estado>
      ) : total === 0 ? (
        <Estado>Nenhum romaneio com entrega para hoje.</Estado>
      ) : (
        <>
          <Valor>
            {recebidas}
            <span className="text-2xl text-muted-foreground">/{total}</span>
            <span className="sr-only"> lojas receberam</span>
          </Valor>
          <div aria-hidden="true" className="mt-2 flex h-2 gap-1">
            {contagem.map((s) => (
              <span key={s.chave} className={cn("rounded-full", s.cor)} style={{ flexGrow: s.quantidade }} />
            ))}
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[13px] text-muted-foreground">
            {contagem.map((s) => (
              <li key={s.chave} className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className={cn("size-2 rounded-full", s.cor)} />
                {s.rotulo}: <span className="font-semibold text-foreground tabular-nums">{s.quantidade}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Cartao>
  )
}

/* ----------------------------------------------- produção de amanhã por setor */

interface Setor {
  nome: string
  totais: Map<Unidade, number>
  produtos: { nome: string; quantidade: number; unidade: Unidade }[]
}

function porSetor(ordem: OrdemDetalhe, setorDe: Map<number, string | null>): Setor[] {
  const setores = new Map<string, Setor>()
  for (const item of ordem.itens) {
    const final = Number(item.total_final)
    if (!final) continue
    const nome = setorDe.get(item.produto.id) ?? "Sem setor"
    const s: Setor = setores.get(nome) ?? { nome, totais: new Map(), produtos: [] }
    s.totais.set(item.unidade, (s.totais.get(item.unidade) ?? 0) + final)
    s.produtos.push({ nome: item.produto.nome, quantidade: final, unidade: item.unidade })
    setores.set(nome, s)
  }
  return [...setores.values()].sort((a, b) => (b.totais.get("UN") ?? 0) - (a.totais.get("UN") ?? 0))
}

function ProducaoPorSetor({ ordem, amanha }: { ordem: OrdemResumo | null | undefined; amanha: string }) {
  const detalhe = useQuery({
    queryKey: ["inicio", "ordem", ordem?.id],
    queryFn: () => apiJson<OrdemDetalhe>(`/producao/ordens/${ordem?.id}`),
    enabled: !!ordem,
  })
  const produtos = useQuery({
    queryKey: ["inicio", "produtos"],
    queryFn: () => apiJson<ProdutosWeb>("/web/produtos?limit=200&offset=0"),
    enabled: !!ordem,
  })
  const setorDe = new Map((produtos.data?.itens ?? []).map((p) => [p.id, p.setor ?? null]))
  const setores = detalhe.data ? porSetor(detalhe.data, setorDe) : []
  const maiorPor = (u: Unidade) => Math.max(1, ...setores.map((s) => s.totais.get(u) ?? 0))

  return (
    <Cartao
      titulo={`Produção de ${diaDaSemana(amanha)} por setor`}
      detalhe={
        ordem ? (
          <Link to={`/producao?data=${amanha}`} className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
            Abrir produção
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        ) : undefined
      }
      className="lg:col-span-7"
    >
      {ordem === undefined ? (
        <Estado>Carregando…</Estado>
      ) : ordem === null ? (
        <Estado>Sem ordem gerada para amanhã.</Estado>
      ) : detalhe.isPending || produtos.isPending ? (
        <Estado>Carregando…</Estado>
      ) : detalhe.isError ? (
        <Estado>Não foi possível carregar a ordem.</Estado>
      ) : setores.length === 0 ? (
        <Estado>Nada a produzir.</Estado>
      ) : (
        <ul className="flex flex-col">
          {setores.map((s) => {
            const u: Unidade = s.totais.has("UN") ? "UN" : "KG"
            const destaque = [...s.produtos].sort((a, b) => b.quantidade - a.quantidade).slice(0, 3)
            return (
              <li
                key={s.nome}
                className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-2 first:border-t-0"
              >
                <span className="truncate font-semibold">{s.nome}</span>
                <span className="relative h-7 min-w-0 rounded-md bg-background">
                  <span
                    aria-hidden="true"
                    className="absolute inset-y-0 left-0 rounded-md bg-primary/20 shadow-[inset_3px_0_0_var(--fr-primary)]"
                    style={{ width: `${Math.max(6, ((s.totais.get(u) ?? 0) / maiorPor(u)) * 100)}%` }}
                  />
                  <span className="relative block truncate px-2.5 text-[13px] leading-7 text-foreground">
                    {destaque.map((p) => `${p.nome} ${formatarQuantidade(p.quantidade, p.unidade)}`).join(" · ")}
                  </span>
                </span>
                <span className="text-right font-mono text-sm font-semibold whitespace-nowrap tabular-nums">
                  {[...s.totais.entries()].map(([un, q]) => formatarQuantidade(q, un)).join(" · ")}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </Cartao>
  )
}

/* --------------------------------------------------------- acerto por loja */

function AcertoPorLoja({ inicio, fim }: { inicio: string; fim: string }) {
  const lojas = useQuery({ queryKey: ["lojas"], queryFn: () => apiJson<LojaWeb[]>("/web/lojas") })
  const ativas = (lojas.data ?? []).filter((l) => l.ativo).slice(0, MAXIMO_LOJAS)
  const porLoja = useQueries({
    queries: ativas.map((l) => ({
      queryKey: ["inicio", "acompanhamento", inicio, fim, l.id],
      queryFn: () =>
        apiJson<Acompanhamento>(`/web/acompanhamento?data_inicio=${inicio}&data_fim=${fim}&loja_id=${l.id}`),
    })),
  })

  return (
    <Cartao titulo="Acerto por loja" detalhe="7 dias · 1 − erro da previsão" className="lg:col-span-7">
      {lojas.isPending ? (
        <Estado>Carregando…</Estado>
      ) : lojas.isError ? (
        <Estado>Não foi possível carregar as lojas.</Estado>
      ) : ativas.length === 0 ? (
        <Estado>Nenhuma loja ativa.</Estado>
      ) : (
        <ul className="flex flex-col">
          {ativas.map((l, i) => {
            const c = porLoja[i]
            const acerto = acertoDe(principal(c?.data?.unidades ?? []))
            return (
              <li
                key={l.id}
                className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_4.5rem] items-center gap-3 border-t border-line py-2 first:border-t-0"
              >
                <span className="truncate text-sm">
                  {l.codigo && <span className="font-mono text-muted-foreground">{l.codigo} </span>}
                  {l.nome}
                </span>
                <span aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-surface">
                  {acerto !== null && (
                    <span className="block h-full rounded-full bg-azul" style={{ width: `${acerto * 100}%` }} />
                  )}
                </span>
                <span className="text-right font-mono text-sm font-semibold tabular-nums">
                  {c?.isPending ? "…" : c?.isError ? "—" : acerto === null ? "sem dado" : formatarPercentual(acerto)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </Cartao>
  )
}

/* ------------------------------------------------------- precisa de você */

interface Pendencia {
  chave: string
  gravidade: "erro" | "aviso" | "info"
  etiqueta: string
  titulo: ReactNode
  detalhe: string
  para: string
}

const ESTILO_PENDENCIA = {
  erro: { classe: "bg-error-bg text-error", Icone: CircleAlert },
  aviso: { classe: "bg-warning-bg text-warning", Icone: TriangleAlert },
  info: { classe: "bg-highlight-bg text-highlight", Icone: Info },
} as const

function PrecisaDeVoce({ pendencias, carregando }: { pendencias: Pendencia[]; carregando: boolean }) {
  return (
    <Cartao
      titulo="Precisa de você"
      detalhe={carregando ? "carregando…" : contar(pendencias.length, "item", "itens")}
      className="lg:col-span-5"
    >
      {pendencias.length === 0 ? (
        <Estado>{carregando ? "Conferindo a central…" : "Nada pendente agora."}</Estado>
      ) : (
        <ul className="flex flex-col">
          {pendencias.map((p) => {
            const { classe, Icone } = ESTILO_PENDENCIA[p.gravidade]
            return (
              <li key={p.chave} className="flex items-start gap-3 border-t border-line py-2.5 first:border-t-0">
                <span
                  className={cn(
                    "mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold",
                    classe,
                  )}
                >
                  <Icone className="size-3.5" aria-hidden="true" />
                  {p.etiqueta}
                </span>
                <div className="min-w-0">
                  <Link to={p.para} className="font-semibold hover:underline">
                    {p.titulo}
                  </Link>
                  <p className="text-[13px] text-muted-foreground">{p.detalhe}</p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Cartao>
  )
}

/* ------------------------------------------------------------------ tela */

export function Inicio() {
  // "Agora" fixado na abertura da tela: a saudação e as datas não mudam a cada renderização.
  const [agora] = useState(() => new Date())
  const hoje = dataIso(agora)
  const amanha = somarDias(hoje, 1)
  const inicio7 = somarDias(hoje, -7)
  const ontem = somarDias(hoje, -1)

  const me = useQuery({ queryKey: ["me"], queryFn: () => apiJson<Me>("/web/me") })
  const ordens = useQuery({
    queryKey: ["inicio", "ordens", amanha],
    queryFn: () => apiJson<OrdensDoDia>(`/producao/ordens?data=${amanha}`),
  })
  const acompanhamento = useQuery({
    queryKey: ["inicio", "acompanhamento", inicio7, ontem],
    queryFn: () => apiJson<Acompanhamento>(`/web/acompanhamento?data_inicio=${inicio7}&data_fim=${ontem}`),
  })
  const romaneios = useQuery({
    queryKey: ["inicio", "romaneios", hoje],
    queryFn: () => apiJson<DistribuicaoDoDia>(`/distribuicao/romaneios?data_entrega=${hoje}`),
  })
  const vendas = useQuery({
    queryKey: ["inicio", "vendas", inicio7, ontem],
    queryFn: () => apiJson<ConsultaDiaria>(`/vendas?data_inicio=${inicio7}&data_fim=${ontem}&limit=1&offset=0`),
  })
  const divergencias = useQuery({
    queryKey: ["inicio", "divergencias", inicio7, hoje],
    queryFn: () => apiJson<Divergencias>(`/distribuicao/divergencias?data_inicio=${inicio7}&data_fim=${hoje}`),
  })

  const primeiroNome = me.data?.usuario.nome.trim().split(/\s+/)[0]
  const lista = ordens.data?.ordens ?? []
  // undefined = carregando ou erro; null = não gerada.
  const ordem = ordens.data ? (lista.find((o) => o.tipo === "programada") ?? null) : undefined
  const emergenciais = lista.filter((o) => o.tipo === "emergencial").length
  const totais = (ordem?.totais ?? []).filter((t) => Number(t.final) !== 0)
  const semVendas = vendas.isSuccess && vendas.data.totais.every((t) => Number(t.quantidade) === 0)
  const diaAmanha = `${diaDaSemana(amanha)}, ${formatarData(amanha).slice(0, 5)}`

  // "Precisa de você": só o que já carregou; nada inventado.
  const pendencias: Pendencia[] = []
  if (ordem === null)
    pendencias.push({
      chave: "ordem",
      gravidade: "aviso",
      etiqueta: "Ordem",
      titulo: `Gerar a ordem de ${diaAmanha}`,
      detalhe: "Ela sai da previsão, da contagem das lojas e do que está a caminho.",
      para: `/producao?data=${amanha}`,
    })
  else if (ordem?.status === "rascunho")
    pendencias.push({
      chave: "ordem",
      gravidade: "info",
      etiqueta: "Ordem",
      titulo: `Aprovar a ordem de ${diaAmanha}`,
      detalhe:
        ordem.linhas_sem_quantidade > 0
          ? `Está em rascunho, com ${contar(ordem.linhas_sem_quantidade, "linha", "linhas")} sem sugestão.`
          : "Está em rascunho. Confira e aprove para liberar o romaneio.",
      para: `/producao?data=${amanha}`,
    })
  const semConfirmacao = (romaneios.data?.ordens ?? []).reduce(
    (s, o) => s + (o.romaneio?.situacoes.sem_confirmacao ?? 0),
    0,
  )
  if (semConfirmacao > 0)
    pendencias.push({
      chave: "confirmacao",
      gravidade: "aviso",
      etiqueta: "Entrega",
      titulo: `${contar(semConfirmacao, "loja", "lojas")} sem confirmar o recebimento`,
      detalhe: "A loja confirma no app. Sem a confirmação, a entrega conta como chegada no dia.",
      para: "/distribuicao",
    })
  const qtdDivergencias = divergencias.data?.divergencias.length ?? 0
  if (qtdDivergencias > 0)
    pendencias.push({
      chave: "divergencias",
      gravidade: "aviso",
      etiqueta: "Recebimento",
      titulo: `${contar(qtdDivergencias, "divergência", "divergências")} de recebimento`,
      detalhe: "Itens recebidos diferente do enviado, nos últimos 7 dias.",
      para: "/distribuicao",
    })
  const rupturas = (acompanhamento.data?.unidades ?? []).reduce((s, u) => s + u.rupturas, 0)
  if (rupturas > 0)
    pendencias.push({
      chave: "rupturas",
      gravidade: "erro",
      etiqueta: "Ruptura",
      titulo: `Produto acabou na loja ${contar(rupturas, "vez", "vezes")}`,
      detalhe: "Na semana, pela contagem de fechamento. Veja quais no acompanhamento.",
      para: "/acompanhamento",
    })
  if (semVendas)
    pendencias.push({
      chave: "vendas",
      gravidade: "erro",
      etiqueta: "Vendas",
      titulo: "Nenhuma venda chegou nos últimos 7 dias",
      detalhe: "A previsão e a ordem usam a venda diária. Veja a integração de vendas.",
      para: "/integracao",
    })
  const carregando = ordens.isPending || romaneios.isPending || divergencias.isPending || acompanhamento.isPending

  const uGrafico = principal(acompanhamento.data?.unidades ?? [])

  return (
    <section className="flex flex-col gap-5">
      {/* Manchete: saudação e o que a central produz amanhã (números em âmbar). */}
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0">
          <p className="text-xs tracking-[0.14em] text-muted-foreground uppercase">
            {dataPorExtenso.format(agora)}
            {me.data && ` · ${me.data.central.nome}`}
          </p>
          <h1 className="mt-1 text-[28px] leading-tight font-semibold tracking-[-0.03em] sm:text-[34px]">
            {primeiroNome ? `${saudacao(agora.getHours())}, ${primeiroNome}` : saudacao(agora.getHours())}
          </h1>
          <p className="text-[22px] leading-tight font-semibold tracking-[-0.03em] text-muted-foreground sm:text-[28px]">
            {ordem === undefined ? (
              ordens.isError ? (
                "Não foi possível carregar a ordem de amanhã."
              ) : (
                "Carregando a ordem de amanhã…"
              )
            ) : ordem === null ? (
              "A ordem de amanhã ainda não foi gerada."
            ) : totais.length === 0 ? (
              "Amanhã a central não tem nada a produzir."
            ) : (
              <>
                Amanhã a central produz{" "}
                {totais.map((t, i) => (
                  <span key={t.unidade}>
                    {i > 0 && " e "}
                    <b className="font-mono font-semibold text-primary">{formatarQuantidade(t.final, t.unidade)}</b>
                  </span>
                ))}
                .
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {ordem !== undefined && (
            <span className="inline-flex items-center gap-2 rounded-full border border-line px-3.5 py-2 text-[13px] text-muted-foreground">
              <span
                aria-hidden="true"
                className={cn("size-2 rounded-full", ordem?.status === "aprovada" ? "bg-success" : "bg-primary")}
              />
              {ordem === null
                ? "Ordem não gerada"
                : ordem.status === "aprovada"
                  ? "Ordem aprovada"
                  : "Ordem em rascunho"}
              {emergenciais > 0 && ` · mais ${contar(emergenciais, "emergencial", "emergenciais")}`}
            </span>
          )}
          <Link to={`/producao?data=${amanha}`} className={cn(buttonVariants())}>
            <Factory aria-hidden="true" />
            {ordem?.status === "rascunho" ? `Revisar ordem de ${diaDaSemana(amanha)}` : "Ver ordem de amanhã"}
          </Link>
        </div>
      </div>

      {semVendas && (
        <Alert variant="aviso">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Nenhuma venda chegou nos últimos 7 dias.</AlertTitle>
          <AlertDescription className="text-current">
            A previsão e a ordem de produção usam a venda diária das lojas.{" "}
            <Link to="/integracao" className="font-semibold underline underline-offset-2">
              Veja a integração de vendas
            </Link>
            .
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-12">
        <CartaoAcerto consulta={acompanhamento} />
        <CartaoPerda consulta={acompanhamento} />
        <CartaoRuptura consulta={acompanhamento} />
        <CartaoEntregas consulta={romaneios} />

        <div className="sm:col-span-2 lg:col-span-7">
          <ProducaoPorSetor ordem={ordem} amanha={amanha} />
        </div>

        <Cartao titulo="Previsto × vendido" detalhe="7 dias" className="sm:col-span-2 lg:col-span-5">
          {acompanhamento.isPending ? (
            <Estado>Carregando…</Estado>
          ) : acompanhamento.isError ? (
            <Estado>Não foi possível carregar.</Estado>
          ) : !uGrafico ? (
            <Estado>Sem previsão nem venda na semana.</Estado>
          ) : (
            <>
              <GraficoDias
                titulo={`Por dia, em ${uGrafico.unidade === "KG" ? "kg" : "un"}`}
                ondeEstaATabela="Valores dia a dia na tela de acompanhamento."
                largura={460}
                unidade={uGrafico.unidade}
                pontos={uGrafico.dias.map((d) => ({
                  data: d.data,
                  previsto: d.previsto === null ? null : Number(d.previsto),
                  vendido: d.vendido === null ? null : Number(d.vendido),
                }))}
              />
              <Link
                to="/acompanhamento"
                className="mt-2 inline-flex items-center gap-1 self-start text-sm font-semibold text-primary hover:underline"
              >
                Abrir acompanhamento
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </>
          )}
        </Cartao>

        <div className="sm:col-span-2 lg:col-span-7">
          <AcertoPorLoja inicio={inicio7} fim={ontem} />
        </div>
        <div className="sm:col-span-2 lg:col-span-5">
          <PrecisaDeVoce pendencias={pendencias} carregando={carregando} />
        </div>
      </div>
    </section>
  )
}
