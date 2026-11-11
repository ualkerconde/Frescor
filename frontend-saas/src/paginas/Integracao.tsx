/*
 * Integração de vendas (D107, D108): de onde vem a venda diária de cada
 * loja e produto, se ela está chegando e o que ficou de fora.
 *
 * Por que existe: a previsão, a necessidade e o acompanhamento dependem da
 * venda de ontem. Sem esta tela, uma busca que falhou ou um produto com
 * código diferente no PDV só apareceriam como previsão ruim dias depois.
 *
 * - Configuração (modo, endereço, chave) é feita na implantação, pelo
 *   script do backend: chave e senha não passam pela tela. Aqui só se lê.
 * - "Buscar agora" (ação principal, só no modo busca): busca de novo um
 *   período (padrão: ontem e os dias de rebusca), até 31 dias.
 * - Pendências: código de produto que não casou com o cadastro. "Ligar a
 *   um produto" grava o código no PDV do produto e reaplica as linhas
 *   guardadas. Loja desconhecida só é mostrada (loja é cadastrada pelo
 *   suporte).
 * - A carga de histórico por CSV (e a contingência) abre daqui.
 */
import { useId, useState } from "react"
import { Link } from "react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { cn } from "cn"
import { CircleAlert, CircleCheck, CircleX, Link2, RefreshCw, TriangleAlert, Upload } from "lucide-react"
import { toast } from "sonner"
import { CabecalhoPagina } from "@/components/layout/CabecalhoPagina"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Toaster } from "@/components/ui/sonner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { ExecucaoSyncVendas, IntegracaoVendas, PendenciaSyncVendas, ResultadoCasamento } from "@/lib/api/tipos"
import { contar, dataIso, diasNoPeriodo, formatarData, formatarInteiro, somarDias } from "@/lib/formato"
import { SeletorProduto, type ProdutoEscolhido } from "./consultar/SeletorProduto"

const MAX_DIAS_BUSCA = 31

const ORIGEM: Record<ExecucaoSyncVendas["origem"], string> = {
  agendada: "Busca automática",
  manual: "Buscar agora",
  envio: "Envio do sistema",
}

const SITUACAO = {
  sucesso: { rotulo: "Tudo certo", classe: "bg-success-bg text-success", Icone: CircleCheck },
  parcial: { rotulo: "Com pendências", classe: "bg-warning-bg text-warning", Icone: TriangleAlert },
  falhou: { rotulo: "Falhou", classe: "bg-error-bg text-error", Icone: CircleX },
} as const

const horario = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" })

/** Data e hora gravadas em UTC sem fuso pelo backend -> hora local do navegador. */
function quando(isoUtc: string): string {
  return horario.format(new Date(isoUtc.endsWith("Z") || isoUtc.includes("+") ? isoUtc : `${isoUtc}Z`))
}

function periodo(inicio: string | null, fim: string | null): string {
  if (!inicio || !fim) return "—"
  return inicio === fim ? formatarData(inicio) : `${formatarData(inicio)} a ${formatarData(fim)}`
}

function SeloSituacao({ situacao }: { situacao: ExecucaoSyncVendas["situacao"] }) {
  const { rotulo, classe, Icone } = SITUACAO[situacao]
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap", classe)}>
      <Icone className="size-4" aria-hidden="true" />
      {rotulo}
    </span>
  )
}

