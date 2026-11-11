/*
 * Itens do menu do SaaS, agrupados por seção (padrão de 11/11/2026, a partir
 * da referência que o sócio do Ualker mandou): a barra lateral, a barra do
 * topo ("PLANEJAMENTO / Produção") e a busca de telas (Ctrl K) leem daqui,
 * para os três nunca divergirem.
 */
import {
  ChartColumn,
  ChartLine,
  ClipboardList,
  Factory,
  LayoutDashboard,
  PlugZap,
  Search,
  Trash2,
  Truck,
  Upload,
} from "lucide-react"

export interface ItemMenu {
  para: string
  rotulo: string
  /** Frase curta mostrada na busca de telas. */
  descricao: string
  Icone: typeof Upload
  /**
   * Fora da barra lateral (só na busca de telas e na barra do topo). É o caso
   * da carga de histórico por CSV, que deixou de ser rotina (D107) e é aberta
   * pela tela de integração.
   */
  foraDoMenu?: boolean
}

export interface GrupoMenu {
  grupo: string
  itens: ItemMenu[]
}

export const GRUPOS_MENU: GrupoMenu[] = [
  {
    grupo: "Visão",
    itens: [
      {
        para: "/inicio",
        rotulo: "Visão geral",
        descricao: "Produção de amanhã, entregas de hoje e a última semana",
        Icone: LayoutDashboard,
      },
      {
        para: "/acompanhamento",
        rotulo: "Acompanhamento",
        descricao: "Previsto × pedido × produzido × vendido, com o erro da previsão",
        Icone: ChartColumn,
      },
    ],
  },
  {
    grupo: "Dados",
    itens: [
      { para: "/consultar", rotulo: "Consultar", descricao: "Ver vendas e perdas por período", Icone: Search },
    ],
  },
  {
    grupo: "Planejamento",
    itens: [
      { para: "/previsao", rotulo: "Previsão", descricao: "Quanto cada loja deve vender", Icone: ChartLine },
      { para: "/producao", rotulo: "Produção", descricao: "Gerar, ajustar e aprovar a ordem", Icone: Factory },
    ],
  },
  {
    grupo: "Operação",
    itens: [
      {
        para: "/distribuicao",
        rotulo: "Distribuição",
        descricao: "Produção real, romaneio, saída e recebimento",
        Icone: Truck,
      },
      {
        para: "/perdas",
        rotulo: "Perdas",
        descricao: "Ver, lançar e corrigir as perdas das lojas",
        Icone: Trash2,
      },
    ],
  },
  {
    grupo: "Configuração",
    itens: [
      {
        para: "/cadastros",
        rotulo: "Cadastros",
        descricao: "Produtos, setores, eventos e a central",
        Icone: ClipboardList,
      },
      {
        para: "/integracao",
        rotulo: "Integração de vendas",
        descricao: "Vendas vindas do sistema do cliente: última busca e pendências",
        Icone: PlugZap,
      },
      {
        para: "/importar",
        rotulo: "Carga de histórico",
        descricao: "Enviar um CSV de vendas (histórico ou contingência)",
        Icone: Upload,
        foraDoMenu: true,
      },
    ],
  },
]

/** Grupo e item da rota atual ("/producao?data=..." -> Planejamento / Produção). */
export function localizar(pathname: string): { grupo: string; item: ItemMenu } | null {
  for (const { grupo, itens } of GRUPOS_MENU) {
    const item = itens.find((i) => pathname === i.para || pathname.startsWith(`${i.para}/`))
    if (item) return { grupo, item }
  }
  return null
}
