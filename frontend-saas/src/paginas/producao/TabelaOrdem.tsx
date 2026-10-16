/*
 * Produtos da ordem (N9). Uma linha por produto com o total sugerido e o
 * final (soma das lojas, D54) e os avisos resumidos; "Ver lojas" abre as
 * lojas daquele produto: sugerido, final (com "ajustado" quando o gestor
 * mudou), perda das 4 semanas (4 faixas, D66), avisos, "Ajustar" (só no
 * rascunho) e "Ver a conta" (a conta passo a passo, conta.ts).
 *
 * Ordem aprovada: só leitura (sem "Ajustar").
 */
import { Fragment, useId, useState } from "react"
import { ChevronDown, ChevronUp, PencilLine } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ItemOrdem, LinhaOrdem } from "@/lib/api/tipos"
import { contar, formatarQuantidade } from "@/lib/formato"
import { passosDaConta } from "./conta"
import type { AlvoAjuste } from "./Dialogos"
import { EtiquetaAviso, IndicadorPerda } from "./Marcadores"

function nomeProduto(item: ItemOrdem): string {
  return item.produto.codigo ? `${item.produto.codigo} · ${item.produto.nome}` : item.produto.nome
}

function nomeLoja(linha: LinhaOrdem): string {
  return linha.loja.codigo ? `${linha.loja.codigo} · ${linha.loja.nome}` : linha.loja.nome
}

function avisosDoProduto(item: ItemOrdem): string[] {
  return [...new Set(item.linhas.flatMap((l) => l.avisos))]
}

function Quantidade({ valor, item }: { valor: string | null; item: ItemOrdem }) {
  return valor === null ? (
    <span className="font-semibold text-error">informar</span>
  ) : (
    <>{formatarQuantidade(valor, item.unidade)}</>
  )
}

