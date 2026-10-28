/*
 * Resumo do período no topo da consulta (pedido do Ualker): total vendido e
 * total de perda, com a unidade. UN e KG não se somam, então cada total
 * mostra uma linha por unidade ("171 un" e "3,75 kg").
 * Skill Frescor: rótulo curto 14px --muted em cima, número grande em Sora
 * --secondary (utilitário text-heading), algarismos tabulares.
 */
import { ShoppingBasket, Trash2 } from "lucide-react"
import type { TotalPorUnidade } from "@/lib/api/tipos"
import { formatarQuantidade } from "@/lib/formato"

function Numero({
  rotulo,
  Icone,
  totais,
  carregando,
  vazio,
}: {
  rotulo: string
  Icone: typeof ShoppingBasket
  totais: TotalPorUnidade[] | undefined
  carregando: boolean
  vazio: string
}) {
  return (
    <div className="painel-kpi p-5">
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icone className="size-5" aria-hidden="true" />
        {rotulo}
      </p>
      {carregando ? (
        <p className="mt-2 text-muted-foreground">Calculando…</p>
      ) : !totais || totais.length === 0 ? (
        <p className="mt-2 text-muted-foreground">{vazio}</p>
      ) : (
        <ul className="mt-1">
          {totais.map((t) => (
            <li key={t.unidade} className="numero-destaque text-[clamp(30px,2.6vw,40px)] leading-tight whitespace-nowrap">
              {formatarQuantidade(t.quantidade, t.unidade)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ResumoPeriodo({
  vendas,
  perdas,
  carregandoVendas,
  carregandoPerdas,
}: {
  vendas: TotalPorUnidade[] | undefined
  perdas: TotalPorUnidade[] | undefined
  carregandoVendas: boolean
  carregandoPerdas: boolean
}) {
  return (
    <section aria-label="Resumo do período" className="grid gap-4 sm:grid-cols-2">
      <Numero
        rotulo="Vendido no período"
        Icone={ShoppingBasket}
        totais={vendas}
        carregando={carregandoVendas}
        vazio="Nenhuma venda no período."
      />
      <Numero
        rotulo="Perda no período"
        Icone={Trash2}
        totais={perdas}
        carregando={carregandoPerdas}
        vazio="Nenhuma perda no período."
      />
    </section>
  )
}
