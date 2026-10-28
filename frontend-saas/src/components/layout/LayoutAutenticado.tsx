/*
 * Estrutura das telas autenticadas do SaaS (passo W5, redesenhado em
 * 28/10/2026), pela skill Frescor:
 *
 * - Barra lateral em --secondary, lisa: logo, navegação em dois grupos
 *   (Dados: Importar e Consultar; Planejamento: Previsão e Produção) e, no
 *   rodapé, quem está logado (gestor · central · negócio, de GET /web/me)
 *   e "Sair". Abaixo de 1024px ela vira uma faixa no topo com a navegação
 *   rolando de lado. É o <header> da página (papel "banner").
 * - Faixa branca no topo do conteúdo com onde a pessoa está (grupo / tela)
 *   e a data de hoje.
 *
 * "Sair" é um botão discreto (ghost): a ação principal de cada tela fica
 * com o conteúdo, não com a navegação (skill: uma ação principal por tela).
 * Ícones sempre com texto. Link "Pular para o conteúdo" para teclado.
 */
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { ChartLine, ChevronRight, Factory, LogOut, Search, Upload } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router"
import { Logo } from "@/components/marca/Logo"
import { Button } from "@/components/ui/button"
import { apiJson } from "@/lib/api/cliente"
import type { Me } from "@/lib/api/tipos"
import { useSessao } from "@/lib/sessao/contexto"

const GRUPOS_MENU = [
  {
    grupo: "Dados",
    itens: [
      { para: "/importar", rotulo: "Importar", Icone: Upload },
      { para: "/consultar", rotulo: "Consultar", Icone: Search },
    ],
  },
  {
    grupo: "Planejamento",
    itens: [
      { para: "/previsao", rotulo: "Previsão", Icone: ChartLine },
      { para: "/producao", rotulo: "Produção", Icone: Factory },
    ],
  },
]

const hoje = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long" })

/** Foco visível sobre a barra escura: anel branco no lugar do --primary (que some no escuro). */
const FOCO_ESCURO = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"

/** Iniciais para o avatar: "Gestor Central Teste" -> "GC". */
function iniciais(nome: string): string {
  return nome
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("")
}

function QuemEsta() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => apiJson<Me>("/web/me"),
  })

  if (isPending) return <span className="text-sm text-ink-muted">Carregando…</span>
  if (isError || !data) return <span className="text-sm text-ink-muted">Não foi possível carregar seus dados.</span>

  return (
    <span className="flex min-w-0 items-center gap-3">
      <span
        aria-hidden="true"
        className="grid size-9 shrink-0 place-items-center rounded-full bg-white/10 text-sm font-semibold text-white"
      >
        {iniciais(data.usuario.nome)}
      </span>
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate text-sm font-semibold text-white">{data.usuario.nome}</span>
        <span className="truncate text-sm text-ink-muted">
          {data.central.nome} · {data.negocio.nome}
        </span>
      </span>
    </span>
  )
}

function Navegacao() {
  return (
    <nav aria-label="Principal" className="-mx-1 overflow-x-auto px-1 lg:mx-0 lg:overflow-visible lg:px-0">
      <div className="flex gap-1 lg:flex-col lg:gap-5">
        {GRUPOS_MENU.map(({ grupo, itens }) => (
          <div key={grupo} className="flex gap-1 lg:flex-col lg:gap-0.5">
            <p className="hidden px-3 pb-1.5 text-xs font-semibold text-ink-muted lg:block">{grupo}</p>
            {itens.map(({ para, rotulo, Icone }) => (
              <NavLink
                key={para}
                to={para}
                className={({ isActive }) =>
                  cn(
                    "inline-flex h-11 shrink-0 items-center gap-3 rounded-md px-3 text-[15px] font-semibold transition-colors duration-150",
                    FOCO_ESCURO,
                    isActive ? "bg-white/10 text-white" : "text-ink-muted hover:bg-white/5 hover:text-white",
                  )
                }
              >
                <Icone className="size-[18px]" aria-hidden="true" />
                {rotulo}
              </NavLink>
            ))}
          </div>
        ))}
      </div>
    </nav>
  )
}

function Trilha() {
  const { pathname } = useLocation()
  for (const { grupo, itens } of GRUPOS_MENU) {
    const item = itens.find((i) => pathname.startsWith(i.para))
    if (item)
      return (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {grupo}
          <ChevronRight className="size-4" aria-hidden="true" />
          <span className="font-semibold text-foreground">{item.rotulo}</span>
        </p>
      )
  }
  return <span />
}

export function LayoutAutenticado() {
  const { sair } = useSessao()
  const [dataDeHoje] = useState(() => hoje.format(new Date()))

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-lg bg-card px-4 py-2 font-semibold text-primary focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Pular para o conteúdo
      </a>

      <header className="bg-heading text-white lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 pt-4 pb-3 lg:flex-col lg:items-stretch lg:gap-0 lg:px-3 lg:pt-5 lg:pb-0">
          <div className="lg:px-3">
            <Logo tamanho={26} sobreEscuro className="[&>span:last-child]:text-[20px]" />
          </div>
          <div className="order-3 w-full lg:order-none lg:mt-8">
            <Navegacao />
          </div>
        </div>

        <div className="hidden flex-1 lg:block" />

        <div className="flex items-center gap-3 border-t border-ink-line px-4 py-3 lg:flex-col lg:items-stretch lg:gap-1 lg:px-3 lg:py-3">
          <div className="min-w-0 flex-1 lg:px-3 lg:py-1">
            <QuemEsta />
          </div>
          <Button
            variant="ghost"
            onClick={sair}
            className={cn("text-ink-muted hover:bg-white/5 hover:text-white lg:justify-start lg:px-3", FOCO_ESCURO)}
          >
            <LogOut aria-hidden="true" />
            Sair
          </Button>
        </div>
      </header>

      <div className="flex min-w-0 flex-col">
        <section aria-label="Onde você está" className="border-b border-line bg-card">
          <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <Trilha />
            <p className="hidden text-sm text-muted-foreground first-letter:uppercase sm:block">{dataDeHoje}</p>
          </div>
        </section>

        <main
          id="conteudo"
          tabIndex={-1}
          className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 focus:outline-none sm:px-6 lg:px-8"
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
