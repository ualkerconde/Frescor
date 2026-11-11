/*
 * Visão geral (padrão de 11/11/2026, a partir da referência que o sócio do
 * Ualker mandou): a primeira tela depois do login. Saudação com o nome do
 * gestor, uma linha do que está acontecendo agora e os números do dia.
 *
 * Só LÊ endpoints que já existem; nenhuma regra de negócio nova:
 *   - GET /producao/ordens?data=amanhã        -> painel escuro (ordem de amanhã)
 *   - GET /distribuicao/romaneios?data_entrega=hoje -> entregas de hoje
 *   - GET /vendas e /perdas (últimos 7 dias, até ontem; só os totais)
 *   - GET /distribuicao/divergencias (últimos 7 dias, até hoje)
 *
 * Cada bloco carrega e falha sozinho: um erro num número não derruba a tela.
 * UN e KG nunca se somam (cada total mostra uma linha por unidade).
 */
import { useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { ArrowRight, ChartLine, Factory, PackageCheck, ShoppingBasket, Trash2, TriangleAlert, Truck } from "lucide-react"
import { Link } from "react-router"
import { CabecalhoPagina } from "@/components/layout/CabecalhoPagina"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { apiJson } from "@/lib/api/cliente"
import type {
  ConsultaDiaria,
  DistribuicaoDoDia,
  Divergencias,
  Me,
  OrdensDoDia,
  SituacaoEntrega,
  TotalPorUnidade,
} from "@/lib/api/tipos"
import {
  contar,
  dataIso,
  diaDaSemana,
  formatarData,
  formatarPercentual,
  formatarQuantidade,
  formatarVariacao,
  somarDias,
} from "@/lib/formato"

const dataPorExtenso = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })

function saudacao(hora: number): string {
  if (hora < 12) return "Bom dia"
  if (hora < 18) return "Boa tarde"
  return "Boa noite"
}

/** Ordem das situações na barra de entregas e o que cada cor quer dizer (cor nunca sozinha: há legenda). */
const SITUACOES: { chave: SituacaoEntrega; rotulo: string; cor: string }[] = [
  { chave: "recebida", rotulo: "Recebidas", cor: "bg-success" },
  { chave: "confirmada_com_atraso", rotulo: "Confirmadas com atraso", cor: "bg-primary" },
  { chave: "a_caminho", rotulo: "A caminho", cor: "bg-highlight" },
  { chave: "aguardando_saida", rotulo: "Aguardando saída", cor: "bg-input-border" },
  { chave: "sem_confirmacao", rotulo: "Sem confirmação", cor: "bg-warning" },
]

function totaisDa(consulta: { data?: ConsultaDiaria }): TotalPorUnidade[] {
  return (consulta.data?.totais ?? []).filter((t) => Number(t.quantidade) !== 0)
}

/* ------------------------------------------------------------------ blocos */

function CartaoKpi({
  titulo,
  Icone,
  link,
  children,
}: {
  titulo: string
  Icone: typeof Truck
  link?: { para: string; rotulo: string }
  children: ReactNode
}) {
  return (
    <section aria-label={titulo} className="painel-kpi flex flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-sans text-[15px] font-semibold text-foreground">{titulo}</h2>
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-md bg-surface text-primary">
          <Icone className="size-[18px]" />
        </span>
      </div>
      <div className="mt-2 flex flex-1 flex-col">{children}</div>
      {link && (
        <Link
          to={link.para}
          className="mt-4 inline-flex items-center gap-1 self-start text-sm font-semibold text-primary hover:underline"
        >
          {link.rotulo}
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      )}
    </section>
  )
}

function Totais({ totais, tamanho = "text-[30px]" }: { totais: TotalPorUnidade[]; tamanho?: string }) {
  return (
    <ul>
      {totais.map((t, i) => (
        <li
          key={t.unidade}
          className={cn(
            "numero-destaque leading-tight whitespace-nowrap",
            i === 0 ? tamanho : "text-lg text-muted-foreground",
          )}
        >
          {formatarQuantidade(t.quantidade, t.unidade)}
        </li>
      ))}
    </ul>
  )
}

