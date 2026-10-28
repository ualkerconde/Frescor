/*
 * Resultado da importação (passo W6), fácil de entender (pedido do Ualker):
 * 1. um resumo grande no topo: "1.232 linhas importadas" (verde) ou
 *    "Nada foi gravado: 3 erros" (vermelho), com o que fazer;
 * 2. depois, a lista de erros (linha + o que corrigir);
 * 3. depois, os avisos (não impedem a importação).
 * Skill Frescor: cor sempre com ícone e texto; números pt-BR; tabela com
 * cabeçalho em maiúsculas e zebra; nada de código técnico.
 */
import { CircleCheck, CircleX, TriangleAlert } from "lucide-react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { MensagemLinha, RelatorioImportacao } from "@/lib/api/tipos"
import { contar } from "@/lib/formato"

function rotuloLinha(linha: number): string {
  return linha === 0 ? "Arquivo" : `Linha ${linha}`
}

function ListaDeLinhas({ itens, cabecalho }: { itens: MensagemLinha[]; cabecalho: string }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-32">Linha</TableHead>
          <TableHead>{cabecalho}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {itens.map((item, i) => (
          <TableRow key={`${item.linha}-${i}`}>
            <TableCell className="font-semibold whitespace-nowrap numero">{rotuloLinha(item.linha)}</TableCell>
            <TableCell>{item.mensagem}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function ResultadoImportacao({ relatorio }: { relatorio: RelatorioImportacao }) {
  const totalErros = relatorio.erros.length + relatorio.erros_omitidos
  const totalAvisos = relatorio.avisos.length + relatorio.avisos_omitidos
  const gravadas = relatorio.inseridas + relatorio.substituidas

  return (
    <section aria-label="Resultado da importação" className="flex flex-col gap-6">
      {relatorio.sucesso ? (
        <div className="rounded-2xl bg-success-bg p-6 ring-1 ring-success/15 ring-inset">
          <p className="flex items-center gap-2 font-semibold text-success">
            <CircleCheck className="size-5" aria-hidden="true" />
            Importação concluída
          </p>
          <h2 className="mt-2 text-[36px] leading-tight numero">
            {contar(gravadas, "linha importada", "linhas importadas")}
          </h2>
          <p className="mt-2 text-foreground numero">
            {relatorio.substituidas === 0
              ? relatorio.inseridas === 1
                ? "É uma linha nova."
                : "Todas são novas."
              : `${contar(relatorio.inseridas, "nova", "novas")} · ${contar(relatorio.substituidas, "substituída", "substituídas")} (já existiam e foram atualizadas com o arquivo)`}
          </p>
        </div>
      ) : (
        <div className="rounded-2xl bg-error-bg p-6 ring-1 ring-error/15 ring-inset">
          <p className="flex items-center gap-2 font-semibold text-error">
            <CircleX className="size-5" aria-hidden="true" />
            Arquivo com erros
          </p>
          <h2 className="mt-2 text-[36px] leading-tight numero">
            Nada foi gravado: {contar(totalErros, "erro", "erros")}
          </h2>
          <p className="mt-2 text-foreground">Corrija {totalErros === 1 ? "a linha abaixo" : "as linhas abaixo"} no arquivo e envie de novo.</p>
        </div>
      )}

      {relatorio.erros.length > 0 && (
        <div>
          <h3 className="flex items-center gap-2 text-[22px]">
            <CircleX className="size-5 text-error" aria-hidden="true" />
            {contar(totalErros, "erro", "erros")}
          </h3>
          <div className="mt-3">
            <ListaDeLinhas itens={relatorio.erros} cabecalho="O que corrigir" />
          </div>
          {relatorio.erros_omitidos > 0 && (
            <p className="mt-3 text-muted-foreground">
              E mais {contar(relatorio.erros_omitidos, "erro não listado", "erros não listados")}. Corrija os de cima e
              envie de novo para ver os demais.
            </p>
          )}
        </div>
      )}

      {relatorio.avisos.length > 0 && (
        <div>
          <h3 className="flex items-center gap-2 text-[22px]">
            <TriangleAlert className="size-5 text-warning" aria-hidden="true" />
            {contar(totalAvisos, "aviso", "avisos")}
          </h3>
          <p className="mt-1 text-muted-foreground">
            {relatorio.sucesso
              ? "A importação foi feita, mas vale conferir:"
              : "Avisos não impedem a importação, mas vale conferir:"}
          </p>
          <div className="mt-3">
            <ListaDeLinhas itens={relatorio.avisos} cabecalho="O que conferir" />
          </div>
          {relatorio.avisos_omitidos > 0 && (
            <p className="mt-3 text-muted-foreground">
              E mais {contar(relatorio.avisos_omitidos, "aviso não listado", "avisos não listados")}.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
