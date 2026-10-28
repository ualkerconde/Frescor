/*
 * Resumo da ordem no topo (N9): situação, quem gerou/aprovou, quanto
 * produzir e quanto distribuir por unidade (UN e KG não se somam) e o
 * bloco "Confira estes", que cita pelo nome o que pede atenção: linhas sem
 * quantidade (bloqueiam a aprovação, D59) e os outros avisos.
 *
 * Skill Frescor: rótulo 14px --muted, número grande em Sora --secondary.
 */
import { CircleAlert, TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { ItemOrdem, OrdemDetalhe, Unidade } from "@/lib/api/tipos"
import { contar, diaDaSemana, formatarData, formatarQuantidade } from "@/lib/formato"
import { descreverAviso } from "./avisos"
import { SituacaoOrdem } from "./Marcadores"

const MAXIMO_NOMES = 5
const horario = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" })

/** Data e hora gravadas em UTC sem fuso pelo backend -> hora local do navegador. */
function quando(isoUtc: string): string {
  return horario.format(new Date(isoUtc.endsWith("Z") || isoUtc.includes("+") ? isoUtc : `${isoUtc}Z`))
}

function somaPorUnidade(itens: ItemOrdem[]): { unidade: Unidade; total: number }[] {
  const somas = new Map<Unidade, number>()
  for (const i of itens) somas.set(i.unidade, (somas.get(i.unidade) ?? 0) + Number(i.total_final))
  return [...somas.entries()].sort().map(([unidade, total]) => ({ unidade, total }))
}

function Numeros({ rotulo, itens }: { rotulo: string; itens: ItemOrdem[] }) {
  const somas = somaPorUnidade(itens)
  if (somas.length === 0) return null
  return (
    <>
      {somas.map((s) => (
        <div key={`${rotulo}-${s.unidade}`} className="painel-kpi p-5">
          <p className="text-sm text-muted-foreground">
            {rotulo} em {s.unidade === "KG" ? "quilos" : "unidades"}
          </p>
          <p className="mt-1 numero-destaque text-[clamp(30px,2.6vw,40px)] leading-tight whitespace-nowrap">
            {formatarQuantidade(s.total, s.unidade)}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {contar(itens.filter((i) => i.unidade === s.unidade).length, "produto", "produtos")}
          </p>
        </div>
      ))}
    </>
  )
}

interface Ocorrencia {
  produto: string
  loja: string
}

function listaNomes(ocorrencias: Ocorrencia[]): string {
  const visiveis = ocorrencias.slice(0, MAXIMO_NOMES).map((o) => `${o.produto} (${o.loja})`)
  const resto = ocorrencias.length - visiveis.length
  return visiveis.join("; ") + (resto > 0 ? ` e mais ${resto}` : "")
}

export function ResumoOrdem({ ordem }: { ordem: OrdemDetalhe }) {
  const produzidos = ordem.itens.filter((i) => i.tipo_abastecimento === "produzido")
  const distribuidos = ordem.itens.filter((i) => i.tipo_abastecimento === "distribuido")

  const semQuantidade: Ocorrencia[] = []
  const porAviso = new Map<string, Ocorrencia[]>()
  for (const item of ordem.itens) {
    for (const l of item.linhas) {
      const o = { produto: item.produto.nome, loja: l.loja.codigo ?? l.loja.nome }
      if (l.quantidade_final === null) semQuantidade.push(o)
      for (const a of l.avisos) {
        if (a === "sem_calendario" || a === "sem_previsao") continue // já estão em "sem quantidade"
        porAviso.set(a, [...(porAviso.get(a) ?? []), o])
      }
    }
  }

  return (
    <section aria-label="Resumo da ordem" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[22px]">
          Produção de {diaDaSemana(ordem.data_producao)}, {formatarData(ordem.data_producao)}
        </h2>
        <SituacaoOrdem status={ordem.status} />
      </div>
      <p className="-mt-2 text-muted-foreground">
        Entrega nas lojas em {formatarData(ordem.data_entrega)}. Gerada em {quando(ordem.gerado_em)}
        {ordem.gerado_por ? ` por ${ordem.gerado_por}` : ""}
        {ordem.status === "aprovada" && ordem.aprovado_em
          ? `; aprovada em ${quando(ordem.aprovado_em)}${ordem.aprovado_por ? ` por ${ordem.aprovado_por}` : ""}.`
          : "."}
        {ordem.status === "rascunho" && ordem.linhas_editadas > 0 && ` ${contar(ordem.linhas_editadas, "linha ajustada", "linhas ajustadas")}.`}
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Numeros rotulo="Produzir" itens={produzidos} />
        <Numeros rotulo="Distribuir" itens={distribuidos} />
      </div>
      {semQuantidade.length > 0 && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>
            {contar(semQuantidade.length, "linha está", "linhas estão")} sem quantidade: {listaNomes(semQuantidade)}.
          </AlertTitle>
          <AlertDescription>
            {ordem.status === "rascunho"
              ? "Abra o produto e use “Ajustar” para informar quanto mandar (0 vale). A ordem só é aprovada com todas preenchidas."
              : "Essas linhas ficaram sem quantidade."}
          </AlertDescription>
        </Alert>
      )}
      {porAviso.size > 0 && (
        <Alert variant="aviso">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Confira estes</AlertTitle>
          <AlertDescription>
            <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
              {[...porAviso.entries()].map(([codigo, ocorrencias]) => (
                <li key={codigo}>
                  <span className="font-semibold">{descreverAviso(codigo).rotulo}</span> —{" "}
                  {descreverAviso(codigo).explicacao} {listaNomes(ocorrencias)}.
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </section>
  )
}
