/*
 * Acompanhamento (dashboard, D115/D116): previsto × solicitado × produzido ×
 * enviado × vendido × perda, sobre GET /web/acompanhamento.
 *
 * - Filtros: período (padrão: os 7 dias até ontem, até 28), loja e produto.
 * - Um bloco por unidade (un e kg nunca se somam): erro da previsão (WAPE),
 *   viés, vendido e perda; gráfico previsto × vendido por dia; totais do
 *   período em barras; tabela do dia a dia.
 * - Tabela por produto, com erro, viés, sobra, perda sem registro e
 *   ruptura ("acabou", D111, pela contagem do fechamento).
 * Pedido, produzido e enviado contam pelo dia de ENTREGA: o que chega num
 * dia vende nos seguintes, então a comparação justa é a dos totais.
 */
import { useId, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CircleAlert, Info } from "lucide-react"
import { CabecalhoPagina } from "@/components/layout/CabecalhoPagina"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { Acompanhamento as Dados, LojaWeb, Unidade, ValoresAcompanhamento } from "@/lib/api/tipos"
import { dataIso, diaDaSemana, diasNoPeriodo, formatarData, formatarPercentual, formatarPrevisao, somarDias } from "@/lib/formato"
import { COR_PREVISTO, COR_VENDIDO, GraficoDias } from "./acompanhamento/GraficoDias"
import { SeletorProduto, type ProdutoEscolhido } from "./consultar/SeletorProduto"

const TODAS = "todas"
const PERIODO_MAXIMO = 28

interface Filtros {
  inicio: string
  fim: string
  loja: string
  produto: ProdutoEscolhido | null
}

const COLUNAS: { chave: keyof ValoresAcompanhamento; rotulo: string; dica: string }[] = [
  { chave: "previsto", rotulo: "Previsto", dica: "Venda prevista para o dia" },
  { chave: "sugerido", rotulo: "Sugerido", dica: "O que o sistema sugeriu na ordem (dia de entrega)" },
  { chave: "final", rotulo: "Pedido", dica: "Quantidade final da ordem aprovada (dia de entrega)" },
  { chave: "produzido", rotulo: "Produzido", dica: "Produção registrada na central (dia de entrega)" },
  { chave: "enviado", rotulo: "Enviado", dica: "O que saiu da central no romaneio (dia de entrega)" },
  { chave: "vendido", rotulo: "Vendido", dica: "Venda real do dia" },
  { chave: "perda", rotulo: "Perda", dica: "Perda lançada no dia" },
]

/** Na tabela do dia a dia entra também a perda sem registro (D111); nas barras não (pode ser negativa). */
const COLUNAS_DIA = [
  ...COLUNAS,
  {
    chave: "sem_registro" as const,
    rotulo: "Sem registro",
    dica: "Contagem de ontem + recebido − vendido − perda lançada − contagem de hoje",
  },
]

/** "Acabou 2 de 9 dias" a partir dos balanços da contagem (D111). */
function textoRupturas(rupturas: number, balancos: number): string {
  if (balancos === 0) return "—"
  return `${rupturas} de ${balancos}`
}

function erroDoPeriodo(f: Filtros): string | null {
  if (!f.inicio || !f.fim) return "Informe as duas datas."
  if (f.fim < f.inicio) return "A data final não pode ser antes da inicial."
  if (diasNoPeriodo(f.inicio, f.fim) > PERIODO_MAXIMO) return `O período pode ter até ${PERIODO_MAXIMO} dias.`
  return null
}

function caminho(f: Filtros): string {
  const p = new URLSearchParams({ data_inicio: f.inicio, data_fim: f.fim })
  if (f.loja !== TODAS) p.set("loja_id", f.loja)
  if (f.produto) p.set("produto_id", String(f.produto.id))
  return `/web/acompanhamento?${p}`
}

function q(valor: string | null, unidade: Unidade): string {
  return valor === null ? "—" : formatarPrevisao(valor, unidade)
}

/** "+4%" previu a mais; "−6%" a menos. */
function textoVies(vies: string | null): string {
  if (vies === null) return "—"
  const v = Number(vies)
  if (Math.abs(v) < 0.005) return "0%"
  return `${v > 0 ? "+" : "−"}${formatarPercentual(Math.abs(v))}`
}

