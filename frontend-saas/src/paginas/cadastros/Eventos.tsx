/*
 * Eventos (datas atípicas, doc §4.3) no cadastro (Fase 6 / C5, D104), sobre
 * a API da F3 (D24, D27): feriado, Natal, festa do bairro.
 *
 * - Lista dos eventos que tocam o período (padrão: de hoje em diante), com
 *   o ajuste em palavras, as lojas e os produtos.
 * - "Novo evento" (ação principal): nome, datas, ajuste (multiplicar a
 *   previsão ou fixar um valor por loja e produto), lojas (todas as da
 *   central, inclusive as que vierem depois, ou algumas) e produtos (todos
 *   ou alguns).
 * - "Apagar" pede confirmação. Editar = apagar e criar de novo (D104).
 * Evento que vale também para outra central não pode ser apagado aqui
 * (a API responde 403 com a explicação, que a tela mostra).
 */
import { useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarDays, CircleAlert, Plus, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiFetch, apiJson } from "@/lib/api/cliente"
import type { Evento, LojaWeb, ProdutosWeb } from "@/lib/api/tipos"
import { contar, dataIso, formatarData } from "@/lib/formato"
import { SeletorProduto, type ProdutoEscolhido } from "../consultar/SeletorProduto"
import { DialogoConfirmar } from "../producao/Dialogos"

const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 })

function descreverAjuste(e: Pick<Evento, "tipo_ajuste" | "valor_ajuste">): string {
  const v = Number(e.valor_ajuste)
  if (e.tipo_ajuste === "valor_fixo") return `Previsão fixa em ${numero.format(v)} por loja e produto`
  if (v === 1) return "Previsão × 1 (sem mudança)"
  const pct = Math.round(Math.abs(v - 1) * 100)
  return `Previsão × ${numero.format(v)} (${pct}% ${v > 1 ? "a mais" : "a menos"})`
}

function periodo(e: Evento): string {
  return e.data_inicio === e.data_fim
    ? formatarData(e.data_inicio)
    : `${formatarData(e.data_inicio)} a ${formatarData(e.data_fim)}`
}

function rotuloLoja(l: { codigo: string | null; nome: string }): string {
  return l.codigo ? `${l.codigo} · ${l.nome}` : l.nome
}

