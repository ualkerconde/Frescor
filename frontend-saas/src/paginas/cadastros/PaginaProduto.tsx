/*
 * Cadastro de um produto (Fase 6 / C4): o formulário completo e, no produto
 * já cadastrado, as lojas da central (LojasDoProduto).
 *
 * - Novo: código obrigatório (D97) e, marcado por padrão, "ativar em todas
 *   as lojas ativas da central" (D101). Depois de cadastrar, a tela vai
 *   para o produto, onde dá para ajustar as lojas.
 * - Editar: a unidade fica travada quando o produto já tem histórico
 *   (D98); um código existente não pode ser apagado (D97).
 * - Não há apagar: "Produto ativo" desmarcado tira o produto do app, da
 *   previsão e da ordem (D99).
 * Uma ação principal: "Cadastrar produto" / "Salvar produto".
 */
import { useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, CircleAlert } from "lucide-react"
import { Link, useNavigate, useParams } from "react-router"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { apiJson } from "@/lib/api/cliente"
import type { ProdutoDetalhe, ProdutoEnvio, SetorProducao } from "@/lib/api/tipos"
import {
  DIAS,
  SEM_SETOR,
  camposDoProduto,
  camposVazios,
  descreverDias,
  montarEnvio,
  type CamposProduto,
  type ErrosProduto,
} from "./formularioProduto"
import { LojasDoProduto } from "./LojasDoProduto"

function Voltar() {
  return (
    <Link to="/cadastros/produtos" className="inline-flex items-center gap-1 font-semibold text-primary underline">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Voltar para a lista de produtos
    </Link>
  )
}

export function NovoProduto() {
  const navegar = useNavigate()
  const queryClient = useQueryClient()
  const criar = useMutation({
    mutationFn: (envio: ProdutoEnvio) => apiJson<ProdutoDetalhe>("/web/produtos", { method: "POST", json: envio }),
    onSuccess: async (p) => {
      toast.success(`Produto “${p.nome}” cadastrado.`)
      queryClient.setQueryData(["cadastro", "produto", String(p.id)], p)
      await queryClient.invalidateQueries({ queryKey: ["cadastro", "produtos"] })
      navegar(`/cadastros/produtos/${p.id}`)
    },
  })
  return (
    <div className="flex flex-col gap-6">
      <Voltar />
      <h2 className="text-[22px]">Novo produto</h2>
      <FormularioProduto
        novo
        inicial={camposVazios()}
        codigoAntigo={null}
        temHistorico={false}
        setorAtual={null}
        salvando={criar.isPending}
        erroApi={criar.isError ? criar.error.message : null}
        aoSalvar={(envio) => criar.mutate(envio)}
      />
    </div>
  )
}

export function EditarProduto() {
  const { produtoId = "" } = useParams()
  const queryClient = useQueryClient()
  const produto = useQuery({
    queryKey: ["cadastro", "produto", produtoId],
    queryFn: () => apiJson<ProdutoDetalhe>(`/web/produtos/${produtoId}`),
  })
  const salvar = useMutation({
    mutationFn: (envio: ProdutoEnvio) =>
      apiJson<ProdutoDetalhe>(`/web/produtos/${produtoId}`, { method: "PATCH", json: envio }),
    onSuccess: async (p) => {
      toast.success("Produto salvo. Vale a partir da próxima previsão e da próxima ordem.")
      queryClient.setQueryData(["cadastro", "produto", produtoId], p)
      await queryClient.invalidateQueries({ queryKey: ["cadastro", "produtos"] })
    },
  })

  if (produto.isError) {
    return (
      <div className="flex flex-col gap-6">
        <Voltar />
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{produto.error.message}</AlertTitle>
          <AlertDescription>Volte para a lista e escolha o produto de novo.</AlertDescription>
        </Alert>
      </div>
    )
  }
  if (produto.isPending) return <p className="text-muted-foreground">Carregando…</p>
  const p = produto.data
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4">
        <Voltar />
        <h2 className="text-[22px]">{p.codigo ? `${p.codigo} · ${p.nome}` : p.nome}</h2>
      </div>
      <FormularioProduto
        // Recomeça o formulário quando o produto salvo volta da API.
        key={JSON.stringify(p)}
        novo={false}
        inicial={camposDoProduto(p)}
        codigoAntigo={p.codigo}
        temHistorico={p.tem_historico}
        setorAtual={p.setor}
        salvando={salvar.isPending}
        erroApi={salvar.isError ? salvar.error.message : null}
        aoSalvar={(envio) => salvar.mutate(envio)}
      />
      <LojasDoProduto produtoId={p.id} produtoAtivo={p.ativo} />
    </div>
  )
}

