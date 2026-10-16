/*
 * Etiquetas da ordem de produção (skill Frescor: pill 14px 600, fundo *-bg
 * e texto na cor semântica; cor nunca sozinha, sempre com ícone e texto).
 *
 * - EtiquetaAviso: um aviso da linha (sem calendário, contagem antiga...),
 *   com a explicação completa no `title` e para o leitor de tela.
 * - IndicadorPerda: perda das 4 semanas em 4 faixas (D66, lib/perda.ts).
 *   "normal" fica sem destaque, só o número e a palavra.
 * - SituacaoOrdem: rascunho / aprovada.
 */
import { CircleAlert, CircleCheck, Info, PencilLine, TrendingDown, TriangleAlert } from "lucide-react"
import { cn } from "cn"
import { formatarPercentual } from "@/lib/formato"
import { faixaPerda, ROTULO_FAIXA, type FaixaPerda } from "@/lib/perda"
import { descreverAviso, type GravidadeAviso } from "./avisos"

const PILL = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap"

const ESTILO_AVISO: Record<GravidadeAviso, { classe: string; Icone: typeof Info }> = {
  erro: { classe: "bg-error-bg text-error", Icone: CircleAlert },
  aviso: { classe: "bg-warning-bg text-warning", Icone: TriangleAlert },
  info: { classe: "bg-surface text-foreground", Icone: Info },
}

export function EtiquetaAviso({ codigo }: { codigo: string }) {
  const aviso = descreverAviso(codigo)
  const { classe, Icone } = ESTILO_AVISO[aviso.gravidade]
  return (
    <span className={cn(PILL, classe)} title={aviso.explicacao}>
      <Icone className="size-4" aria-hidden="true" />
      {aviso.rotulo}
      <span className="sr-only">: {aviso.explicacao}</span>
    </span>
  )
}

const ESTILO_PERDA: Record<FaixaPerda, string> = {
  baixa: "bg-success-bg text-success",
  normal: "",
  alta: "bg-warning-bg text-warning",
  muito_alta: "bg-error-bg text-error",
}

export function IndicadorPerda({ taxa }: { taxa: string | null | undefined }) {
  const faixa = faixaPerda(taxa)
  if (faixa === null) return <span className="text-muted-foreground">sem venda</span>
  const texto = `${formatarPercentual(taxa as string)} · ${ROTULO_FAIXA[faixa]}`
  if (faixa === "normal") return <span className="whitespace-nowrap numero">{texto}</span>
  const Icone = faixa === "baixa" ? TrendingDown : faixa === "alta" ? TriangleAlert : CircleAlert
  return (
    <span className={cn(PILL, "numero", ESTILO_PERDA[faixa])}>
      <Icone className="size-4" aria-hidden="true" />
      {texto}
    </span>
  )
}

export function SituacaoOrdem({ status }: { status: "rascunho" | "aprovada" }) {
  return status === "aprovada" ? (
    <span className={cn(PILL, "bg-success-bg text-success")}>
      <CircleCheck className="size-4" aria-hidden="true" />
      Aprovada
    </span>
  ) : (
    <span className={cn(PILL, "bg-highlight text-foreground")}>
      <PencilLine className="size-4" aria-hidden="true" />
      Rascunho
    </span>
  )
}
