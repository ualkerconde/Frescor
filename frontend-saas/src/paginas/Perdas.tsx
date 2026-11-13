/*
 * Perdas (D110): os lançamentos de perda das lojas da central.
 *
 * Por que existe: a perda dos itens produzidos não vem do PDV. A loja lança
 * no app na hora do descarte; aqui o gestor vê, lança por uma loja (qualquer
 * dia passado) e corrige ou apaga, sem o prazo da loja (fim de D+1). A soma
 * do dia vai para a perda que a previsão e a necessidade já usam.
 *
 * - Filtros: período (padrão: últimos 7 dias, até 92), loja e produto.
 * - Tabela com dia, loja, produto, quantidade, motivo e quem lançou.
 * - "Lançar perda" é a ação principal. Produto e dia não mudam numa
 *   correção: para isso, apague e lance de novo (igual ao app).
 */
import { useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleAlert, Pencil, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { CabecalhoPagina } from "@/components/layout/CabecalhoPagina"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Toaster } from "@/components/ui/sonner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { apiFetch, apiJson } from "@/lib/api/cliente"
import type { LancamentoPerda, LojaWeb } from "@/lib/api/tipos"
import { contar, dataIso, diasNoPeriodo, formatarData, formatarQuantidade, somarDias } from "@/lib/formato"
import { SeletorProduto, type ProdutoEscolhido } from "./consultar/SeletorProduto"
import { DialogoConfirmar } from "./producao/Dialogos"

const TODAS = "todas"
const PERIODO_MAXIMO = 92
const TAMANHO_OBSERVACAO = 200

const MOTIVOS_PERDA: { valor: LancamentoPerda["motivo"]; rotulo: string }[] = [
  { valor: "vencido", rotulo: "Vencido" },
  { valor: "avariado", rotulo: "Avariado" },
  { valor: "outro", rotulo: "Outro" },
]

function rotuloMotivo(valor: string): string {
  return MOTIVOS_PERDA.find((m) => m.valor === valor)?.rotulo ?? valor
}

function rotuloLoja(l: { codigo: string | null; nome: string }): string {
  return l.codigo ? `${l.codigo} · ${l.nome}` : l.nome
}

interface Filtros {
  inicio: string
  fim: string
  loja: string
  produto: ProdutoEscolhido | null
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
  return `/web/perdas/lancamentos?${p}`
}

/** "3 un · 12,5 kg" (só as unidades que aparecem). */
function totais(lista: LancamentoPerda[]): string {
  const soma = { UN: 0, KG: 0 }
  for (const l of lista) soma[l.unidade] += Number(l.quantidade)
  return (["UN", "KG"] as const)
    .filter((u) => soma[u] > 0)
    .map((u) => formatarQuantidade(soma[u], u))
    .join(" · ")
}

