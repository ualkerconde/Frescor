/*
 * Consulta de vendas e perdas (passo W7), pela skill Frescor.
 *
 * - Filtros: período (obrigatório, até 366 dias), loja (lojas da central,
 *   GET /web/lojas) e produto (busca em GET /web/produtos, sem acento).
 *   Uma ação principal: "Consultar". Os filtros aplicados ficam na URL
 *   (recarregar ou compartilhar mantém a consulta).
 * - No topo, o resumo do período (total vendido e total de perda, por
 *   unidade), antes da tabela (pedido do Ualker).
 * - "Vendas" / "Perdas" troca a tabela na hora; paginação de 50 em 50 com
 *   o total; números à direita, sempre com a unidade; datas dd/mm/aaaa.
 * - Estado vazio útil (com o caminho para importar) e erros em português.
 */
import { useId, useMemo, useState, type FormEvent } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { ChevronLeft, ChevronRight, CircleAlert, Search, Upload } from "lucide-react"
import { Link, useSearchParams } from "react-router"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { ConsultaDiaria, ItemDiario, LojaWeb, TipoImportacao } from "@/lib/api/tipos"
import { contar, dataIso, diasNoPeriodo, formatarData, formatarInteiro, formatarQuantidade } from "@/lib/formato"
import { ResumoPeriodo } from "./consultar/ResumoPeriodo"
import { SeletorProduto, type ProdutoEscolhido } from "./consultar/SeletorProduto"

const TAMANHO_PAGINA = 50
const PERIODO_MAXIMO_DIAS = 366
const TODAS_AS_LOJAS = "todas"

const ORIGEM: Record<ItemDiario["origem"], string> = {
  manual: "Importação",
  api: "PDV",
  inferida: "Calculada",
}

interface Filtros {
  inicio: string
  fim: string
  loja: string // id ou TODAS_AS_LOJAS
  produto: ProdutoEscolhido | null
}

/** Padrão: os últimos 7 dias, até ontem (o dado de hoje ainda não fechou). */
function periodoPadrao(): { inicio: string; fim: string } {
  const ontem = new Date()
  ontem.setDate(ontem.getDate() - 1)
  const inicio = new Date(ontem)
  inicio.setDate(ontem.getDate() - 6)
  return { inicio: dataIso(inicio), fim: dataIso(ontem) }
}

function lerFiltros(params: URLSearchParams): Filtros {
  const padrao = periodoPadrao()
  const produtoId = Number(params.get("produto"))
  return {
    inicio: params.get("inicio") ?? padrao.inicio,
    fim: params.get("fim") ?? padrao.fim,
    loja: params.get("loja") ?? TODAS_AS_LOJAS,
    produto: produtoId ? { id: produtoId, rotulo: params.get("produto_rotulo") ?? `Produto ${produtoId}` } : null,
  }
}

function erroDoPeriodo(f: Filtros): string | null {
  if (!f.inicio || !f.fim) return "Informe a data inicial e a final."
  if (f.inicio > f.fim) return "A data inicial é depois da final. Confira o período."
  const dias = diasNoPeriodo(f.inicio, f.fim)
  if (dias > PERIODO_MAXIMO_DIAS) return `O período tem ${formatarInteiro(dias)} dias; o máximo é ${PERIODO_MAXIMO_DIAS}. Escolha um período menor.`
  return null
}

function caminhoConsulta(tipo: TipoImportacao, f: Filtros, limit: number, offset: number): string {
  const q = new URLSearchParams({ data_inicio: f.inicio, data_fim: f.fim, limit: String(limit), offset: String(offset) })
  if (f.loja !== TODAS_AS_LOJAS) q.set("loja_id", f.loja)
  if (f.produto) q.set("produto_id", String(f.produto.id))
  return `/${tipo}?${q.toString()}`
}