function fraseVies(vies: string | null): string {
  if (vies === null) return "Sem previsão e venda no mesmo dia."
  const v = Number(vies)
  if (Math.abs(v) < 0.005) return "A previsão acertou o total."
  return v > 0 ? "A previsão ficou acima da venda." : "A previsão ficou abaixo da venda."
}

function Indicador({ rotulo, valor, apoio }: { rotulo: string; valor: string; apoio: string }) {
  return (
    <div className="painel-kpi flex flex-col gap-1 p-5">
      <p className="text-sm font-semibold text-muted-foreground">{rotulo}</p>
      <p className="numero text-[26px] leading-tight font-bold">{valor}</p>
      <p className="text-sm text-muted-foreground">{apoio}</p>
    </div>
  )
}

function BarrasTotais({ totais, unidade, produzidoDisponivel }: { totais: ValoresAcompanhamento; unidade: Unidade; produzidoDisponivel: boolean }) {
  const linhas = COLUNAS.filter((c) => c.chave !== "produzido" || produzidoDisponivel)
  const maximo = Math.max(1, ...linhas.map((c) => Number(totais[c.chave] ?? 0)))
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="font-semibold">Totais do período</figcaption>
      <ul className="flex flex-col gap-2" aria-label="Totais do período">
        {linhas.map((c) => {
          const v = totais[c.chave]
          const cor = c.chave === "previsto" ? COR_PREVISTO : c.chave === "vendido" ? COR_VENDIDO : "var(--fr-input-border)"
          return (
            <li key={c.chave} className="grid grid-cols-[88px_1fr_auto] items-center gap-3 text-sm" title={c.dica}>
              <span>{c.rotulo}</span>
              <span className="h-3 rounded-r-[4px] bg-transparent">
                {v !== null && Number(v) > 0 && (
                  <span
                    className="block h-3 rounded-r-[4px]"
                    style={{ width: `${(Number(v) / maximo) * 100}%`, background: cor }}
                  />
                )}
              </span>
              <span className="numero min-w-20 text-right">{q(v, unidade)}</span>
            </li>
          )
        })}
      </ul>
    </figure>
  )
}