export function Eventos() {
  const id = useId()
  const queryClient = useQueryClient()
  const [inicio, setInicio] = useState(() => dataIso(new Date()))
  const [criando, setCriando] = useState(false)
  const [apagando, setApagando] = useState<Evento | null>(null)

  const eventos = useQuery({
    queryKey: ["cadastro", "eventos", inicio],
    queryFn: () => apiJson<Evento[]>(`/eventos${inicio ? `?data_inicio=${inicio}` : ""}`),
  })
  const lojas = useQuery({ queryKey: ["lojas"], queryFn: () => apiJson<LojaWeb[]>("/web/lojas") })
  // Nomes dos produtos dos eventos (o catálogo da rede cabe numa página de 200).
  const produtos = useQuery({
    queryKey: ["cadastro", "produtos", "nomes"],
    queryFn: () => apiJson<ProdutosWeb>("/web/produtos?limit=200"),
  })
  const nomeLoja = new Map((lojas.data ?? []).map((l) => [l.id, rotuloLoja(l)]))
  const nomeProduto = new Map((produtos.data?.itens ?? []).map((p) => [p.id, p.codigo ? `${p.codigo} · ${p.nome}` : p.nome]))

  const criar = useMutation({
    mutationFn: (corpo: object) => apiJson<Evento>("/eventos", { method: "POST", json: corpo }),
    onSuccess: async (e) => {
      toast.success(`Evento “${e.nome}” cadastrado. Gere a previsão de novo para ele entrar na conta.`)
      setCriando(false)
      await queryClient.invalidateQueries({ queryKey: ["cadastro", "eventos"] })
    },
  })
  const apagar = useMutation({
    mutationFn: (e: Evento) => apiFetch(`/eventos/${e.id}`, { method: "DELETE" }),
    onSuccess: async (_r, e) => {
      toast.success(`Evento “${e.nome}” apagado.`)
      setApagando(null)
      await queryClient.invalidateQueries({ queryKey: ["cadastro", "eventos"] })
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-inicio`}>Eventos a partir de</Label>
          <Input
            id={`${id}-inicio`}
            type="date"
            className="w-48"
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            aria-describedby={`${id}-inicio-ajuda`}
          />
          <p id={`${id}-inicio-ajuda`} className="text-sm text-muted-foreground">
            Apague a data para ver também os eventos passados.
          </p>
        </div>
        <Button onClick={() => setCriando(true)}>
          <Plus aria-hidden="true" />
          Novo evento
        </Button>
      </div>
      <p className="max-w-2xl text-muted-foreground">
        Um evento ajusta a previsão nos dias dele e tira esses dias da base das semanas seguintes. Ele entra na conta
        quando a previsão é gerada de novo.
      </p>

      <div aria-live="polite">
        {eventos.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{eventos.error.message}</AlertTitle>
            <AlertDescription>Recarregue a página.</AlertDescription>
          </Alert>
        ) : eventos.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : eventos.data.length === 0 ? (
          <div className="rounded-lg bg-surface p-6">
            <p>Nenhum evento {inicio ? `a partir de ${formatarData(inicio)}` : "cadastrado"}.</p>
            <p className="mt-1 text-muted-foreground">
              Cadastre feriados e datas especiais para a previsão não errar nesses dias.
            </p>
          </div>
        ) : (
          <Table aria-label="Eventos">
            <TableHeader>
              <TableRow>
                <TableHead>Evento</TableHead>
                <TableHead>Quando</TableHead>
                <TableHead>Ajuste</TableHead>
                <TableHead>Lojas</TableHead>
                <TableHead>Produtos</TableHead>
                <TableHead className="text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {eventos.data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-semibold">{e.nome}</TableCell>
                  <TableCell className="numero whitespace-nowrap">{periodo(e)}</TableCell>
                  <TableCell>{descreverAjuste(e)}</TableCell>
                  <TableCell>
                    {e.escopo_loja === "todas"
                      ? "Todas as lojas da central"
                      : e.loja_ids.map((l) => nomeLoja.get(l) ?? `Loja ${l}`).join(", ")}
                  </TableCell>
                  <TableCell>
                    {e.escopo_produto === "todos"
                      ? "Todos os produtos"
                      : e.produto_ids.map((p) => nomeProduto.get(p) ?? `Produto ${p}`).join(", ")}
                  </TableCell>
                  <TableCell className="text-right">
                    {e.pode_apagar ? (
                      <Button variant="ghost" aria-label={`Apagar: ${e.nome}`} onClick={() => setApagando(e)}>
                        <Trash2 aria-hidden="true" />
                        Apagar
                      </Button>
                    ) : (
                      <span className="text-sm text-muted-foreground">Vale também para outra central</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <Dialog
        open={criando}
        onOpenChange={(a) => {
          if (!a) {
            setCriando(false)
            criar.reset()
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          {criando && (
            <FormularioEvento
              lojas={(lojas.data ?? []).filter((l) => l.ativo)}
              salvando={criar.isPending}
              erroApi={criar.isError ? criar.error.message : null}
              aoFechar={() => {
                setCriando(false)
                criar.reset()
              }}
              aoSalvar={(corpo) => criar.mutate(corpo)}
            />
          )}
        </DialogContent>
      </Dialog>

      <DialogoConfirmar
        aberto={apagando !== null}
        titulo={`Apagar o evento “${apagando?.nome ?? ""}”?`}
        descricao={
          <p>
            A previsão volta ao normal nesses dias quando for gerada de novo. Para corrigir um evento, apague e cadastre
            de novo.
          </p>
        }
        verbo="Apagar evento"
        verboCarregando="Apagando…"
        perigo
        carregando={apagar.isPending}
        erroApi={apagar.isError ? apagar.error.message : null}
        dica="Este evento não pode ser apagado por aqui."
        aoFechar={() => {
          setApagando(null)
          apagar.reset()
        }}
        aoConfirmar={() => apagando && apagar.mutate(apagando)}
      />
    </div>
  )
}

const CAIXA = "size-5 shrink-0 accent-primary"

function FormularioEvento({
  lojas,
  salvando,
  erroApi,
  aoFechar,
  aoSalvar,
}: {
  lojas: LojaWeb[]
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoSalvar: (corpo: object) => void
}) {
  const id = useId()
  const [nome, setNome] = useState("")
  const [inicio, setInicio] = useState("")
  const [fim, setFim] = useState("")
  const [tipo, setTipo] = useState<Evento["tipo_ajuste"]>("multiplicador")
  const [valor, setValor] = useState("")
  const [todasLojas, setTodasLojas] = useState(true)
  const [lojaIds, setLojaIds] = useState<number[]>([])
  const [todosProdutos, setTodosProdutos] = useState(true)
  const [produtosEscolhidos, setProdutosEscolhidos] = useState<ProdutoEscolhido[]>([])
  const [erros, setErros] = useState<Record<string, string>>({})

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    const e: Record<string, string> = {}
    if (!nome.trim()) e.nome = "Informe o nome do evento."
    if (!inicio) e.inicio = "Informe o primeiro dia."
    if (!fim) e.fim = "Informe o último dia (igual ao primeiro, se for um dia só)."
    else if (inicio && fim < inicio) e.fim = "O último dia não pode ser antes do primeiro."
    const v = valor.trim().replace(",", ".")
    if (!/^\d+(\.\d+)?$/.test(v)) e.valor = "Use só números, por exemplo 1,5 ou 0."
    else if (v.includes(".") && v.split(".")[1].length > 4) e.valor = "Informe no máximo 4 casas decimais."
    if (!todasLojas && lojaIds.length === 0) e.lojas = "Escolha pelo menos uma loja."
    if (!todosProdutos && produtosEscolhidos.length === 0) e.produtos = "Escolha pelo menos um produto."
    setErros(e)
    if (Object.keys(e).length > 0) return
    aoSalvar({
      nome: nome.trim(),
      data_inicio: inicio,
      data_fim: fim,
      tipo_ajuste: tipo,
      valor_ajuste: v,
      escopo_loja: todasLojas ? "todas" : "especificas",
      loja_ids: todasLojas ? null : lojaIds,
      produto_ids: todosProdutos ? null : produtosEscolhidos.map((p) => p.id),
    })
  }

  function erro(chave: string) {
    if (!erros[chave]) return null
    return (
      <p id={`${id}-${chave}-erro`} className="flex items-center gap-1 text-sm text-error">
        <CircleAlert className="size-4" aria-hidden="true" />
        {erros[chave]}
      </p>
    )
  }

  const invalido = (chave: string) => ({
    "aria-invalid": erros[chave] !== undefined,
    "aria-describedby": erros[chave] ? `${id}-${chave}-erro` : undefined,
  })

  return (
    <form onSubmit={enviar} noValidate className="flex flex-col gap-5">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <CalendarDays className="size-5" aria-hidden="true" />
          Novo evento
        </DialogTitle>
        <DialogDescription>Feriado, data comemorativa ou festa local que muda as vendas.</DialogDescription>
      </DialogHeader>
      <div className="flex max-h-[60vh] flex-col gap-5 overflow-y-auto pr-1">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-nome`}>Nome do evento</Label>
          <Input id={`${id}-nome`} value={nome} maxLength={255} onChange={(e) => setNome(e.target.value)} {...invalido("nome")} />
          {erro("nome")}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-inicio`}>Primeiro dia</Label>
            <Input id={`${id}-inicio`} type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} {...invalido("inicio")} />
            {erro("inicio")}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-fim`}>Último dia</Label>
            <Input id={`${id}-fim`} type="date" value={fim} onChange={(e) => setFim(e.target.value)} {...invalido("fim")} />
            {erro("fim")}
          </div>
        </div>

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-semibold">Ajuste da previsão</legend>
          <label className="flex items-start gap-3">
            <input type="radio" name={`${id}-tipo`} className={`${CAIXA} mt-0.5`} checked={tipo === "multiplicador"} onChange={() => setTipo("multiplicador")} />
            <span>
              <span className="font-semibold">Multiplicar a previsão</span>
              <span className="block text-sm text-muted-foreground">Ex.: 1,5 = 50% a mais; 0,5 = metade.</span>
            </span>
          </label>
          <label className="flex items-start gap-3">
            <input type="radio" name={`${id}-tipo`} className={`${CAIXA} mt-0.5`} checked={tipo === "valor_fixo"} onChange={() => setTipo("valor_fixo")} />
            <span>
              <span className="font-semibold">Fixar um valor</span>
              <span className="block text-sm text-muted-foreground">
                A previsão de cada loja e produto passa a ser este número (ex.: 0 com a loja fechada).
              </span>
            </span>
          </label>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-valor`}>{tipo === "multiplicador" ? "Multiplicar por" : "Valor por loja e produto"}</Label>
            <Input
              id={`${id}-valor`}
              inputMode="decimal"
              className="max-w-32 text-right numero"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              {...invalido("valor")}
            />
            {erro("valor")}
          </div>
        </fieldset>

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-semibold">Lojas</legend>
          <label className="flex items-center gap-3">
            <input type="checkbox" className={CAIXA} checked={todasLojas} onChange={(e) => setTodasLojas(e.target.checked)} />
            Todas as lojas da central (inclusive as que entrarem depois)
          </label>
          {!todasLojas && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 pl-8">
              {lojas.map((l) => (
                <label key={l.id} className="flex min-h-11 items-center gap-2">
                  <input
                    type="checkbox"
                    className={CAIXA}
                    checked={lojaIds.includes(l.id)}
                    onChange={(e) =>
                      setLojaIds((atual) => (e.target.checked ? [...atual, l.id] : atual.filter((x) => x !== l.id)))
                    }
                  />
                  {rotuloLoja(l)}
                </label>
              ))}
            </div>
          )}
          {erro("lojas")}
        </fieldset>

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-semibold">Produtos</legend>
          <label className="flex items-center gap-3">
            <input type="checkbox" className={CAIXA} checked={todosProdutos} onChange={(e) => setTodosProdutos(e.target.checked)} />
            Todos os produtos
          </label>
          {!todosProdutos && (
            <div className="flex flex-col gap-3 pl-8">
              <div className="flex max-w-sm flex-col gap-2">
                <Label htmlFor={`${id}-produto`}>Adicionar produto</Label>
                <SeletorProduto
                  id={`${id}-produto`}
                  valor={null}
                  textoVazio="Buscar produto"
                  oferecerTodos={false}
                  aoMudar={(p) => p && setProdutosEscolhidos((atual) => (atual.some((x) => x.id === p.id) ? atual : [...atual, p]))}
                />
              </div>
              {produtosEscolhidos.length > 0 && (
                <ul aria-label="Produtos do evento" className="flex flex-wrap gap-2">
                  {produtosEscolhidos.map((p) => (
                    <li key={p.id} className="inline-flex items-center gap-1 rounded-lg bg-surface py-1 pr-1 pl-3">
                      {p.rotulo}
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Tirar ${p.rotulo}`}
                        onClick={() => setProdutosEscolhidos((atual) => atual.filter((x) => x.id !== p.id))}
                      >
                        <X aria-hidden="true" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-sm text-muted-foreground">{contar(produtosEscolhidos.length, "produto escolhido", "produtos escolhidos")}</p>
            </div>
          )}
          {erro("produtos")}
        </fieldset>
      </div>

      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>O evento não foi cadastrado. {erroApi}</AlertTitle>
          <AlertDescription>Corrija e tente de novo.</AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>
          Cancelar
        </Button>
        <Button type="submit" carregando={salvando} textoCarregando="Cadastrando…">
          Cadastrar evento
        </Button>
      </DialogFooter>
    </form>
  )
}