export function Integracao() {
  const queryClient = useQueryClient()
  const [hoje] = useState(() => dataIso(new Date()))
  const [buscando, setBuscando] = useState(false)
  const [ligando, setLigando] = useState<PendenciaSyncVendas | null>(null)

  const estado = useQuery({
    queryKey: ["integracao", "vendas"],
    queryFn: () => apiJson<IntegracaoVendas>("/web/integracao/vendas"),
  })

  async function recarregar() {
    // Venda nova muda a consulta, a visão geral e o acompanhamento.
    for (const chave of ["integracao", "consulta", "inicio", "acompanhamento"]) {
      await queryClient.invalidateQueries({ queryKey: [chave] })
    }
  }

  const buscar = useMutation({
    mutationFn: (corpo: { data_inicio: string; data_fim: string }) =>
      apiJson<ExecucaoSyncVendas>("/web/integracao/vendas/buscar", { method: "POST", json: corpo }),
    onSuccess: async (ex) => {
      const linhas = contar(ex.linhas_gravadas, "linha gravada", "linhas gravadas")
      if (ex.situacao === "falhou") toast.error(`A busca falhou. ${ex.mensagem ?? ""}`.trim())
      else if (ex.situacao === "parcial") toast.warning(`Busca feita: ${linhas}; ${contar(ex.linhas_pendentes, "linha ficou", "linhas ficaram")} pendente.`)
      else toast.success(`Busca feita: ${linhas}.`)
      setBuscando(false)
      await recarregar()
    },
  })

  const ligar = useMutation({
    mutationFn: (corpo: { codigo_produto: string; produto_id: number; rotulo: string }) =>
      apiJson<ResultadoCasamento>("/web/integracao/vendas/pendencias/casar", {
        method: "POST",
        json: { codigo_produto: corpo.codigo_produto, produto_id: corpo.produto_id },
      }),
    onSuccess: async (r, corpo) => {
      toast.success(
        `Código ${corpo.codigo_produto} ligado a ${corpo.rotulo}: ${contar(r.gravadas, "linha de venda gravada", "linhas de venda gravadas")}.`,
      )
      setLigando(null)
      await recarregar()
    },
  })

  const dados = estado.data
  const busca = dados?.configurada && dados.modo === "busca"

  return (
    <section className="flex flex-col gap-8">
      <CabecalhoPagina
        sobretitulo="Configuração"
        titulo="Integração de vendas"
        descricao="A venda diária de cada loja e produto vem do sistema de vendas do cliente. Aqui você vê se ela está chegando e resolve o que ficou de fora."
        acoes={
          <>
            <Link to="/importar" className={buttonVariants({ variant: "secondary" })}>
              <Upload aria-hidden="true" />
              Carga de histórico (CSV)
            </Link>
            {busca && (
              <Button onClick={() => setBuscando(true)} disabled={!dados.ativa}>
                <RefreshCw aria-hidden="true" />
                Buscar agora
              </Button>
            )}
          </>
        }
      />

      {estado.isError ? (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{estado.error.message}</AlertTitle>
          <AlertDescription>Recarregue a página e tente de novo.</AlertDescription>
        </Alert>
      ) : estado.isPending ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : (
        <>
          <Situacao dados={estado.data} />
          <Pendencias pendencias={estado.data.pendencias} aoLigar={setLigando} />
          {estado.data.configurada && <Execucoes execucoes={estado.data.execucoes} />}
        </>
      )}

      <Dialog open={buscando} onOpenChange={(a) => {
        if (!a) {
          setBuscando(false)
          buscar.reset()
        }
      }}>
        <DialogContent className="sm:max-w-lg">
          {buscando && dados && (
            <FormularioBusca
              hoje={hoje}
              diasRebusca={dados.dias_rebusca ?? 0}
              carregando={buscar.isPending}
              erroApi={buscar.isError ? buscar.error.message : null}
              aoFechar={() => {
                setBuscando(false)
                buscar.reset()
              }}
              aoBuscar={(corpo) => buscar.mutate(corpo)}
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={ligando !== null} onOpenChange={(a) => {
        if (!a) {
          setLigando(null)
          ligar.reset()
        }
      }}>
        <DialogContent className="sm:max-w-lg">
          {ligando && (
            <FormularioLigar
              pendencia={ligando}
              carregando={ligar.isPending}
              erroApi={ligar.isError ? ligar.error.message : null}
              aoFechar={() => {
                setLigando(null)
                ligar.reset()
              }}
              aoLigar={(produto) => ligar.mutate({ codigo_produto: ligando.codigo, produto_id: produto.id, rotulo: produto.rotulo })}
            />
          )}
        </DialogContent>
      </Dialog>
      <Toaster position="bottom-right" />
    </section>
  )
}

function Situacao({ dados }: { dados: IntegracaoVendas }) {
  if (!dados.configurada) {
    return (
      <Alert variant="aviso">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>A integração com o sistema de vendas ainda não foi ligada.</AlertTitle>
        <AlertDescription>
          Ela é configurada na implantação, com os dados do sistema do cliente. Até lá, a venda entra pela carga de
          histórico (CSV).
        </AlertDescription>
      </Alert>
    )
  }

  const ultima = dados.execucoes[0] ?? null
  const como =
    dados.modo === "busca"
      ? `O Frescor busca todo dia às ${(dados.horario_busca ?? "").slice(0, 5)} a venda de ontem e confere de novo ${contar(dados.dias_rebusca ?? 0, "dia anterior", "dias anteriores")}.`
      : `O sistema do cliente envia a venda para o Frescor, com a chave que começa por ${dados.chave_prefixo ?? "—"}.`

  return (
    <div className="flex flex-col gap-4">
      {!dados.ativa && (
        <Alert variant="aviso">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>A integração está pausada: nenhuma venda nova entra.</AlertTitle>
          <AlertDescription>Fale com o suporte do Frescor para religar.</AlertDescription>
        </Alert>
      )}
      {dados.ativa && ultima?.situacao === "falhou" && (
        <Alert variant="erro">
          <CircleX aria-hidden="true" />
          <AlertTitle>A última {dados.modo === "busca" ? "busca" : "execução"} falhou ({quando(ultima.iniciada_em)}).</AlertTitle>
          <AlertDescription>
            {ultima.mensagem ?? "Sem detalhe do erro."}{" "}
            {dados.modo === "busca"
              ? "O Frescor tenta de novo na próxima madrugada; resolvido o problema, use “Buscar agora”."
              : "Confira com o responsável pelo sistema de vendas."}
          </AlertDescription>
        </Alert>
      )}
      <dl className="painel grid gap-6 p-6 md:grid-cols-3">
        <div className="flex flex-col gap-1 md:col-span-3">
          <dt className="text-sm font-semibold text-muted-foreground">Como a venda chega</dt>
          <dd>{como}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-sm font-semibold text-muted-foreground">Sistema de vendas</dt>
          <dd className="font-semibold">{dados.sistema ?? "Não informado"}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-sm font-semibold text-muted-foreground">Situação</dt>
          <dd className="font-semibold">{dados.ativa ? "Ligada" : "Pausada"}</dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-sm font-semibold text-muted-foreground">Última execução</dt>
          <dd className="flex flex-wrap items-center gap-2">
            {ultima ? (
              <>
                <span className="numero">{quando(ultima.iniciada_em)}</span>
                <SeloSituacao situacao={ultima.situacao} />
              </>
            ) : (
              "Nenhuma ainda"
            )}
          </dd>
        </div>
      </dl>
    </div>
  )
}

function Pendencias({
  pendencias,
  aoLigar,
}: {
  pendencias: PendenciaSyncVendas[]
  aoLigar: (p: PendenciaSyncVendas) => void
}) {
  const produtos = pendencias.filter((p) => p.motivo === "produto_desconhecido")
  const lojas = pendencias.filter((p) => p.motivo === "loja_desconhecida")

  return (
    <section aria-labelledby="titulo-pendencias" className="flex flex-col gap-4">
      <div>
        <h2 id="titulo-pendencias" className="text-xl">Vendas que ficaram de fora</h2>
        <p className="mt-1 max-w-2xl text-muted-foreground">
          Código que o sistema de vendas mandou e o Frescor não conhece. A venda fica guardada e entra assim que o
          código for ligado a um produto.
        </p>
      </div>
      {pendencias.length === 0 ? (
        <p className="rounded-lg bg-surface p-6">Nenhuma venda pendente: todos os códigos recebidos casaram com o cadastro.</p>
      ) : (
        <Table aria-label="Códigos sem cadastro">
          <TableHeader>
            <TableRow>
              <TableHead>Código</TableHead>
              <TableHead>O que é</TableHead>
              <TableHead className="text-right">Linhas</TableHead>
              <TableHead>Dias</TableHead>
              <TableHead>Lojas</TableHead>
              <TableHead className="text-right">Ação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...produtos, ...lojas].map((p) => (
              <TableRow key={`${p.motivo}-${p.codigo}`}>
                <TableCell className="numero font-semibold">{p.codigo}</TableCell>
                <TableCell>{p.motivo === "produto_desconhecido" ? "Produto sem cadastro" : "Loja sem cadastro"}</TableCell>
                <TableCell className="numero text-right">{formatarInteiro(p.linhas)}</TableCell>
                <TableCell className="numero whitespace-nowrap">{periodo(p.primeira_data, p.ultima_data)}</TableCell>
                <TableCell className="numero">{p.lojas.join(", ")}</TableCell>
                <TableCell className="text-right">
                  {p.motivo === "produto_desconhecido" ? (
                    <Button variant="secondary" onClick={() => aoLigar(p)} aria-label={`Ligar o código ${p.codigo} a um produto`}>
                      <Link2 aria-hidden="true" />
                      Ligar a um produto
                    </Button>
                  ) : (
                    <span className="text-sm text-muted-foreground">Peça ao suporte para cadastrar a loja com este código.</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  )
}

function Execucoes({ execucoes }: { execucoes: ExecucaoSyncVendas[] }) {
  return (
    <section aria-labelledby="titulo-execucoes" className="flex flex-col gap-4">
      <h2 id="titulo-execucoes" className="text-xl">Últimas execuções</h2>
      {execucoes.length === 0 ? (
        <p className="rounded-lg bg-surface p-6">Nenhuma execução ainda.</p>
      ) : (
        <Table aria-label="Últimas execuções da integração">
          <TableHeader>
            <TableRow>
              <TableHead>Quando</TableHead>
              <TableHead>Como</TableHead>
              <TableHead>Dias de venda</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead className="text-right">Gravadas</TableHead>
              <TableHead className="text-right">Pendentes</TableHead>
              <TableHead className="text-right">Recusadas</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {execucoes.map((ex) => (
              <TableRow key={ex.id}>
                <TableCell className="numero whitespace-nowrap">{quando(ex.iniciada_em)}</TableCell>
                <TableCell className="whitespace-nowrap">{ORIGEM[ex.origem]}</TableCell>
                <TableCell className="numero whitespace-nowrap">{periodo(ex.data_inicio, ex.data_fim)}</TableCell>
                <TableCell>
                  <SeloSituacao situacao={ex.situacao} />
                  {ex.mensagem && <span className="mt-1 block max-w-md text-sm text-muted-foreground">{ex.mensagem}</span>}
                </TableCell>
                <TableCell className="numero text-right">
                  {formatarInteiro(ex.linhas_gravadas)}
                  <span className="block text-sm text-muted-foreground">de {formatarInteiro(ex.linhas_recebidas)}</span>
                </TableCell>
                <TableCell className="numero text-right">{formatarInteiro(ex.linhas_pendentes)}</TableCell>
                <TableCell className="numero text-right">{formatarInteiro(ex.linhas_invalidas)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  )
}

function FormularioBusca({
  hoje,
  diasRebusca,
  carregando,
  erroApi,
  aoFechar,
  aoBuscar,
}: {
  hoje: string
  diasRebusca: number
  carregando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoBuscar: (corpo: { data_inicio: string; data_fim: string }) => void
}) {
  const id = useId()
  const ontem = somarDias(hoje, -1)
  const [inicio, setInicio] = useState(somarDias(ontem, -diasRebusca))
  const [fim, setFim] = useState(ontem)
  const [erro, setErro] = useState<string | null>(null)

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    let e: string | null = null
    if (!inicio || !fim) e = "Informe as duas datas."
    else if (fim < inicio) e = "A data final não pode ser antes da inicial."
    else if (fim > hoje) e = "Não dá para buscar venda de um dia que ainda não chegou."
    else if (diasNoPeriodo(inicio, fim) > MAX_DIAS_BUSCA) e = `Busque até ${MAX_DIAS_BUSCA} dias de cada vez.`
    setErro(e)
    if (!e) aoBuscar({ data_inicio: inicio, data_fim: fim })
  }

  const invalido = {
    "aria-invalid": erro ? true : undefined,
    "aria-describedby": erro ? `${id}-erro` : undefined,
  }

  return (
    <form onSubmit={enviar} noValidate className="flex flex-col gap-5">
      <DialogHeader>
        <DialogTitle>Buscar vendas agora</DialogTitle>
        <DialogDescription>
          A venda destes dias vem de novo do sistema e substitui a que já estava. Use depois de uma falha ou de uma
          correção no sistema de vendas.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-inicio`}>Primeiro dia</Label>
          <Input id={`${id}-inicio`} type="date" max={hoje} value={inicio} onChange={(e) => setInicio(e.target.value)} {...invalido} />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-fim`}>Último dia</Label>
          <Input id={`${id}-fim`} type="date" max={hoje} value={fim} onChange={(e) => setFim(e.target.value)} {...invalido} />
        </div>
      </div>
      {erro && (
        <p id={`${id}-erro`} className="flex items-center gap-1 text-sm text-error">
          <CircleAlert className="size-4" aria-hidden="true" />
          {erro}
        </p>
      )}
      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A busca não foi feita. {erroApi}</AlertTitle>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>Cancelar</Button>
        <Button type="submit" carregando={carregando} textoCarregando="Buscando…">
          <RefreshCw aria-hidden="true" />
          Buscar
        </Button>
      </DialogFooter>
    </form>
  )
}

function FormularioLigar({
  pendencia,
  carregando,
  erroApi,
  aoFechar,
  aoLigar,
}: {
  pendencia: PendenciaSyncVendas
  carregando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoLigar: (produto: ProdutoEscolhido) => void
}) {
  const id = useId()
  const [produto, setProduto] = useState<ProdutoEscolhido | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    if (!produto) {
      setErro("Escolha o produto.")
      return
    }
    setErro(null)
    aoLigar(produto)
  }

  return (
    <form onSubmit={enviar} noValidate className="flex flex-col gap-5">
      <DialogHeader>
        <DialogTitle>Ligar o código {pendencia.codigo} a um produto</DialogTitle>
        <DialogDescription>
          {contar(pendencia.linhas, "linha de venda", "linhas de venda")} de {periodo(pendencia.primeira_data, pendencia.ultima_data)}
          {pendencia.lojas.length > 0 && ` (lojas ${pendencia.lojas.join(", ")})`}. O código fica gravado no produto como
          “código no sistema de vendas” e a venda guardada entra na hora.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-produto`}>Produto do Frescor</Label>
        <SeletorProduto id={`${id}-produto`} valor={produto} textoVazio="Buscar produto" oferecerTodos={false} aoMudar={setProduto} />
        {erro && (
          <p className="flex items-center gap-1 text-sm text-error">
            <CircleAlert className="size-4" aria-hidden="true" />
            {erro}
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          Confira a unidade: a quantidade que o sistema manda é lida na unidade do produto (un ou kg).
        </p>
      </div>
      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>O código não foi ligado. {erroApi}</AlertTitle>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>Cancelar</Button>
        <Button type="submit" carregando={carregando} textoCarregando="Ligando…">
          <Link2 aria-hidden="true" />
          Ligar ao produto
        </Button>
      </DialogFooter>
    </form>
  )
}
