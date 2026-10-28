/*
 * Tela da distribuição e do romaneio (Fase 5 / E10), pela skill Frescor.
 * Carregada só quando aberta (React.lazy em App.tsx).
 *
 * - Dia de entrega na URL (padrão: hoje). A tela lista as ordens com
 *   entrega nesse dia (D92), cada uma com o que dá para fazer na situação
 *   dela (BlocoOrdem): registrar a produção, gerar, ajustar e aprovar o
 *   romaneio, imprimir e registrar a saída; depois, acompanhar o
 *   recebimento por loja.
 * - Sem ordem no dia: estado vazio com o caminho para a ordem de produção.
 * - Abaixo, as diferenças confirmadas pelas lojas no recebimento (D78).
 */
import { useId, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleAlert } from "lucide-react"
import { Link, useSearchParams } from "react-router"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Toaster } from "@/components/ui/sonner"
import { apiJson } from "@/lib/api/cliente"
import type { DistribuicaoDoDia } from "@/lib/api/tipos"
import { dataIso, formatarData } from "@/lib/formato"
import { BlocoOrdem } from "./distribuicao/BlocoOrdem"
import { Divergencias } from "./distribuicao/Divergencias"

function hoje(): string {
  return dataIso(new Date())
}

export function Distribuicao() {
  const [params, setParams] = useSearchParams()
  const data = params.get("data") || hoje()
  const [dataDigitada, setDataDigitada] = useState(data)
  const [dataVista, setDataVista] = useState(data)
  if (data !== dataVista) {
    setDataVista(data)
    setDataDigitada(data)
  }
  const queryClient = useQueryClient()
  const id = useId()

  const dia = useQuery({
    queryKey: ["distribuicao", "dia", data],
    queryFn: () => apiJson<DistribuicaoDoDia>(`/distribuicao/romaneios?data_entrega=${data}`),
  })

  function atualizar() {
    return queryClient.invalidateQueries({ queryKey: ["distribuicao"] })
  }

  return (
    <section className="flex flex-col gap-8">
      <div>
        <h1 className="text-[28px]">Distribuição e romaneio</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Registre o que foi produzido, monte o romaneio com quanto vai para cada loja, imprima e registre a saída.
          Depois, acompanhe a confirmação de cada loja.
        </p>
      </div>

      <div className="grid gap-4 rounded-lg border border-line bg-card p-6 md:grid-cols-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-data`}>Dia de entrega</Label>
          <Input
            id={`${id}-data`}
            type="date"
            value={dataDigitada}
            onChange={(e) => {
              setDataDigitada(e.target.value)
              if (e.target.value) setParams({ data: e.target.value })
            }}
          />
        </div>
      </div>

      <div aria-live="polite" className="flex flex-col gap-8">
        {dia.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{dia.error.message}</AlertTitle>
            <AlertDescription>Recarregue a página. Se continuar, tente de novo em alguns minutos.</AlertDescription>
          </Alert>
        ) : dia.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : dia.data.ordens.length === 0 ? (
          <div className="rounded-lg bg-surface p-6">
            <p>Nenhuma ordem de produção com entrega em {formatarData(data)}.</p>
            <p className="mt-1 text-muted-foreground">
              O romaneio sai da ordem de produção aprovada.{" "}
              <Link to="/producao" className="font-semibold text-primary underline">
                Abrir a ordem de produção
              </Link>
            </p>
          </div>
        ) : (
          dia.data.ordens.map((o) => <BlocoOrdem key={o.ordem_id} ordem={o} atualizar={atualizar} />)
        )}
      </div>

      <Divergencias dataEntrega={data} />

      {/* Avisos de sucesso montados aqui (e não no layout): a biblioteca vai no pacote desta tela. */}
      <Toaster position="bottom-right" />
    </section>
  )
}
