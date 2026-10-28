/*
 * Divergências do recebimento (D78): o que as lojas confirmaram diferente
 * do enviado, no período escolhido (padrão: 7 dias até o dia de entrega da
 * tela; até 92 dias). Diferença negativa = chegou menos. Totais por unidade
 * (UN e KG não se somam).
 */
import { useId, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CircleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { Divergencias as RespostaDivergencias, Unidade } from "@/lib/api/tipos"
import { formatarData, formatarQuantidade, somarDias } from "@/lib/formato"
import { MOTIVOS, nomeCom } from "./situacao"

function diferenca(valor: string, unidade: Unidade): string {
  const n = Number(valor)
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${formatarQuantidade(Math.abs(n), unidade)}`
}

export function Divergencias({ dataEntrega }: { dataEntrega: string }) {
  const id = useId()
  const [fimEscolhido, setFim] = useState<string | null>(null)
  const [inicioEscolhido, setInicio] = useState<string | null>(null)
  const fim = fimEscolhido ?? dataEntrega
  const inicio = inicioEscolhido ?? somarDias(fim, -6)
  const periodoValido = inicio !== "" && fim !== "" && inicio <= fim

  const consulta = useQuery({
    queryKey: ["distribuicao", "divergencias", inicio, fim],
    queryFn: () => apiJson<RespostaDivergencias>(`/distribuicao/divergencias?data_inicio=${inicio}&data_fim=${fim}`),
    enabled: periodoValido,
  })
  const dados = consulta.data

  return (
    <section aria-labelledby={`${id}-titulo`} className="flex flex-col gap-4 rounded-lg border border-line bg-card p-6">
      <div>
        <h2 id={`${id}-titulo`} className="text-[22px]">
          Diferenças no recebimento
        </h2>
        <p className="mt-1 text-muted-foreground">
          O que as lojas confirmaram diferente do que foi enviado: falta, avaria ou a mais.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 md:max-w-xl">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-inicio`}>De</Label>
          <Input id={`${id}-inicio`} type="date" value={inicio} max={fim} onChange={(e) => setInicio(e.target.value)} />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-fim`}>Até</Label>
          <Input id={`${id}-fim`} type="date" value={fim} min={inicio} onChange={(e) => setFim(e.target.value)} />
        </div>
      </div>
      <div aria-live="polite">
        {!periodoValido ? (
          <p className="text-muted-foreground">Escolha um período com o início antes do fim.</p>
        ) : consulta.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{consulta.error.message}</AlertTitle>
            <AlertDescription>Confira o período e tente de novo.</AlertDescription>
          </Alert>
        ) : consulta.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : !dados || dados.divergencias.length === 0 ? (
          <p className="rounded-lg bg-surface p-4 text-muted-foreground">
            Nenhuma diferença confirmada pelas lojas de {formatarData(inicio)} a {formatarData(fim)}.
          </p>
        ) : (
          <>
            <Table aria-label="Diferenças no recebimento">
              <TableHeader>
                <TableRow>
                  <TableHead>Entrega</TableHead>
                  <TableHead>Loja</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead className="text-right">Enviado</TableHead>
                  <TableHead className="text-right">Recebido</TableHead>
                  <TableHead className="text-right">Diferença</TableHead>
                  <TableHead>Motivo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dados.divergencias.map((d, i) => (
                  <TableRow key={`${d.data_entrega}-${d.loja.id}-${d.produto.id}-${i}`}>
                    <TableCell className="numero">{formatarData(d.data_entrega)}</TableCell>
                    <TableCell className="whitespace-nowrap">{nomeCom(d.loja)}</TableCell>
                    <TableCell>{nomeCom(d.produto)}</TableCell>
                    <TableCell className="text-right numero">{formatarQuantidade(d.quantidade_enviada, d.unidade)}</TableCell>
                    <TableCell className="text-right numero">{formatarQuantidade(d.quantidade_recebida, d.unidade)}</TableCell>
                    <TableCell className="text-right font-semibold numero">{diferenca(d.diferenca, d.unidade)}</TableCell>
                    <TableCell>
                      {MOTIVOS[d.motivo]}
                      {d.observacao && <span className="block text-sm text-muted-foreground">{d.observacao}</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              No período:{" "}
              {dados.totais
                .map((t) => `${diferenca(t.diferenca, t.unidade)} (enviado ${formatarQuantidade(t.enviada, t.unidade)})`)
                .join(" · ")}
            </p>
          </>
        )}
      </div>
    </section>
  )
}
