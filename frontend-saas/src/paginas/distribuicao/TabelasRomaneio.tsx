/*
 * Tabelas do romaneio (E10):
 * - TabelaProducao: por produto, planejado, produzido e o que vai para as
 *   lojas; destaca quando a soma das lojas passa do produzido (D71: o
 *   romaneio não aprova assim).
 * - TabelaRascunho: loja + produto, sugerido (rateio da D70) e final, com
 *   "Ajustar" (só no rascunho).
 * - TabelaAcompanhamento: uma linha por loja, na ordem do código, com a
 *   situação (aguardando saída / a caminho / recebido / recebido com
 *   diferença / sem confirmação), saída e recebimento; "Ver itens" abre o
 *   enviado e o recebido de cada produto.
 */
import { Fragment, useId, useState } from "react"
import { ChevronDown, ChevronUp, PencilLine, TriangleAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { EntregaRomaneio, ItemProducao, ProducaoRomaneio } from "@/lib/api/tipos"
import { formatarQuantidade } from "@/lib/formato"
import type { AlvoAjuste } from "../producao/Dialogos"
import { EtiquetaSituacao } from "./Marcadores"
import { MOTIVOS, nomeCom, quando } from "./situacao"

const PILL_AVISO =
  "inline-flex items-center gap-1 rounded-full bg-warning-bg px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap text-warning"

/** Produção registrada da ordem ainda sem romaneio (D69). */
export function TabelaProducaoOrdem({ itens }: { itens: ItemProducao[] }) {
  return (
    <Table aria-label="Produção da ordem">
      <TableHeader>
        <TableRow>
          <TableHead>Produto</TableHead>
          <TableHead className="text-right">Planejado</TableHead>
          <TableHead className="text-right">Produzido</TableHead>
          <TableHead>Para as lojas</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {itens.map((i) => {
          const produzido = i.produzido === null ? null : Number(i.produzido)
          const planejado = Number(i.planejado)
          return (
            <TableRow key={i.item_id}>
              <TableCell>{nomeCom(i.produto)}</TableCell>
              <TableCell className="text-right numero">{formatarQuantidade(i.planejado, i.unidade)}</TableCell>
              <TableCell className="text-right font-semibold numero">
                {produzido === null ? (
                  <span className="text-muted-foreground">a registrar</span>
                ) : (
                  formatarQuantidade(produzido, i.unidade)
                )}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {produzido === null
                  ? "—"
                  : produzido < planejado
                    ? "Faltou: o romaneio divide entre as lojas"
                    : produzido > planejado
                      ? "Sobrou: a sobra fica na central"
                      : "Vai como na ordem"}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

export function TabelaProducao({ producao }: { producao: ProducaoRomaneio[] }) {
  return (
    <Table aria-label="Produção e envio">
      <TableHeader>
        <TableRow>
          <TableHead>Produto</TableHead>
          <TableHead className="text-right">Planejado</TableHead>
          <TableHead className="text-right">Produzido</TableHead>
          <TableHead className="text-right">Para as lojas</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {producao.map((p) => {
          const excesso = Number(p.total_final) - Number(p.produzido ?? 0)
          return (
            <TableRow key={p.produto.id}>
              <TableCell>{nomeCom(p.produto)}</TableCell>
              <TableCell className="text-right numero">{formatarQuantidade(p.planejado, p.unidade)}</TableCell>
              <TableCell className="text-right numero">
                {p.produzido === null ? "—" : formatarQuantidade(p.produzido, p.unidade)}
              </TableCell>
              <TableCell className="text-right font-semibold numero">
                {formatarQuantidade(p.total_final, p.unidade)}
                {excesso > 0 && (
                  <span className={`${PILL_AVISO} ml-2`}>
                    <TriangleAlert className="size-4" aria-hidden="true" />
                    {formatarQuantidade(excesso, p.unidade)} além do produzido
                  </span>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

export function TabelaRascunho({
  entregas,
  aoAjustar,
}: {
  entregas: EntregaRomaneio[]
  aoAjustar: (alvo: AlvoAjuste) => void
}) {
  return (
    <Table aria-label="Entregas por loja">
      <TableHeader>
        <TableRow>
          <TableHead>Loja</TableHead>
          <TableHead>Produto</TableHead>
          <TableHead className="text-right">Sugerido</TableHead>
          <TableHead className="text-right">Vai para a loja</TableHead>
          <TableHead className="sr-only">Ajustar</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entregas.flatMap((e) =>
          e.itens.map((i, n) => (
            <TableRow key={i.id}>
              <TableCell className="whitespace-nowrap">{n === 0 ? nomeCom(e.loja) : ""}</TableCell>
              <TableCell>{nomeCom(i.produto)}</TableCell>
              <TableCell className="text-right text-muted-foreground numero">
                {formatarQuantidade(i.quantidade_sugerida, i.unidade)}
              </TableCell>
              <TableCell className="text-right font-semibold whitespace-nowrap numero">
                {formatarQuantidade(i.quantidade_final, i.unidade)}
                {i.editado_em && (
                  <span className="block text-sm font-normal text-muted-foreground">
                    ajustado{i.motivo_edicao ? `: ${i.motivo_edicao}` : ""}
                  </span>
                )}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="secondary"
                  size="sm"
                  aria-label={`Ajustar ${i.produto.nome} na loja ${e.loja.codigo ?? e.loja.nome}`}
                  onClick={() =>
                    aoAjustar({
                      linhaId: i.id,
                      produto: i.produto.nome,
                      loja: nomeCom(e.loja),
                      unidade: i.unidade,
                      sugerida: i.quantidade_sugerida,
                      final: i.quantidade_final,
                      motivo: i.motivo_edicao,
                    })
                  }
                >
                  <PencilLine aria-hidden="true" />
                  Ajustar
                </Button>
              </TableCell>
            </TableRow>
          )),
        )}
      </TableBody>
    </Table>
  )
}

export function TabelaAcompanhamento({ entregas }: { entregas: EntregaRomaneio[] }) {
  const id = useId()
  const [abertas, setAbertas] = useState<Set<number>>(new Set())

  function alternar(entregaId: number) {
    setAbertas((atual) => {
      const nova = new Set(atual)
      if (nova.has(entregaId)) nova.delete(entregaId)
      else nova.add(entregaId)
      return nova
    })
  }

  return (
    <Table aria-label="Acompanhamento por loja">
      <TableHeader>
        <TableRow>
          <TableHead>Loja</TableHead>
          <TableHead>Situação</TableHead>
          <TableHead>Saída</TableHead>
          <TableHead>Recebimento</TableHead>
          <TableHead className="sr-only">Itens</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entregas.map((e) => {
          const aberta = abertas.has(e.id)
          const idItens = `${id}-${e.id}`
          return (
            <Fragment key={e.id}>
              <TableRow>
                <TableCell className="whitespace-nowrap">{nomeCom(e.loja)}</TableCell>
                <TableCell>
                  <EtiquetaSituacao situacao={e.situacao} />
                </TableCell>
                <TableCell className="numero">{e.expedido_em ? quando(e.expedido_em) : "—"}</TableCell>
                <TableCell className="numero">{e.recebido_em ? quando(e.recebido_em) : "—"}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="link"
                    size="sm"
                    className="px-0"
                    aria-expanded={aberta}
                    aria-controls={aberta ? idItens : undefined}
                    aria-label={`${aberta ? "Esconder" : "Ver"} os itens da loja ${e.loja.codigo ?? e.loja.nome}`}
                    onClick={() => alternar(e.id)}
                  >
                    {aberta ? "Esconder itens" : "Ver itens"}
                    {aberta ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
                  </Button>
                </TableCell>
              </TableRow>
              {aberta && (
                <TableRow id={idItens} className="bg-surface hover:bg-surface">
                  <TableCell colSpan={5} className="py-3">
                    <ul className="flex flex-col gap-1">
                      {e.itens.map((i) => (
                        <li key={i.id} className="flex flex-wrap justify-between gap-x-4">
                          <span>{nomeCom(i.produto)}</span>
                          <span className="numero">
                            enviado {formatarQuantidade(i.quantidade_final, i.unidade)}
                            {i.quantidade_recebida !== null &&
                              ` · recebido ${formatarQuantidade(i.quantidade_recebida, i.unidade)}`}
                            {i.motivo_divergencia && ` · ${MOTIVOS[i.motivo_divergencia]}`}
                            {i.observacao_divergencia && `: ${i.observacao_divergencia}`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