function LojasDoProduto({
  item,
  somenteLeitura,
  aoAjustar,
}: {
  item: ItemOrdem
  somenteLeitura: boolean
  aoAjustar: (alvo: AlvoAjuste) => void
}) {
  const [contas, setContas] = useState<Set<number>>(new Set())
  const id = useId()
  const colunas = somenteLeitura ? 5 : 6

  function alternar(linhaId: number) {
    setContas((atual) => {
      const nova = new Set(atual)
      if (nova.has(linhaId)) nova.delete(linhaId)
      else nova.add(linhaId)
      return nova
    })
  }

  return (
    <Table aria-label={`Lojas de ${item.produto.nome}`}>
      <TableHeader>
        <TableRow>
          <TableHead>Loja</TableHead>
          <TableHead className="text-right">Sugerido</TableHead>
          <TableHead className="text-right">Final</TableHead>
          <TableHead>Perda (4 semanas)</TableHead>
          <TableHead>Avisos e conta</TableHead>
          {!somenteLeitura && <TableHead className="sr-only">Ajustar</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {item.linhas.map((linha) => {
          const aberta = contas.has(linha.id)
          const idConta = `${id}-${linha.id}`
          return (
            <Fragment key={linha.id}>
              <TableRow>
                <TableCell className="whitespace-nowrap">{nomeLoja(linha)}</TableCell>
                <TableCell className="text-right text-muted-foreground numero">
                  {linha.quantidade_sugerida === null ? "—" : formatarQuantidade(linha.quantidade_sugerida, item.unidade)}
                </TableCell>
                <TableCell className="text-right font-semibold whitespace-nowrap numero">
                  <Quantidade valor={linha.quantidade_final} item={item} />
                  {linha.editada && (
                    <span className="block text-sm font-normal text-muted-foreground" title={linha.motivo_edicao ?? undefined}>
                      ajustado{linha.motivo_edicao ? `: ${linha.motivo_edicao}` : ""}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <IndicadorPerda taxa={linha.componentes.taxa_perda} />
                </TableCell>
                <TableCell className="py-2">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {linha.avisos.map((a) => (
                      <EtiquetaAviso key={a} codigo={a} />
                    ))}
                    <Button
                      variant="link"
                      size="sm"
                      className="px-0"
                      aria-expanded={aberta}
                      aria-controls={aberta ? idConta : undefined}
                      aria-label={`${aberta ? "Esconder" : "Ver"} a conta de ${item.produto.nome} na loja ${linha.loja.codigo ?? linha.loja.nome}`}
                      onClick={() => alternar(linha.id)}
                    >
                      {aberta ? "Esconder a conta" : "Ver a conta"}
                      {aberta ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
                    </Button>
                  </div>
                </TableCell>
                {!somenteLeitura && (
                  <TableCell className="text-right">
                    <Button
                      variant="secondary"
                      size="sm"
                      aria-label={`Ajustar ${item.produto.nome} na loja ${linha.loja.codigo ?? linha.loja.nome}`}
                      onClick={() =>
                        aoAjustar({
                          linhaId: linha.id,
                          produto: item.produto.nome,
                          loja: nomeLoja(linha),
                          unidade: item.unidade,
                          sugerida: linha.quantidade_sugerida,
                          final: linha.quantidade_final,
                          motivo: linha.motivo_edicao,
                        })
                      }
                    >
                      <PencilLine aria-hidden="true" />
                      Ajustar
                    </Button>
                  </TableCell>
                )}
              </TableRow>
              {aberta && (
                <TableRow id={idConta} className="bg-surface hover:bg-surface">
                  <TableCell colSpan={colunas} className="py-3 whitespace-normal">
                    <ol className="flex list-decimal flex-col gap-1 pl-6">
                      {passosDaConta(linha.componentes, item.unidade).map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ol>
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

export function TabelaOrdem({
  titulo,
  descricao,
  itens,
  somenteLeitura,
  aoAjustar,
}: {
  titulo: string
  descricao: string
  itens: ItemOrdem[]
  somenteLeitura: boolean
  aoAjustar: (alvo: AlvoAjuste) => void
}) {
  const [abertos, setAbertos] = useState<Set<number>>(new Set())
  const id = useId()

  if (itens.length === 0) return null

  function alternar(itemId: number) {
    setAbertos((atual) => {
      const novo = new Set(atual)
      if (novo.has(itemId)) novo.delete(itemId)
      else novo.add(itemId)
      return novo
    })
  }

  return (
    <section className="flex flex-col gap-3" aria-labelledby={`${id}-titulo`}>
      <div>
        <h2 id={`${id}-titulo`} className="text-[22px]">
          {titulo}
        </h2>
        <p className="mt-1 text-muted-foreground">{descricao}</p>
      </div>
      <Table aria-label={titulo}>
        <TableHeader>
          <TableRow>
            <TableHead>Produto</TableHead>
            <TableHead className="text-right">Sugerido</TableHead>
            <TableHead className="text-right">Final</TableHead>
            <TableHead>Atenção</TableHead>
            <TableHead className="sr-only">Lojas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {itens.map((item) => {
            const aberto = abertos.has(item.id)
            const idLojas = `${id}-${item.id}`
            const semQuantidade = item.linhas.filter((l) => l.quantidade_final === null).length
            return (
              <Fragment key={item.id}>
                <TableRow>
                  <TableCell className="font-semibold">{nomeProduto(item)}</TableCell>
                  <TableCell className="text-right text-muted-foreground numero">
                    {formatarQuantidade(item.total_sugerido, item.unidade)}
                  </TableCell>
                  <TableCell className="text-right font-semibold whitespace-nowrap numero">
                    {formatarQuantidade(item.total_final, item.unidade)}
                    {semQuantidade > 0 && (
                      <span className="block text-sm font-normal text-error">
                        faltam {contar(semQuantidade, "loja", "lojas")}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="py-2">
                    <div className="flex flex-wrap gap-1">
                      {avisosDoProduto(item).map((a) => (
                        <EtiquetaAviso key={a} codigo={a} />
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="link"
                      size="sm"
                      aria-expanded={aberto}
                      aria-controls={aberto ? idLojas : undefined}
                      aria-label={`${aberto ? "Esconder" : "Ver"} as lojas de ${item.produto.nome}`}
                      onClick={() => alternar(item.id)}
                    >
                      {aberto ? "Esconder lojas" : `Ver ${contar(item.linhas.length, "loja", "lojas")}`}
                      {aberto ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
                    </Button>
                  </TableCell>
                </TableRow>
                {aberto && (
                  <TableRow id={idLojas} className="hover:bg-transparent">
                    <TableCell colSpan={5} className="bg-card p-0 pl-6 whitespace-normal">
                      <LojasDoProduto item={item} somenteLeitura={somenteLeitura} aoAjustar={aoAjustar} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
    </section>
  )
}