export function Consultar() {
  const [params, setParams] = useSearchParams()
  const aplicados = useMemo(() => lerFiltros(params), [params])
  const tipo: TipoImportacao = params.get("tipo") === "perdas" ? "perdas" : "vendas"
  const pagina = Math.max(1, Number(params.get("pagina")) || 1)
  const [rascunho, setRascunho] = useState<Filtros>(aplicados)
  const [erroFiltro, setErroFiltro] = useState<string | null>(null)
  // Voltar/avançar do navegador muda a URL: o formulário acompanha.
  const [paramsVistos, setParamsVistos] = useState(params.toString())
  if (params.toString() !== paramsVistos) {
    setParamsVistos(params.toString())
    setRascunho(aplicados)
    setErroFiltro(null)
  }
  const id = useId()
  const periodoValido = erroDoPeriodo(aplicados) === null

  const lojas = useQuery({ queryKey: ["lojas"], queryFn: () => apiJson<LojaWeb[]>("/web/lojas") })
  const nomeLoja = useMemo(() => new Map((lojas.data ?? []).map((l) => [l.id, l])), [lojas.data])

  const chaveFiltros = [aplicados.inicio, aplicados.fim, aplicados.loja, aplicados.produto?.id ?? null]
  const totaisVendas = useQuery({
    queryKey: ["consulta", "totais", "vendas", ...chaveFiltros],
    queryFn: () => apiJson<ConsultaDiaria>(caminhoConsulta("vendas", aplicados, 1, 0)),
    enabled: periodoValido,
  })
  const totaisPerdas = useQuery({
    queryKey: ["consulta", "totais", "perdas", ...chaveFiltros],
    queryFn: () => apiJson<ConsultaDiaria>(caminhoConsulta("perdas", aplicados, 1, 0)),
    enabled: periodoValido,
  })
  const lista = useQuery({
    queryKey: ["consulta", "lista", tipo, ...chaveFiltros, pagina],
    queryFn: () => apiJson<ConsultaDiaria>(caminhoConsulta(tipo, aplicados, TAMANHO_PAGINA, (pagina - 1) * TAMANHO_PAGINA)),
    enabled: periodoValido,
    placeholderData: keepPreviousData,
  })

  function atualizarUrl(mudancas: Record<string, string | null>) {
    const novos = new URLSearchParams(params)
    for (const [chave, valor] of Object.entries(mudancas)) {
      if (valor === null) novos.delete(chave)
      else novos.set(chave, valor)
    }
    setParams(novos)
  }

  function aoConsultar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const erro = erroDoPeriodo(rascunho)
    setErroFiltro(erro)
    if (erro) return
    atualizarUrl({
      inicio: rascunho.inicio,
      fim: rascunho.fim,
      loja: rascunho.loja === TODAS_AS_LOJAS ? null : rascunho.loja,
      produto: rascunho.produto ? String(rascunho.produto.id) : null,
      produto_rotulo: rascunho.produto ? rascunho.produto.rotulo : null,
      pagina: null,
    })
  }

  const total = lista.data?.total ?? 0
  const primeira = total === 0 ? 0 : (pagina - 1) * TAMANHO_PAGINA + 1
  const ultima = Math.min(pagina * TAMANHO_PAGINA, total)
  const nomeTipo = tipo === "vendas" ? "venda" : "perda"

  return (
    <section className="flex flex-col gap-8">
      <div>
        <h1 className="text-[32px] leading-tight">Consultar vendas e perdas</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Veja o que foi importado por período, loja e produto.
        </p>
      </div>

      <form onSubmit={aoConsultar} noValidate className="flex flex-col gap-4 painel p-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-inicio`}>Data inicial</Label>
            <Input
              id={`${id}-inicio`}
              type="date"
              value={rascunho.inicio}
              onChange={(e) => setRascunho({ ...rascunho, inicio: e.target.value })}
              aria-invalid={erroFiltro ? true : undefined}
              aria-describedby={erroFiltro ? `${id}-erro` : undefined}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-fim`}>Data final</Label>
            <Input
              id={`${id}-fim`}
              type="date"
              value={rascunho.fim}
              onChange={(e) => setRascunho({ ...rascunho, fim: e.target.value })}
              aria-invalid={erroFiltro ? true : undefined}
              aria-describedby={erroFiltro ? `${id}-erro` : undefined}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-loja`}>Loja</Label>
            <Select value={rascunho.loja} onValueChange={(loja) => setRascunho({ ...rascunho, loja })}>
              <SelectTrigger id={`${id}-loja`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS_AS_LOJAS}>Todas as lojas da central</SelectItem>
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
            <SeletorProduto
              id={`${id}-produto`}
              valor={rascunho.produto}
              aoMudar={(produto) => setRascunho({ ...rascunho, produto })}
            />
          </div>
        </div>
        {erroFiltro && (
          <p id={`${id}-erro`} className="flex items-start gap-2 text-sm text-error">
            <CircleAlert className="size-5 shrink-0" aria-hidden="true" />
            {erroFiltro}
          </p>
        )}
        <div>
          <Button type="submit">
            <Search aria-hidden="true" />
            Consultar
          </Button>
        </div>
      </form>

      {!periodoValido ? (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{erroDoPeriodo(aplicados)}</AlertTitle>
        </Alert>
      ) : (
        <>
          <div aria-live="polite">
            <p className="mb-3 text-sm text-muted-foreground">
              Período de {formatarData(aplicados.inicio)} a {formatarData(aplicados.fim)}
              {aplicados.loja !== TODAS_AS_LOJAS && nomeLoja.get(Number(aplicados.loja))
                ? ` · loja ${nomeLoja.get(Number(aplicados.loja))!.codigo ?? nomeLoja.get(Number(aplicados.loja))!.nome}`
                : " · todas as lojas"}
              {aplicados.produto ? ` · ${aplicados.produto.rotulo}` : " · todos os produtos"}
            </p>
            <ResumoPeriodo
              vendas={totaisVendas.data?.totais}
              perdas={totaisPerdas.data?.totais}
              carregandoVendas={totaisVendas.isPending}
              carregandoPerdas={totaisPerdas.isPending}
            />
          </div>

          <div className="flex flex-col gap-4">
            <fieldset>
              <legend className="sr-only">Mostrar na tabela</legend>
              <div className="inline-flex rounded-lg bg-surface p-1">
                {(["vendas", "perdas"] as const).map((opcao) => (
                  <label
                    key={opcao}
                    className={cn(
                      "inline-flex h-11 min-w-28 cursor-pointer items-center justify-center rounded-md px-4 font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
                      tipo === opcao ? "bg-card text-primary shadow-elevado" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <input
                      type="radio"
                      name={`${id}-tipo`}
                      value={opcao}
                      checked={tipo === opcao}
                      onChange={() => atualizarUrl({ tipo: opcao === "vendas" ? null : opcao, pagina: null })}
                      className="sr-only"
                    />
                    {opcao === "vendas" ? "Vendas" : "Perdas"}
                  </label>
                ))}
              </div>
            </fieldset>

            {lista.isError ? (
              <Alert variant="erro">
                <CircleAlert aria-hidden="true" />
                <AlertTitle>{lista.error.message}</AlertTitle>
              </Alert>
            ) : lista.isPending ? (
              <p className="text-muted-foreground">Carregando…</p>
            ) : total === 0 ? (
              <div className="painel-vazio p-6">
                <p className="text-foreground">
                  Nenhuma {nomeTipo} importada neste período{aplicados.loja !== TODAS_AS_LOJAS || aplicados.produto ? " com esses filtros" : ""}.
                </p>
                <p className="mt-1 text-muted-foreground">Mude o período ou os filtros, ou importe o arquivo.</p>
                <Link to="/importar" className={buttonVariants({ variant: "secondary", className: "mt-4" })}>
                  <Upload aria-hidden="true" />
                  Importar CSV
                </Link>
              </div>
            ) : (
              <>
                <Table aria-label={tipo === "vendas" ? "Vendas do período" : "Perdas do período"}>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Data</TableHead>
                      <TableHead>Loja</TableHead>
                      <TableHead>Produto</TableHead>
                      <TableHead className="text-right">Quantidade</TableHead>
                      <TableHead>Origem</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {lista.data.itens.map((item, i) => {
                      const loja = nomeLoja.get(item.loja.id)
                      return (
                        <TableRow key={`${item.data}-${item.loja.id}-${item.produto.id}-${item.origem}-${i}`}>
                          <TableCell className="whitespace-nowrap numero">{formatarData(item.data)}</TableCell>
                          <TableCell className="whitespace-nowrap">
                            {item.loja.codigo ?? ""}
                            {loja ? ` · ${loja.nome}` : ""}
                          </TableCell>
                          <TableCell>
                            {item.produto.codigo ? `${item.produto.codigo} · ` : ""}
                            {item.produto.nome}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap numero">
                            {formatarQuantidade(item.quantidade, item.unidade)}
                          </TableCell>
                          <TableCell>
                            <span className="inline-flex rounded-full bg-surface px-2.5 py-0.5 text-sm font-semibold text-foreground">
                              {ORIGEM[item.origem]}
                            </span>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>

                <nav aria-label="Páginas" className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-muted-foreground numero">
                    Mostrando {formatarInteiro(primeira)}–{formatarInteiro(ultima)} de {contar(total, "linha", "linhas")}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      disabled={pagina <= 1}
                      onClick={() => atualizarUrl({ pagina: pagina - 1 <= 1 ? null : String(pagina - 1) })}
                    >
                      <ChevronLeft aria-hidden="true" />
                      Anterior
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={ultima >= total}
                      onClick={() => atualizarUrl({ pagina: String(pagina + 1) })}
                    >
                      Próxima
                      <ChevronRight aria-hidden="true" />
                    </Button>
                  </div>
                </nav>
              </>
            )}
          </div>
        </>
      )}
    </section>
  )
}