export function Perdas() {
  const id = useId()
  const queryClient = useQueryClient()
  const [hoje] = useState(() => dataIso(new Date()))
  const [rascunho, setRascunho] = useState<Filtros>({ inicio: somarDias(hoje, -6), fim: hoje, loja: TODAS, produto: null })
  const [aplicados, setAplicados] = useState<Filtros>(rascunho)
  const [erroFiltro, setErroFiltro] = useState<string | null>(null)
  // null = fechado; "novo" = lançar; um lançamento = corrigir.
  const [formulario, setFormulario] = useState<"novo" | LancamentoPerda | null>(null)
  const [apagando, setApagando] = useState<LancamentoPerda | null>(null)

  const lojas = useQuery({ queryKey: ["lojas"], queryFn: () => apiJson<LojaWeb[]>("/web/lojas") })
  const lista = useQuery({
    queryKey: ["perdas", "lancamentos", aplicados.inicio, aplicados.fim, aplicados.loja, aplicados.produto?.id ?? null],
    queryFn: () => apiJson<LancamentoPerda[]>(caminho(aplicados)),
  })

  async function recarregar() {
    // A perda alimenta a Visão geral e a consulta: tudo que leu perda fica velho.
    await queryClient.invalidateQueries({ queryKey: ["perdas"] })
    await queryClient.invalidateQueries({ queryKey: ["consulta"] })
    await queryClient.invalidateQueries({ queryKey: ["inicio"] })
  }

  const salvar = useMutation({
    mutationFn: ({ editando, corpo }: { editando: LancamentoPerda | null; corpo: object }) =>
      editando
        ? apiJson<LancamentoPerda>(`/web/perdas/lancamentos/${editando.id}`, { method: "PUT", json: corpo })
        : apiJson<LancamentoPerda>("/web/perdas/lancamentos", { method: "POST", json: corpo }),
    onSuccess: async (l, { editando }) => {
      toast.success(
        `${editando ? "Lançamento corrigido" : "Perda lançada"}: ${l.produto.nome}, ${formatarQuantidade(l.quantidade, l.unidade)} em ${formatarData(l.data)}.`,
      )
      setFormulario(null)
      await recarregar()
    },
  })
  const apagar = useMutation({
    mutationFn: (l: LancamentoPerda) => apiFetch(`/web/perdas/lancamentos/${l.id}`, { method: "DELETE" }),
    onSuccess: async (_r, l) => {
      toast.success(`Lançamento apagado: ${l.produto.nome}, ${formatarQuantidade(l.quantidade, l.unidade)} em ${formatarData(l.data)}.`)
      setApagando(null)
      await recarregar()
    },
  })

  function aplicar(evento: React.FormEvent) {
    evento.preventDefault()
    const erro = erroDoPeriodo(rascunho)
    setErroFiltro(erro)
    if (!erro) setAplicados(rascunho)
  }

  function fecharFormulario() {
    setFormulario(null)
    salvar.reset()
  }

  return (
    <section className="flex flex-col gap-8">
      <CabecalhoPagina
        sobretitulo="Operação"
        titulo="Perdas"
        descricao="O que as lojas descartaram: vencido, avariado ou outro motivo. A loja lança no app; aqui você confere, lança por ela e corrige."
        acoes={
          <Button onClick={() => setFormulario("novo")}>
            <Plus aria-hidden="true" />
            Lançar perda
          </Button>
        }
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
                    {rotuloLoja(l)}
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
          <Button type="submit" variant="secondary">Filtrar</Button>
        </div>
      </form>

      <div aria-live="polite" className="flex flex-col gap-4">
        {lista.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{lista.error.message}</AlertTitle>
            <AlertDescription>Confira os filtros e tente de novo.</AlertDescription>
          </Alert>
        ) : lista.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : lista.data.length === 0 ? (
          <div className="rounded-lg bg-surface p-6">
            <p>
              Nenhuma perda lançada de {formatarData(aplicados.inicio)} a {formatarData(aplicados.fim)}
              {aplicados.loja !== TODAS || aplicados.produto ? " com estes filtros" : ""}.
            </p>
            <p className="mt-1 text-muted-foreground">
              Sem lançamento, o sistema não sabe se a loja não perdeu nada ou se não lançou. Confirme com as lojas.
            </p>
          </div>
        ) : (
          <>
            <p className="text-muted-foreground">
              {contar(lista.data.length, "lançamento", "lançamentos")} · total {totais(lista.data)}
            </p>
            <Table aria-label="Lançamentos de perda">
              <TableHeader>
                <TableRow>
                  <TableHead>Dia</TableHead>
                  <TableHead>Loja</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead className="text-right">Quantidade</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Lançado por</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lista.data.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="numero whitespace-nowrap">{formatarData(l.data)}</TableCell>
                    <TableCell>{rotuloLoja(l.loja)}</TableCell>
                    <TableCell className="font-semibold">{l.produto.nome}</TableCell>
                    <TableCell className="numero text-right whitespace-nowrap">{formatarQuantidade(l.quantidade, l.unidade)}</TableCell>
                    <TableCell>
                      {rotuloMotivo(l.motivo)}
                      {l.observacao && <span className="block text-sm text-muted-foreground">{l.observacao}</span>}
                    </TableCell>
                    <TableCell>
                      {l.lancado_por}
                      {l.alterado_por && (
                        <span className="block text-sm text-muted-foreground">Corrigido por {l.alterado_por}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button variant="ghost" aria-label={`Corrigir: ${l.produto.nome} de ${formatarData(l.data)}, ${l.loja.nome}`}
                        onClick={() => setFormulario(l)}>
                        <Pencil aria-hidden="true" />
                        Corrigir
                      </Button>
                      <Button variant="ghost" aria-label={`Apagar: ${l.produto.nome} de ${formatarData(l.data)}, ${l.loja.nome}`}
                        onClick={() => setApagando(l)}>
                        <Trash2 aria-hidden="true" />
                        Apagar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </div>

      <Dialog open={formulario !== null} onOpenChange={(a) => !a && fecharFormulario()}>
        <DialogContent className="sm:max-w-xl">
          {formulario !== null && (
            <FormularioPerda
              editando={formulario === "novo" ? null : formulario}
              lojas={(lojas.data ?? []).filter((l) => l.ativo)}
              hoje={hoje}
              salvando={salvar.isPending}
              erroApi={salvar.isError ? salvar.error.message : null}
              aoFechar={fecharFormulario}
              aoSalvar={(corpo) => salvar.mutate({ editando: formulario === "novo" ? null : formulario, corpo })}
            />
          )}
        </DialogContent>
      </Dialog>

      <DialogoConfirmar
        aberto={apagando !== null}
        titulo="Apagar este lançamento de perda?"
        descricao={
          apagando && (
            <p>
              {apagando.produto.nome}: {formatarQuantidade(apagando.quantidade, apagando.unidade)} em{" "}
              {formatarData(apagando.data)}, {rotuloLoja(apagando.loja)} ({rotuloMotivo(apagando.motivo).toLowerCase()}).
              A perda do dia é refeita sem ele.
            </p>
          )
        }
        verbo="Apagar lançamento"
        verboCarregando="Apagando…"
        perigo
        carregando={apagar.isPending}
        erroApi={apagar.isError ? apagar.error.message : null}
        dica="Recarregue a página e tente de novo."
        aoFechar={() => {
          setApagando(null)
          apagar.reset()
        }}
        aoConfirmar={() => apagando && apagar.mutate(apagando)}
      />
      <Toaster position="bottom-right" />
    </section>
  )
}

const RADIO = "size-5 shrink-0 accent-primary"

function FormularioPerda({
  editando,
  lojas,
  hoje,
  salvando,
  erroApi,
  aoFechar,
  aoSalvar,
}: {
  editando: LancamentoPerda | null
  lojas: LojaWeb[]
  hoje: string
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoSalvar: (corpo: object) => void
}) {
  const id = useId()
  const [loja, setLoja] = useState(lojas.length === 1 ? String(lojas[0].id) : "")
  const [produto, setProduto] = useState<ProdutoEscolhido | null>(null)
  const [dia, setDia] = useState(hoje)
  const [quantidade, setQuantidade] = useState(editando ? String(Number(editando.quantidade)).replace(".", ",") : "")
  const [motivo, setMotivo] = useState<string>(editando?.motivo ?? "")
  const [observacao, setObservacao] = useState(editando?.observacao ?? "")
  const [erros, setErros] = useState<Record<string, string>>({})

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    const e: Record<string, string> = {}
    if (!editando) {
      if (!loja) e.loja = "Escolha a loja."
      if (!produto) e.produto = "Escolha o produto."
      if (!dia) e.dia = "Informe o dia da perda."
      else if (dia > hoje) e.dia = "Não dá para lançar perda de um dia que ainda não chegou."
    }
    const q = quantidade.trim().replace(",", ".")
    if (!/^\d+(\.\d+)?$/.test(q) || Number(q) <= 0) e.quantidade = "Informe uma quantidade maior que zero, como 3 ou 1,5."
    else if (q.includes(".") && q.split(".")[1].length > 3) e.quantidade = "Use no máximo 3 casas depois da vírgula."
    if (!motivo) e.motivo = "Escolha o motivo."
    if (motivo === "outro" && !observacao.trim()) e.observacao = "Com o motivo “Outro”, escreva numa linha o que aconteceu."
    setErros(e)
    if (Object.keys(e).length > 0) return
    const base = { quantidade: q, motivo, observacao: observacao.trim() || null }
    aoSalvar(editando ? base : { ...base, loja_id: Number(loja), produto_id: produto!.id, data: dia })
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
        <DialogTitle>{editando ? "Corrigir lançamento de perda" : "Lançar perda"}</DialogTitle>
        <DialogDescription>
          {editando
            ? `${editando.produto.nome}, ${rotuloLoja(editando.loja)}, ${formatarData(editando.data)}. Produto, loja e dia não mudam: para isso, apague e lance de novo.`
            : "Pela loja, em qualquer dia até hoje. A loja também lança pelo app."}
        </DialogDescription>
      </DialogHeader>

      {!editando && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-loja`}>Loja</Label>
            <Select value={loja} onValueChange={setLoja}>
              <SelectTrigger id={`${id}-loja`} className="w-full" {...invalido("loja")}>
                <SelectValue placeholder="Escolha a loja" />
              </SelectTrigger>
              <SelectContent>
                {lojas.map((l) => (
                  <SelectItem key={l.id} value={String(l.id)}>{rotuloLoja(l)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {erro("loja")}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-dia`}>Dia da perda</Label>
            <Input id={`${id}-dia`} type="date" max={hoje} value={dia} onChange={(e) => setDia(e.target.value)} {...invalido("dia")} />
            {erro("dia")}
          </div>
          <div className="flex flex-col gap-2 sm:col-span-2">
            <Label htmlFor={`${id}-produto`}>Produto</Label>
            <SeletorProduto id={`${id}-produto`} valor={produto} textoVazio="Buscar produto" oferecerTodos={false}
              aoMudar={setProduto} />
            {erro("produto")}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-quantidade`}>
          Quantidade perdida{editando ? ` (${editando.unidade.toLowerCase()})` : " (na unidade do produto)"}
        </Label>
        <Input id={`${id}-quantidade`} inputMode="decimal" className="numero max-w-40 text-right" value={quantidade}
          onChange={(e) => setQuantidade(e.target.value)} {...invalido("quantidade")} />
        {erro("quantidade")}
      </div>

      <fieldset className="flex flex-col gap-3" aria-describedby={erros.motivo ? `${id}-motivo-erro` : undefined}>
        <legend className="text-sm font-semibold">Motivo</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {MOTIVOS_PERDA.map((m) => (
            <label key={m.valor} className="flex min-h-11 items-center gap-2">
              <input type="radio" name={`${id}-motivo`} className={RADIO} checked={motivo === m.valor}
                onChange={() => setMotivo(m.valor)} />
              {m.rotulo}
            </label>
          ))}
        </div>
        {erro("motivo")}
      </fieldset>

      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-obs`}>{motivo === "outro" ? "O que aconteceu?" : "Observação (opcional)"}</Label>
        <Textarea id={`${id}-obs`} rows={2} maxLength={TAMANHO_OBSERVACAO} value={observacao}
          onChange={(e) => setObservacao(e.target.value)} {...invalido("observacao")} />
        {erro("observacao")}
      </div>

      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{editando ? "A correção não foi salva." : "A perda não foi lançada."} {erroApi}</AlertTitle>
          <AlertDescription>Corrija e tente de novo.</AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>Cancelar</Button>
        <Button type="submit" carregando={salvando} textoCarregando="Salvando…">
          {editando ? "Salvar correção" : "Lançar perda"}
        </Button>
      </DialogFooter>
    </form>
  )
}
