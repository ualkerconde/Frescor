/*
 * Qualidade da previsão (F9): o teste no passado do backend
 * (GET /previsoes/qualidade), em linguagem de loja. Para cada dia das
 * últimas 4 semanas, o sistema previu só com os dados de antes e comparou
 * com o que foi vendido.
 *
 * - "Errou em média X% do volume" (WAPE).
 * - "Tende a sobrar / faltar Y%" (sinal do viés: positivo = sobra).
 * - Comparação com repetir a venda da semana passada (o "ingênuo"): se o
 *   motor não ganhar, a tela avisa.
 * Um bloco por unidade (UN e KG não se misturam).
 *
 * É calculada na hora (~1 s no seed): o resultado fica guardado por 10
 * minutos por loja + produto e não depende da data escolhida.
 */
import { useQuery } from "@tanstack/react-query"
import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { apiJson } from "@/lib/api/cliente"
import type { QualidadePrevisao, QualidadeUnidade } from "@/lib/api/tipos"
import { contar, formatarData, formatarPercentual } from "@/lib/formato"

const DEZ_MINUTOS = 10 * 60 * 1000

function textoVies(vies: string): string {
  const v = Number(vies)
  if (formatarPercentual(Math.abs(v)) === "0%") return "Nem sobra nem falta, na média"
  return v > 0 ? `Tende a sobrar ${formatarPercentual(v)}` : `Tende a faltar ${formatarPercentual(-v)}`
}

function BlocoUnidade({ q }: { q: QualidadeUnidade }) {
  const nome = q.unidade === "KG" ? "Produtos em quilos" : "Produtos em unidades"
  if (q.wape === null || q.vies === null) {
    return (
      <div className="rounded-lg bg-surface p-4">
        <p className="text-sm font-semibold text-muted-foreground">{nome}</p>
        <p className="mt-1">Sem vendas no período para medir.</p>
      </div>
    )
  }
  return (
    <div className="rounded-lg bg-surface p-4">
      <p className="text-sm font-semibold text-muted-foreground">{nome}</p>
      <p className="mt-1 numero-destaque text-[24px]">
        Errou em média {formatarPercentual(q.wape)} do volume
      </p>
      <p className="mt-1 numero">{textoVies(q.vies)}</p>
      {q.vence_ingenuo === false ? (
        <p className="mt-2 flex items-start gap-2 text-warning">
          <TriangleAlert className="size-5 shrink-0" aria-hidden="true" />
          <span className="numero">
            Repetir a venda da semana passada teria errado menos ({formatarPercentual(q.ingenuo_wape ?? 0)}). Use os
            números com cuidado e confira os produtos de maior volume.
          </span>
        </p>
      ) : q.vence_ingenuo === true ? (
        <p className="mt-2 flex items-start gap-2 text-success">
          <CircleCheck className="size-5 shrink-0" aria-hidden="true" />
          <span className="numero">
            Melhor que repetir a venda da semana passada (que errou {formatarPercentual(q.ingenuo_wape ?? 0)}).
          </span>
        </p>
      ) : null}
      <p className="mt-2 text-sm text-muted-foreground numero">
        {contar(q.pares, "dia de produto medido", "dias de produto medidos")} (loja × produto × dia)
      </p>
    </div>
  )
}

export function CardQualidade({ lojaId, produtoId }: { lojaId: number | null; produtoId: number | null }) {
  const qualidade = useQuery({
    queryKey: ["previsoes", "qualidade", lojaId, produtoId],
    queryFn: () => {
      const q = new URLSearchParams()
      if (lojaId !== null) q.set("loja_id", String(lojaId))
      if (produtoId !== null) q.set("produto_id", String(produtoId))
      const busca = q.toString()
      return apiJson<QualidadePrevisao>(`/previsoes/qualidade${busca ? `?${busca}` : ""}`)
    },
    staleTime: DEZ_MINUTOS,
  })

  return (
    <section aria-labelledby="titulo-qualidade" className="painel p-6">
      <h2 id="titulo-qualidade" className="text-[22px]">
        Qualidade da previsão
      </h2>
      {qualidade.isPending ? (
        <p className="mt-2 text-muted-foreground" aria-live="polite">
          Medindo a qualidade nas últimas 4 semanas… (leva alguns segundos)
        </p>
      ) : qualidade.isError ? (
        <Alert variant="erro" className="mt-3">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>Não foi possível medir a qualidade. {qualidade.error.message}</AlertTitle>
        </Alert>
      ) : (
        <>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Teste de {formatarData(qualidade.data.data_inicio)} a {formatarData(qualidade.data.data_fim)}: para cada dia,
            o sistema previu só com as vendas de antes e comparou com o que foi vendido de verdade.
          </p>
          {qualidade.data.por_unidade.length === 0 ? (
            <p className="mt-3">Ainda não há vendas suficientes para medir. Importe as vendas das últimas semanas.</p>
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {qualidade.data.por_unidade.map((q) => (
                <BlocoUnidade key={q.unidade} q={q} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
