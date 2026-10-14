/*
 * Tabela de previsões do dia (F9). Cada linha mostra o número, a venda do
 * mesmo dia da semana passada e, sempre visível, uma frase curta de como o
 * número foi calculado ("Mediana das últimas 6 terças × tendência +10%"),
 * com as etiquetas "Evento", "Pouco histórico" e "Sem previsão". O botão
 * "Ver a conta" abre a conta passo a passo logo abaixo da linha.
 *
 * Produto sem previsão continua na tabela (nunca some), com "Sem previsão"
 * no lugar do número e o motivo na explicação.
 */
import { Fragment, useId, useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ItemPrevisao } from "@/lib/api/tipos"
import { formatarData, formatarPrevisao, formatarQuantidade } from "@/lib/formato"
import { Etiqueta } from "./Etiqueta"
import { explicarPrevisao } from "./explicacao"

const horario = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" })

function chave(item: ItemPrevisao): string {
  return `${item.loja.id}-${item.produto.id}`
}

export function TabelaPrevisao({ itens, mostrarLoja }: { itens: ItemPrevisao[]; mostrarLoja: boolean }) {
  const [abertas, setAbertas] = useState<Set<string>>(new Set())
  const id = useId()
  const colunas = mostrarLoja ? 5 : 4

  function alternar(k: string) {
    setAbertas((atual) => {
      const nova = new Set(atual)
      if (nova.has(k)) nova.delete(k)
      else nova.add(k)
      return nova
    })
  }

  return (
    <Table aria-label="Previsão por loja e produto">
      <TableHeader>
        <TableRow>
          {mostrarLoja && <TableHead>Loja</TableHead>}
          <TableHead>Produto</TableHead>
          <TableHead className="text-right">Previsão</TableHead>
          <TableHead className="text-right">Semana passada</TableHead>
          <TableHead>Como foi calculado</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {itens.map((item) => {
          const k = chave(item)
          const explicacao = explicarPrevisao(item)
          const aberta = abertas.has(k)
          const idDetalhe = `${id}-${k}`
          return (
            <Fragment key={k}>
              <TableRow>
                {mostrarLoja && (
                  <TableCell className="whitespace-nowrap">
                    {item.loja.codigo ? `${item.loja.codigo} · ` : ""}
                    {item.loja.nome}
                  </TableCell>
                )}
                <TableCell>
                  {item.produto.codigo ? `${item.produto.codigo} · ` : ""}
                  {item.produto.nome}
                </TableCell>
                <TableCell className="text-right font-semibold whitespace-nowrap numero">
                  {item.previsao === null ? (
                    <Etiqueta tipo="sem_previsao">Sem previsão</Etiqueta>
                  ) : (
                    formatarPrevisao(item.previsao, item.unidade)
                  )}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap text-muted-foreground numero">
                  {item.venda_semana_passada === null ? "sem dado" : formatarQuantidade(item.venda_semana_passada, item.unidade)}
                </TableCell>
                <TableCell className="py-2">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span>{explicacao.resumo}</span>
                    {item.eventos.map((e) => (
                      <Etiqueta key={e.id} tipo="evento">
                        Evento: {e.nome}
                      </Etiqueta>
                    ))}
                    {item.pouco_historico && item.previsao !== null && (
                      <Etiqueta tipo="pouco_historico">Pouco histórico</Etiqueta>
                    )}
                    <Button
                      variant="link"
                      size="sm"
                      className="px-0"
                      aria-expanded={aberta}
                      aria-controls={aberta ? idDetalhe : undefined}
                      // Nome completo para leitor de tela: há um botão destes por linha.
                      aria-label={`${aberta ? "Esconder" : "Ver"} a conta de ${item.produto.nome}${mostrarLoja ? ` na loja ${item.loja.codigo ?? item.loja.nome}` : ""}`}
                      onClick={() => alternar(k)}
                    >
                      {aberta ? "Esconder a conta" : "Ver a conta"}
                      {aberta ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
              {aberta && (
                <TableRow id={idDetalhe} className="bg-surface hover:bg-surface">
                  <TableCell colSpan={colunas} className="py-3 whitespace-normal">
                    <ol className="flex list-decimal flex-col gap-1 pl-6">
                      {explicacao.passos.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ol>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Calculada em {horario.format(new Date(item.gerado_em))}, com vendas até {formatarData(item.data_referencia)} · método {item.versao_metodo}
                    </p>
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
