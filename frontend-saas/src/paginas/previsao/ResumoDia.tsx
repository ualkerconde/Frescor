/*
 * Resumo do dia previsto, no topo da tela (pedido do Ualker): o total
 * previsto por unidade (UN e KG não se somam) ao lado do vendido no mesmo
 * dia da semana passada, e os produtos que pedem atenção (sem previsão ou
 * com pouco histórico) pelo nome, para nenhum deles passar despercebido.
 *
 * Skill Frescor: rótulo 14px --muted, número grande em Sora --secondary,
 * variação embaixo com seta. A variação é neutra (cinza): prever mais ou
 * menos que a semana passada não é bom nem ruim por si só.
 */
import { ArrowDown, ArrowRight, ArrowUp, Package, TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { ItemPrevisao, TotalPrevisto, Unidade } from "@/lib/api/tipos"
import { contar, diaDaSemana, formatarData, formatarPrevisao, formatarQuantidade, formatarVariacao, somarDias } from "@/lib/formato"

const MAXIMO_NOMES = 5

function rotuloItem(item: ItemPrevisao, mostrarLoja: boolean): string {
  const produto = item.produto.codigo ? `${item.produto.codigo} · ${item.produto.nome}` : item.produto.nome
  return mostrarLoja ? `${produto} (loja ${item.loja.codigo ?? item.loja.nome})` : produto
}

function ListaNomes({ itens, mostrarLoja }: { itens: ItemPrevisao[]; mostrarLoja: boolean }) {
  const visiveis = itens.slice(0, MAXIMO_NOMES)
  const resto = itens.length - visiveis.length
  return (
    <>
      {visiveis.map((i) => rotuloItem(i, mostrarLoja)).join("; ")}
      {resto > 0 && ` e mais ${contar(resto, "produto", "produtos")}`}
    </>
  )
}

function Variacao({ previsto, vendido, unidade }: { previsto: number; vendido: number; unidade: Unidade }) {
  if (vendido <= 0) return null
  const fator = previsto / vendido
  const texto = formatarVariacao(fator)
  const Seta = texto === "0%" ? ArrowRight : fator > 1 ? ArrowUp : ArrowDown
  return (
    <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground numero">
      <Seta className="size-4" aria-hidden="true" />
      {texto === "0%" ? "igual à" : `${texto} vs.`} semana passada ({formatarQuantidade(vendido, unidade)})
    </p>
  )
}

export function ResumoDia({
  data,
  itens,
  totais,
  mostrarLoja,
}: {
  data: string
  itens: ItemPrevisao[]
  totais: TotalPrevisto[]
  mostrarLoja: boolean
}) {
  const semPrevisao = itens.filter((i) => i.previsao === null)
  const poucoHistorico = itens.filter((i) => i.pouco_historico && i.previsao !== null)
  const calculadas = itens.length - semPrevisao.length
  const semanaPassada = somarDias(data, -7)

  return (
    <section aria-label="Resumo do dia previsto" className="flex flex-col gap-4">
      <h2 className="text-[22px]">
        Previsão para {diaDaSemana(data)}, {formatarData(data)}
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {totais.map((t) => {
          const semNumero = semPrevisao.filter((i) => i.unidade === t.unidade).length
          return (
            <div key={t.unidade} className="rounded-lg border border-line bg-card p-4">
              <p className="text-sm text-muted-foreground">
                Previsto em {t.unidade === "KG" ? "quilos" : "unidades"}
              </p>
              <p className="font-heading text-[40px] leading-tight font-semibold text-heading numero">
                {formatarPrevisao(t.previsto, t.unidade)}
              </p>
              <Variacao previsto={Number(t.previsto)} vendido={Number(t.vendido_semana_passada)} unidade={t.unidade} />
              {Number(t.vendido_semana_passada) <= 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Sem venda registrada em {diaDaSemana(semanaPassada)}, {formatarData(semanaPassada)}.
                </p>
              )}
              {semNumero > 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Não inclui {contar(semNumero, "produto sem previsão", "produtos sem previsão")}.
                </p>
              )}
            </div>
          )
        })}
        <div className="rounded-lg border border-line bg-card p-4">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Package className="size-5" aria-hidden="true" />
            Produtos previstos (por loja)
          </p>
          <p className="font-heading text-[40px] leading-tight font-semibold text-heading numero">
            {itens.length}
          </p>
          <p className="mt-1 text-sm text-muted-foreground numero">
            {contar(calculadas, "com previsão", "com previsão")} · {contar(semPrevisao.length, "sem previsão", "sem previsão")}
          </p>
        </div>
      </div>

      {(semPrevisao.length > 0 || poucoHistorico.length > 0) && (
        // role="note": é informação permanente da tela, não um aviso urgente para o leitor de tela.
        <Alert variant="aviso" role="note">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Confira estes produtos antes de usar os números</AlertTitle>
          <AlertDescription className="text-base">
            <ul className="flex flex-col gap-1">
              {semPrevisao.length > 0 && (
                <li>
                  <strong>Sem previsão</strong> (defina a quantidade pela sua experiência):{" "}
                  <ListaNomes itens={semPrevisao} mostrarLoja={mostrarLoja} />.
                </li>
              )}
              {poucoHistorico.length > 0 && (
                <li>
                  <strong>Pouco histórico</strong> (o número usa produtos parecidos e pode errar mais):{" "}
                  <ListaNomes itens={poucoHistorico} mostrarLoja={mostrarLoja} />.
                </li>
              )}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </section>
  )
}