export function Acompanhamento() {
  const id = useId()
  const [inicial] = useState<Filtros>(() => {
    const ontem = somarDias(dataIso(new Date()), -1)
    return { inicio: somarDias(ontem, -6), fim: ontem, loja: TODAS, produto: null }
  })
  const [rascunho, setRascunho] = useState<Filtros>(inicial)
  const [aplicados, setAplicados] = useState<Filtros>(inicial)
  const [erroFiltro, setErroFiltro] = useState<string | null>(null)

  const lojas = useQuery({ queryKey: ["lojas"], queryFn: () => apiJson<LojaWeb[]>("/web/lojas") })
  const dados = useQuery({
    queryKey: ["acompanhamento", aplicados.inicio, aplicados.fim, aplicados.loja, aplicados.produto?.id ?? null],
    queryFn: () => apiJson<Dados>(caminho(aplicados)),
  })

  function aplicar(evento: React.FormEvent) {
    evento.preventDefault()
    const erro = erroDoPeriodo(rascunho)
    setErroFiltro(erro)
    if (!erro) setAplicados(rascunho)
  }

  return (
    <section className="flex flex-col gap-8">
      <CabecalhoPagina
        sobretitulo="Visão"
        titulo="Acompanhamento"
        descricao="A previsão acertou? O que foi pedido, produzido e enviado bateu com a venda? Compare por período, loja e produto."
      />

      <form onSubmit={aplicar} noValidate className="painel flex flex-col gap-4 p-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-inicio`}>Data inicial</Label>
            <Input id={`${id}-inicio`} type="date" value={rascunho.inicio}
              onChange={(e) => setRascunho({ ...rascunho, inicio: e.target.value })}
              aria-invalid={erroFiltro ? true : undefined} aria-describedby={erroFiltro ? `${id}-erro` : undefined} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-fim`}>Data final</Label>
            <Input id={`${id}-fim`} type="date" value={rascunho.fim}
              onChange={(e) => setRascunho({ ...rascunho, fim: e.target.value })}
              aria-invalid={erroFiltro ? true : undefined} aria-describedby={erroFiltro ? `${id}-erro` : undefined} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-loja`}>Loja</Label>
            <Select value={rascunho.loja} onValueChange={(loja) => setRascunho({ ...rascunho, loja })}>
              <SelectTrigger id={`${id}-loja`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todas as lojas da central</SelectItem>
                {(lojas.data ?? []).map((l) => (
                  <SelectItem key={l.id} value={String(l.id)}>
                    {l.codigo ? `${l.codigo} · ${l.nome}` : l.nome}
                    {!l.ativo && " (inativa)"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-produto`}>Produto</Label>
            <SeletorProduto id={`${id}-produto`} valor={rascunho.produto}
              aoMudar={(produto) => setRascunho({ ...rascunho, produto })} />
          </div>
        </div>
        {erroFiltro && (
          <p id={`${id}-erro`} className="flex items-center gap-1 text-sm text-error">
            <CircleAlert className="size-4" aria-hidden="true" />
            {erroFiltro}
          </p>
        )}
        <div>
          <Button type="submit" variant="secondary">Atualizar</Button>
        </div>
      </form>

      <div aria-live="polite" className="flex flex-col gap-10">
        {dados.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{dados.error.message}</AlertTitle>
            <AlertDescription>Confira os filtros e tente de novo.</AlertDescription>
          </Alert>
        ) : dados.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : dados.data.unidades.length === 0 ? (
          <div className="rounded-lg bg-surface p-6">
            <p>
              Nada registrado de {formatarData(dados.data.data_inicio)} a {formatarData(dados.data.data_fim)}: nem
              previsão, nem pedido, nem venda.
            </p>
            <p className="mt-1 text-muted-foreground">
              Sem venda chegando, não há com o que comparar. Confira se as vendas do período entraram.
            </p>
          </div>
        ) : (
          <>
            <Alert>
              <Info aria-hidden="true" />
              <AlertTitle>Como ler</AlertTitle>
              <AlertDescription>
                Previsto e vendido são do próprio dia. Pedido, produzido e enviado contam pelo dia de entrega, e o que
                chega num dia vende nos seguintes: compare os totais do período, não dia a dia.
                {!dados.data.produzido_disponivel && " Com uma loja escolhida, a produção fica de fora (ela é da central inteira)."}
              </AlertDescription>
            </Alert>
            {dados.data.unidades.map((u) => {
              const nome = u.unidade === "KG" ? "Produtos em quilo (kg)" : "Produtos em unidade (un)"
              const vendido = u.totais.vendido === null ? null : Number(u.totais.vendido)
              const perda = u.totais.perda === null ? null : Number(u.totais.perda)
              return (
                <section key={u.unidade} aria-labelledby={`${id}-${u.unidade}`} className="flex flex-col gap-6">
                  <h2 id={`${id}-${u.unidade}`} className="text-xl font-bold">{nome}</h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                    <Indicador
                      rotulo="Erro da previsão"
                      valor={u.erro.wape === null ? "—" : formatarPercentual(u.erro.wape)}
                      apoio={u.erro.celulas === 0 ? "Sem previsão e venda no mesmo dia." : `Do vendido, em ${u.erro.celulas} ${u.erro.celulas === 1 ? "comparação" : "comparações"} loja × produto × dia.`}
                    />
                    <Indicador rotulo="Viés" valor={textoVies(u.erro.vies)} apoio={fraseVies(u.erro.vies)} />
                    <Indicador rotulo="Vendido" valor={q(u.totais.vendido, u.unidade)} apoio="Venda real no período." />
                    <Indicador
                      rotulo="Perda lançada"
                      valor={q(u.totais.perda, u.unidade)}
                      apoio={perda === null ? "Nenhuma perda lançada." : vendido ? `${formatarPercentual(perda / vendido)} do vendido.` : "Sem venda para comparar."}
                    />
                    <Indicador
                      rotulo="Perda sem registro"
                      valor={q(u.totais.sem_registro, u.unidade)}
                      apoio={
                        u.balancos === 0
                          ? "Sem contagem de fechamento em dois dias seguidos com venda."
                          : `Pela contagem, em ${u.balancos} ${u.balancos === 1 ? "balanço" : "balanços"} loja × produto × dia. Acabou em ${u.rupturas}.`
                      }
                    />
                  </div>
                  <div className="painel grid gap-8 p-6 xl:grid-cols-[2fr_1fr]">
                    <GraficoDias
                      titulo="Previsto × vendido por dia"
                      unidade={u.unidade}
                      pontos={u.dias.map((d) => ({
                        data: d.data,
                        previsto: d.previsto === null ? null : Number(d.previsto),
                        vendido: d.vendido === null ? null : Number(d.vendido),
                      }))}
                    />
                    <BarrasTotais totais={u.totais} unidade={u.unidade} produzidoDisponivel={dados.data.produzido_disponivel} />
                  </div>
                  <Table aria-label={`Dia a dia: ${nome}`}>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Dia</TableHead>
                        {COLUNAS_DIA.filter((c) => c.chave !== "produzido" || dados.data.produzido_disponivel).map((c) => (
                          <TableHead key={c.chave} className="text-right" title={c.dica}>{c.rotulo}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {u.dias.map((d) => (
                        <TableRow key={d.data}>
                          <TableCell className="numero whitespace-nowrap">
                            {formatarData(d.data).slice(0, 5)} <span className="text-muted-foreground">{diaDaSemana(d.data).slice(0, 3)}</span>
                          </TableCell>
                          {COLUNAS_DIA.filter((c) => c.chave !== "produzido" || dados.data.produzido_disponivel).map((c) => (
                            <TableCell key={c.chave} className="numero text-right whitespace-nowrap">{q(d[c.chave], u.unidade)}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </section>
              )
            })}

            <section aria-labelledby={`${id}-produtos`} className="flex flex-col gap-4">
              <h2 id={`${id}-produtos`} className="text-xl font-bold">Por produto</h2>
              <p className="max-w-3xl text-muted-foreground">
                Sobra = enviado − vendido − perda lançada no período. Inclui o que ainda está na prateleira, por isso não
                é perda; sobra alta e repetida indica pedido acima da venda. Sem registro = o que a contagem mostra que
                sumiu além da venda e da perda lançada (descarte não lançado, furto, erro de contagem); negativo, apareceu
                mais do que o esperado. Acabou = dias em que a contagem do fechamento deu zero e houve venda: a venda
                daquele dia pode ter sido menor que a procura.
              </p>
              <Table aria-label="Por produto">
                <TableHeader>
                  <TableRow>
                    <TableHead>Produto</TableHead>
                    <TableHead className="text-right">Previsto</TableHead>
                    <TableHead className="text-right">Pedido</TableHead>
                    {dados.data.produzido_disponivel && <TableHead className="text-right">Produzido</TableHead>}
                    <TableHead className="text-right">Enviado</TableHead>
                    <TableHead className="text-right">Vendido</TableHead>
                    <TableHead className="text-right">Perda</TableHead>
                    <TableHead className="text-right">Erro</TableHead>
                    <TableHead className="text-right">Viés</TableHead>
                    <TableHead className="text-right">Sobra</TableHead>
                    <TableHead className="text-right">Sem registro</TableHead>
                    <TableHead className="text-right">Acabou (dias)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.data.produtos.map((p) => (
                    <TableRow key={p.produto.id}>
                      <TableCell className="font-semibold">{p.produto.codigo ? `${p.produto.codigo} · ${p.produto.nome}` : p.produto.nome}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.previsto, p.unidade)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.final, p.unidade)}</TableCell>
                      {dados.data.produzido_disponivel && (
                        <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.produzido, p.unidade)}</TableCell>
                      )}
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.enviado, p.unidade)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.vendido, p.unidade)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.perda, p.unidade)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{p.erro.wape === null ? "—" : formatarPercentual(p.erro.wape)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{textoVies(p.erro.vies)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.sobra, p.unidade)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{q(p.totais.sem_registro, p.unidade)}</TableCell>
                      <TableCell className="numero text-right whitespace-nowrap">{textoRupturas(p.rupturas, p.balancos)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          </>
        )}
      </div>
    </section>
  )
}
