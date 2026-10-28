/*
 * Etiquetas da distribuição (skill Frescor: pill 14px 600, fundo *-bg e
 * texto na cor semântica; cor nunca sozinha, sempre com ícone e texto).
 */
import { CircleCheck, Clock, PackageCheck, PencilLine, Truck, TriangleAlert } from "lucide-react"
import { cn } from "cn"
import type { SituacaoDaEntrega } from "@/lib/api/tipos"
import { descreverSituacao, type GravidadeSituacao } from "./situacao"

const PILL = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap"

const ESTILO: Record<GravidadeSituacao, string> = {
  sucesso: "bg-success-bg text-success",
  aviso: "bg-warning-bg text-warning",
  andamento: "bg-highlight text-foreground",
  neutra: "bg-surface text-foreground",
}

const ICONE: Record<SituacaoDaEntrega["situacao"], typeof Truck> = {
  aguardando_saida: Clock,
  a_caminho: Truck,
  sem_confirmacao: TriangleAlert,
  recebida: PackageCheck,
  confirmada_com_atraso: PackageCheck,
}

export function EtiquetaSituacao({ situacao }: { situacao: SituacaoDaEntrega }) {
  const d = descreverSituacao(situacao)
  const Icone = d.gravidade === "aviso" ? TriangleAlert : ICONE[situacao.situacao]
  return (
    <span className={cn(PILL, ESTILO[d.gravidade])} title={d.explicacao}>
      <Icone className="size-4" aria-hidden="true" />
      {d.rotulo}
      <span className="sr-only">: {d.explicacao}</span>
    </span>
  )
}

export function SituacaoRomaneio({ status }: { status: "rascunho" | "aprovado" }) {
  return status === "aprovado" ? (
    <span className={cn(PILL, "bg-success-bg text-success")}>
      <CircleCheck className="size-4" aria-hidden="true" />
      Aprovado
    </span>
  ) : (
    <span className={cn(PILL, "bg-highlight text-foreground")}>
      <PencilLine className="size-4" aria-hidden="true" />
      Rascunho
    </span>
  )
}