function Erro({ id, texto }: { id: string; texto?: string }) {
  if (!texto) return null
  return (
    <p id={id} className="flex items-center gap-1 text-sm text-error">
      <CircleAlert className="size-4" aria-hidden="true" />
      {texto}
    </p>
  )
}

const CAIXA = "size-5 shrink-0 accent-primary"
const GRUPO = "grid gap-4 rounded-lg border border-line bg-card p-6"

function FormularioProduto({
  novo,
  inicial,
  codigoAntigo,
  temHistorico,
  setorAtual,
  salvando,
  erroApi,
  aoSalvar,
}: {
  novo: boolean
  inicial: CamposProduto
  codigoAntigo: string | null
  temHistorico: boolean
  setorAtual: { id: number; nome: string } | null
  salvando: boolean
  erroApi: string | null
  aoSalvar: (envio: ProdutoEnvio) => void
}) {
  const id = useId()
  const [c, setC] = useState<CamposProduto>(inicial)
  const [erros, setErros] = useState<ErrosProduto>({})
  const setores = useQuery({
    queryKey: ["cadastro", "setores"],
    queryFn: () => apiJson<SetorProducao[]>("/producao/setores"),
  })
  // Na escolha: os setores ativos e, se for o caso, o setor inativo que o produto já tem.
  const opcoesSetor = (setores.data ?? []).filter((s) => s.ativo || s.id === setorAtual?.id)

  function mudar<K extends keyof CamposProduto>(campo: K, valor: CamposProduto[K]) {
    setC((atual) => ({ ...atual, [campo]: valor }))
  }

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    const r = montarEnvio(c, novo, codigoAntigo)
    if (!r.ok) {
      setErros(r.erros)
      return
    }
    setErros({})
    aoSalvar(r.envio)
  }

  function campo(nome: keyof CamposProduto) {
    const erro = erros[nome]
    return {
      id: `${id}-${nome}`,
      "aria-invalid": erro !== undefined,
      "aria-describedby": erro ? `${id}-${nome}-erro` : undefined,
    }
  }

  return (
    <form onSubmit={enviar} noValidate className="flex flex-col gap-6">
      <fieldset className={GRUPO}>
        <legend className="px-1 font-heading text-lg font-semibold text-heading">Identificação</legend>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2 md:col-span-3">
            <Label htmlFor={`${id}-nome`}>Nome do produto</Label>
            <Input {...campo("nome")} value={c.nome} onChange={(e) => mudar("nome", e.target.value)} maxLength={255} />
            <Erro id={`${id}-nome-erro`} texto={erros.nome} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-codigo`}>Código</Label>
            <Input {...campo("codigo")} value={c.codigo} onChange={(e) => mudar("codigo", e.target.value)} maxLength={64} />
            <p className="text-sm text-muted-foreground">O mesmo código dos arquivos de vendas e perdas.</p>
            <Erro id={`${id}-codigo-erro`} texto={erros.codigo} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-codigo_barras`}>Código de barras (opcional)</Label>
            <Input
              {...campo("codigo_barras")}
              inputMode="numeric"
              value={c.codigo_barras}
              onChange={(e) => mudar("codigo_barras", e.target.value)}
              maxLength={64}
            />
            <p className="text-sm text-muted-foreground">Usado pelo leitor do app na contagem.</p>
          </div>
        </div>
        <label className="flex items-center gap-3 font-semibold">
          <input type="checkbox" className={CAIXA} checked={c.ativo} onChange={(e) => mudar("ativo", e.target.checked)} />
          Produto ativo
        </label>
        <p className="-mt-2 text-sm text-muted-foreground">
          Desmarcado, o produto sai da contagem no app, da previsão e da ordem de produção. O histórico continua.
        </p>
      </fieldset>

      <fieldset className={GRUPO}>
        <legend className="px-1 font-heading text-lg font-semibold text-heading">Unidade e produção</legend>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-unidade`}>Unidade</Label>
            <Select
              value={c.unidade}
              disabled={temHistorico}
              onValueChange={(v) => mudar("unidade", v as CamposProduto["unidade"])}
            >
              <SelectTrigger id={`${id}-unidade`} className="w-full" aria-describedby={`${id}-unidade-ajuda`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="UN">Unidade (un)</SelectItem>
                <SelectItem value="KG">Quilo (kg)</SelectItem>
              </SelectContent>
            </Select>
            <p id={`${id}-unidade-ajuda`} className="text-sm text-muted-foreground">
              {temHistorico
                ? "Não muda: o produto já tem vendas, perdas, contagens ou previsões nesta unidade."
                : "Como o produto é vendido e contado."}
            </p>
          </div>
          {c.unidade === "KG" && (
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${id}-peso_medio_kg`}>Peso médio de uma peça (opcional)</Label>
              <div className="flex items-center gap-2">
                <Input
                  {...campo("peso_medio_kg")}
                  inputMode="decimal"
                  className="max-w-40 text-right numero"
                  value={c.peso_medio_kg}
                  onChange={(e) => mudar("peso_medio_kg", e.target.value)}
                />
                <span className="font-semibold text-muted-foreground">kg</span>
              </div>
              <p className="text-sm text-muted-foreground">Vazio: a loja pesa o produto na contagem.</p>
              <Erro id={`${id}-peso_medio_kg-erro`} texto={erros.peso_medio_kg} />
            </div>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-tipo`}>Abastecimento</Label>
            <Select
              value={c.tipo_abastecimento}
              onValueChange={(v) => mudar("tipo_abastecimento", v as CamposProduto["tipo_abastecimento"])}
            >
              <SelectTrigger id={`${id}-tipo`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="produzido">Produzido na central</SelectItem>
                <SelectItem value="distribuido">Distribuído (a central só envia)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-setor`}>Setor de produção</Label>
            <Select value={c.setor_id} onValueChange={(v) => mudar("setor_id", v)}>
              <SelectTrigger id={`${id}-setor`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SEM_SETOR}>Sem setor</SelectItem>
                {opcoesSetor.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.nome}
                    {!s.ativo && " (inativo)"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">Define em qual folha o produto sai na impressão da ordem.</p>
          </div>
        </div>

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-semibold">
            {c.tipo_abastecimento === "distribuido" ? "Dias de envio" : "Dias de produção"}
          </legend>
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            {DIAS.map((d) => (
              <label key={d.valor} className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  className={CAIXA}
                  checked={c.dias.includes(d.valor)}
                  onChange={(e) =>
                    mudar("dias", e.target.checked ? [...c.dias, d.valor] : c.dias.filter((x) => x !== d.valor))
                  }
                />
                {d.rotulo}
              </label>
            ))}
          </div>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {c.dias.length === 0
              ? "Nenhum dia marcado: o produto fica sem calendário e a ordem de produção não sugere quantidade para ele (você informa à mão)."
              : `A central produz ${descreverDias(c.dias)}.`}
          </p>
        </fieldset>
      </fieldset>

      <fieldset className={GRUPO}>
        <legend className="px-1 font-heading text-lg font-semibold text-heading">Validade e margem</legend>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-dias_validade`}>Validade (opcional)</Label>
            <div className="flex items-center gap-2">
              <Input
                {...campo("dias_validade")}
                inputMode="numeric"
                className="max-w-28 text-right numero"
                value={c.dias_validade}
                onChange={(e) => mudar("dias_validade", e.target.value)}
              />
              <span className="font-semibold text-muted-foreground">dias</span>
            </div>
            <p className="text-sm text-muted-foreground">Dias depois da fabricação. Vazio: sem limite.</p>
            <Erro id={`${id}-dias_validade-erro`} texto={erros.dias_validade} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${id}-margem`}>Margem de segurança (opcional)</Label>
            <div className="flex items-center gap-2">
              <Input
                {...campo("margem")}
                inputMode="decimal"
                className="max-w-28 text-right numero"
                value={c.margem}
                onChange={(e) => mudar("margem", e.target.value)}
              />
              <span className="font-semibold text-muted-foreground">%</span>
            </div>
            <p className="text-sm text-muted-foreground">Quanto produzir a mais que a previsão. Vazio: 10%.</p>
            <Erro id={`${id}-margem-erro`} texto={erros.margem} />
          </div>
        </div>
      </fieldset>

      <fieldset className={GRUPO}>
        <legend className="px-1 font-heading text-lg font-semibold text-heading">Vigência</legend>
        <div className="flex flex-col gap-3">
          {(
            [
              ["permanente", "Permanente", "Vendido o ano todo."],
              ["temporario", "Temporário", "Vendido só a partir de uma data, até uma data, ou entre as duas."],
              ["sazonal", "Sazonal", "Volta todo ano no mesmo período (ex.: panetone, de 01/11 a 06/01)."],
            ] as const
          ).map(([valor, rotulo, ajuda]) => (
            <label key={valor} className="flex items-start gap-3">
              <input
                type="radio"
                name={`${id}-vigencia`}
                className={`${CAIXA} mt-0.5`}
                checked={c.vigencia === valor}
                onChange={() => mudar("vigencia", valor)}
              />
              <span>
                <span className="font-semibold">{rotulo}</span>
                <span className="block text-sm text-muted-foreground">{ajuda}</span>
              </span>
            </label>
          ))}
        </div>
        {c.vigencia !== "permanente" && (
          <div className="grid gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${id}-inicio`}>{c.vigencia === "sazonal" ? "Início da temporada" : "Vendido a partir de"}</Label>
              <Input {...campo("inicio")} type="date" value={c.inicio} onChange={(e) => mudar("inicio", e.target.value)} />
              <Erro id={`${id}-inicio-erro`} texto={erros.inicio} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${id}-fim`}>{c.vigencia === "sazonal" ? "Fim da temporada" : "Vendido até"}</Label>
              <Input {...campo("fim")} type="date" value={c.fim} onChange={(e) => mudar("fim", e.target.value)} />
              <Erro id={`${id}-fim-erro`} texto={erros.fim} />
            </div>
          </div>
        )}
      </fieldset>

      {novo && (
        <label className="flex items-center gap-3 font-semibold">
          <input
            type="checkbox"
            className={CAIXA}
            checked={c.habilitar_lojas}
            onChange={(e) => mudar("habilitar_lojas", e.target.checked)}
          />
          Ativar em todas as lojas ativas da central
        </label>
      )}

      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>O produto não foi salvo. {erroApi}</AlertTitle>
          <AlertDescription>Corrija o campo indicado e salve de novo.</AlertDescription>
        </Alert>
      )}
      {Object.keys(erros).length > 0 && (
        <p role="alert" className="flex items-center gap-1 text-error">
          <CircleAlert className="size-4" aria-hidden="true" />
          Confira os campos marcados.
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" carregando={salvando} textoCarregando="Salvando…">
          {novo ? "Cadastrar produto" : "Salvar produto"}
        </Button>
        <Button type="button" variant="secondary" asChild>
          <Link to="/cadastros/produtos">Cancelar</Link>
        </Button>
      </div>
    </form>
  )
}