function Estado({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground">{children}</p>
}

/* ------------------------------------------------------- painel da ordem */

function PainelOrdem({ amanha }: { amanha: string }) {
  const consulta = useQuery({
    queryKey: ["inicio", "ordens", amanha],
    queryFn: () => apiJson<OrdensDoDia>(`/producao/ordens?data=${amanha}`),
  })
  const ordens = consulta.data?.ordens ?? []
  const ordem = ordens.find((o) => o.tipo === "programada") ?? null
  const emergenciais = ordens.filter((o) => o.tipo === "emergencial").length
  const totais = (ordem?.totais ?? []).filter((t) => Number(t.final) !== 0)

  return (
    <section
      aria-label="Ordem de produção de amanhã"
      className="flex flex-col overflow-hidden rounded-xl bg-heading text-white lg:col-span-3"
    >
      <div className="flex flex-1 flex-col p-6">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <h2 className="flex items-center gap-2 font-sans text-xs font-semibold tracking-[0.08em] text-ink-muted uppercase">
            <Factory className="size-4 text-highlight" aria-hidden="true" />
            Ordem de produção · {diaDaSemana(amanha)}, {formatarData(amanha).slice(0, 5)}
          </h2>
          <Link
            to={`/producao?data=${amanha}`}
            className="inline-flex items-center gap-1 text-sm font-semibold whitespace-nowrap text-highlight hover:underline focus-visible:outline-white"
          >
            Abrir produção
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>

        {consulta.isPending ? (
          <p className="mt-6 text-ink-muted">Carregando a ordem…</p>
        ) : consulta.isError ? (
          <p className="mt-6 text-ink-muted">Não foi possível carregar a ordem de amanhã.</p>
        ) : !ordem ? (
          <div className="mt-6">
            <p className="font-heading text-[32px] leading-tight font-semibold">Ainda não gerada</p>
            <p className="mt-2 max-w-md text-ink-muted">
              A ordem de amanhã sai da previsão, da contagem das lojas e do que está a caminho. Gere e confira na tela de
              produção.
            </p>
          </div>
        ) : (
          <div className="mt-5">
            <span
              className={cn(
                "inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-semibold",
                ordem.status === "aprovada" ? "bg-success-bg text-success" : "bg-highlight text-foreground",
              )}
            >
              {ordem.status === "aprovada" ? "Aprovada" : "Em rascunho"}
            </span>
            {totais.length === 0 ? (
              <p className="mt-3 font-heading text-[32px] leading-tight font-semibold">Nada a produzir</p>
            ) : (
              <ul className="mt-3">
                {totais.map((t, i) => (
                  <li
                    key={t.unidade}
                    className={cn(
                      "font-heading leading-tight font-semibold tracking-[-0.02em] whitespace-nowrap tabular-nums",
                      i === 0 ? "text-[44px]" : "text-2xl text-ink-muted",
                    )}
                  >
                    {formatarQuantidade(t.final, t.unidade)}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-sm text-ink-muted">
              Total a produzir para entregar em {formatarData(ordem.data_entrega)}
              {emergenciais > 0 && ` · mais ${contar(emergenciais, "ordem emergencial", "ordens emergenciais")}`}
            </p>
          </div>
        )}

        {/* Sugerido pelo sistema x final do gestor, por unidade (só leitura dos totais da ordem). */}
        {ordem && totais.length > 0 && (
          <div className="mt-auto pt-8">
            <h3 className="font-sans text-xs font-semibold tracking-[0.08em] text-ink-muted uppercase">
              Sugerido pelo sistema × final
            </h3>
            <ul className="mt-3 flex flex-col gap-3">
              {totais.map((t) => {
                const sugerido = Number(t.sugerido)
                const final = Number(t.final)
                const maior = Math.max(sugerido, final) || 1
                return (
                  <li key={t.unidade} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5">
                    <div aria-hidden="true" className="flex flex-col gap-1">
                      <span className="h-1.5 rounded-full bg-white/20" style={{ width: `${(sugerido / maior) * 100}%` }} />
                      <span className="h-1.5 rounded-full bg-highlight" style={{ width: `${(final / maior) * 100}%` }} />
                    </div>
                    <p className="text-sm text-ink-muted tabular-nums">
                      {formatarQuantidade(sugerido, t.unidade)} →{" "}
                      <span className="font-semibold text-white">{formatarQuantidade(final, t.unidade)}</span>
                      {sugerido > 0 && final !== sugerido && (
                        <span> ({formatarVariacao(final / sugerido)})</span>
                      )}
                    </p>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>

      {ordem && (
        <dl className="grid grid-cols-3 border-t border-ink-line">
          {[
            { rotulo: "Linhas (loja × produto)", valor: ordem.linhas },
            { rotulo: "Ajustadas pelo gestor", valor: ordem.linhas_editadas },
            { rotulo: "Sem sugestão", valor: ordem.linhas_sem_quantidade },
          ].map(({ rotulo, valor }, i) => (
            <div key={rotulo} className={cn("px-6 py-4", i > 0 && "border-l border-ink-line")}>
              <dt className="text-xs text-ink-muted">{rotulo}</dt>
              <dd className="mt-0.5 font-heading text-xl font-semibold tabular-nums">{valor}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

/* ------------------------------------------------------- entregas de hoje */

function CartaoEntregas({ hoje }: { hoje: string }) {
  const consulta = useQuery({
    queryKey: ["inicio", "romaneios", hoje],
    queryFn: () => apiJson<DistribuicaoDoDia>(`/distribuicao/romaneios?data_entrega=${hoje}`),
  })
  const romaneios = (consulta.data?.ordens ?? []).flatMap((o) => (o.romaneio ? [o.romaneio] : []))
  const total = romaneios.reduce((s, r) => s + r.entregas, 0)
  const contagem = SITUACOES.map((s) => ({
    ...s,
    quantidade: romaneios.reduce((soma, r) => soma + (r.situacoes[s.chave] ?? 0), 0),
  })).filter((s) => s.quantidade > 0)

  return (
    <CartaoKpi titulo="Entregas de hoje" Icone={Truck} link={{ para: "/distribuicao", rotulo: "Ver distribuição" }}>
      {consulta.isPending ? (
        <Estado>Carregando…</Estado>
      ) : consulta.isError ? (
        <Estado>Não foi possível carregar as entregas.</Estado>
      ) : total === 0 ? (
        <Estado>Nenhum romaneio com entrega para hoje.</Estado>
      ) : (
        <>
          <p className="numero-destaque text-[30px] leading-tight">
            {total} <span className="font-sans text-base font-normal text-muted-foreground">{total === 1 ? "loja" : "lojas"}</span>
          </p>
          <div aria-hidden="true" className="mt-3 flex h-2 gap-1 overflow-hidden rounded-full">
            {contagem.map((s) => (
              <span key={s.chave} className={cn("h-full rounded-full", s.cor)} style={{ flexGrow: s.quantidade }} />
            ))}
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
            {contagem.map((s) => (
              <li key={s.chave} className="inline-flex items-center gap-1.5">
                <span aria-hidden="true" className={cn("size-2 rounded-full", s.cor)} />
                {s.rotulo}: <span className="font-semibold text-foreground tabular-nums">{s.quantidade}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </CartaoKpi>
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
  const vendas = useQuery({
    queryKey: ["inicio", "vendas", inicio7, ontem],
    queryFn: () => apiJson<ConsultaDiaria>(`/vendas?data_inicio=${inicio7}&data_fim=${ontem}&limit=1&offset=0`),
  })
  const perdas = useQuery({
    queryKey: ["inicio", "perdas", inicio7, ontem],
    queryFn: () => apiJson<ConsultaDiaria>(`/perdas?data_inicio=${inicio7}&data_fim=${ontem}&limit=1&offset=0`),
  })
  const divergencias = useQuery({
    queryKey: ["inicio", "divergencias", inicio7, hoje],
    queryFn: () => apiJson<Divergencias>(`/distribuicao/divergencias?data_inicio=${inicio7}&data_fim=${hoje}`),
  })
  const ordens = useQuery({
    queryKey: ["inicio", "ordens", amanha],
    queryFn: () => apiJson<OrdensDoDia>(`/producao/ordens?data=${amanha}`),
  })

  const primeiroNome = me.data?.usuario.nome.trim().split(/\s+/)[0]
  const totaisVendas = totaisDa(vendas)
  const totaisPerdas = totaisDa(perdas)
  const qtdDivergencias = divergencias.data?.divergencias.length

  // "Agora: ..." só com o que já carregou; nada inventado.
  const resumo: ReactNode[] = []
  if (ordens.data) {
    const ordem = ordens.data.ordens.find((o) => o.tipo === "programada")
    resumo.push(
      <span key="ordem">
        a ordem de amanhã{" "}
        <strong className="text-foreground">
          {!ordem ? "ainda não foi gerada" : ordem.status === "aprovada" ? "está aprovada" : "está em rascunho"}
        </strong>
      </span>,
    )
  }
  if (qtdDivergencias !== undefined) {
    resumo.push(
      <span key="div">
        <strong className="text-foreground">{contar(qtdDivergencias, "divergência", "divergências")}</strong> de
        recebimento nos últimos 7 dias
      </span>,
    )
  }

  const semVendas = vendas.isSuccess && totaisVendas.length === 0

  return (
    <section className="flex flex-col gap-6">
      <CabecalhoPagina
        sobretitulo={dataPorExtenso.format(agora)}
        titulo={primeiroNome ? `${saudacao(agora.getHours())}, ${primeiroNome}` : saudacao(agora.getHours())}
        descricao={
          resumo.length > 0 ? (
            <>
              Agora:{" "}
              {resumo.map((parte, i) => (
                <span key={i}>
                  {i > 0 && (i === resumo.length - 1 ? " e " : ", ")}
                  {parte}
                </span>
              ))}
              .
            </>
          ) : (
            "O resumo da central para hoje."
          )
        }
        acoes={
          <>
            <Link to="/acompanhamento" className={cn(buttonVariants({ variant: "secondary" }))}>
              Acompanhamento
            </Link>
            <Link to={`/producao?data=${amanha}`} className={cn(buttonVariants())}>
              <Factory aria-hidden="true" />
              Ver ordem de amanhã
            </Link>
          </>
        }
      />

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

      <div className="grid gap-4 lg:grid-cols-5">
        <PainelOrdem amanha={amanha} />

        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          <CartaoEntregas hoje={hoje} />

          <CartaoKpi titulo="Divergências" Icone={PackageCheck} link={{ para: "/distribuicao", rotulo: "Ver recebimentos" }}>
            {divergencias.isPending ? (
              <Estado>Carregando…</Estado>
            ) : divergencias.isError ? (
              <Estado>Não foi possível carregar.</Estado>
            ) : (
              <>
                <p className="numero-destaque text-[30px] leading-tight">{qtdDivergencias}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {qtdDivergencias === 0
                    ? "Nos últimos 7 dias, tudo chegou como enviado."
                    : "Itens recebidos diferente do enviado, nos últimos 7 dias."}
                </p>
              </>
            )}
          </CartaoKpi>

          <CartaoKpi titulo="Vendido" Icone={ShoppingBasket} link={{ para: "/consultar", rotulo: "Consultar vendas" }}>
            {vendas.isPending ? (
              <Estado>Carregando…</Estado>
            ) : vendas.isError ? (
              <Estado>Não foi possível carregar.</Estado>
            ) : totaisVendas.length === 0 ? (
              <Estado>Nenhuma venda no período.</Estado>
            ) : (
              <>
                <Totais totais={totaisVendas} />
                <p className="mt-1 text-sm text-muted-foreground">
                  Últimos 7 dias ({formatarData(inicio7).slice(0, 5)} a {formatarData(ontem).slice(0, 5)})
                </p>
              </>
            )}
          </CartaoKpi>

          <CartaoKpi titulo="Perda" Icone={Trash2} link={{ para: "/consultar?tipo=perdas", rotulo: "Consultar perdas" }}>
            {perdas.isPending ? (
              <Estado>Carregando…</Estado>
            ) : perdas.isError ? (
              <Estado>Não foi possível carregar.</Estado>
            ) : totaisPerdas.length === 0 ? (
              <Estado>Nenhuma perda no período.</Estado>
            ) : (
              <>
                <Totais totais={totaisPerdas} />
                <ul className="mt-1 text-sm text-muted-foreground">
                  {totaisPerdas.map((p) => {
                    const venda = totaisVendas.find((v) => v.unidade === p.unidade)
                    if (!venda) return null
                    return (
                      <li key={p.unidade}>
                        <span className="font-semibold text-foreground tabular-nums">
                          {formatarPercentual(Number(p.quantidade) / Number(venda.quantidade))}
                        </span>{" "}
                        do vendido em {p.unidade === "KG" ? "kg" : "un"}
                      </li>
                    )
                  })}
                </ul>
              </>
            )}
          </CartaoKpi>
        </div>
      </div>

      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <ChartLine className="size-4" aria-hidden="true" />
        Vendas e perdas de {formatarData(inicio7)} a {formatarData(ontem)}, pelo que foi registrado.
      </p>
    </section>
  )
}
