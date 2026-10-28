/*
 * Estrutura das telas autenticadas do SaaS (passo W5, redesenhado em
 * 28/10/2026), pela skill Frescor:
 *
 * - Barra lateral escura (--secondary -> --ink, a "sala de controle" da
 *   central) com o logo, a navegação em dois grupos (Dados: Importar e
 *   Consultar; Planejamento: Previsão e Produção) e, no rodapé, quem está
 *   logado (gestor · central · negócio, de GET /web/me) e "Sair".
 *   Abaixo de 1024px ela vira uma faixa no topo com a navegação rolando de
 *   lado. É o <header> da página (papel "banner").
 * - Faixa superior clara com onde a pessoa está (grupo / tela) e a data de
 *   hoje, e a área de trabalho com um brilho suave nos cantos.
 *
 * "Sair" é um botão discreto (ghost): a ação principal de cada tela fica
 * com o conteúdo, não com a navegação (skill: uma ação principal por tela).
 * Ícones sempre com texto. Link "Pular para o conteúdo" para teclado.
 */
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { CalendarDays, ChartLine, ChevronRight, Factory, LogOut, Search, Upload } from "lucide-react"
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

/** Iniciais para o avatar: "Gestor Central Teste" -> "GC". */
function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  return partes
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
        className="grid size-10 shrink-0 place-items-center rounded-full bg-highlight font-heading text-sm font-bold text-ink ring-2 ring-white/15"
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
      <div className="flex gap-1 lg:flex-col lg:gap-6">
        {GRUPOS_MENU.map(({ grupo, itens }) => (
          <div key={grupo} className="flex gap-1 lg:flex-col">
            <p className="hidden px-3 pb-1 text-xs font-semibold tracking-[0.12em] text-ink-muted uppercase lg:block">
              {grupo}
            </p>
            {itens.map(({ para, rotulo, Icone }) => (
              <NavLink
                key={para}
                to={para}
                className={({ isActive }) =>
                  cn(
                    "group relative inline-flex h-11 shrink-0 items-center gap-3 rounded-lg px-3 font-semibold transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mint",
                    isActive
                      ? "bg-white/[0.09] text-white ring-1 ring-white/10 ring-inset"
                      : "text-ink-muted hover:bg-white/[0.05] hover:text-white",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {/* Marcador dourado do item atual (à esquerda no desktop, embaixo no celular). */}
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute rounded-full bg-highlight transition-opacity duration-150",
                        "inset-x-3 -bottom-px h-0.5 lg:inset-x-auto lg:inset-y-2.5 lg:-left-px lg:h-auto lg:w-[3px]",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <Icone
                      className={cn("size-5 transition-colors", isActive ? "text-highlight" : "text-ink-muted group-hover:text-white")}
                      aria-hidden="true"
                    />
                    {rotulo}
                  </>
                )}
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
  const { pathname } = useLocation()
  const [dataDeHoje] = useState(() => hoje.format(new Date()))

  return (
    <div className="min-h-screen fundo-trabalho lg:grid lg:grid-cols-[272px_minmax(0,1fr)]">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-lg bg-card px-4 py-2 font-semibold text-primary focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Pular para o conteúdo
      </a>

      <header className="relative isolate overflow-hidden bg-linear-to-b from-heading to-ink text-white lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
        {/* Fundo decorativo: trama de pontos e um brilho verde no topo. */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 trama-pontos opacity-60" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 -left-16 -z-10 size-72 rounded-full bg-primary opacity-40 blur-3xl"
        />

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 pt-4 pb-3 lg:flex-col lg:items-stretch lg:gap-0 lg:px-4 lg:pt-6 lg:pb-0">
          <div className="flex items-center justify-between gap-4 lg:px-2">
            <Logo tamanho={34} sobreEscuro className="[&>span:last-child]:text-[24px]" />
          </div>
          <p className="hidden px-2 pt-1 text-sm text-ink-muted lg:block">Central de produção</p>

          <div className="order-3 w-full lg:order-none lg:mt-8">
            <Navegacao />
          </div>
        </div>

        <div className="hidden flex-1 lg:block" />

        <div className="flex items-center gap-3 border-t border-ink-line/80 bg-white/[0.02] px-4 py-3 lg:flex-col lg:items-stretch lg:gap-2 lg:px-4 lg:py-4">
          <div className="min-w-0 flex-1 lg:px-1">
            <QuemEsta />
          </div>
          <Button
            variant="ghost"
            onClick={sair}
            className="text-ink-muted hover:bg-white/10 hover:text-white focus-visible:outline-mint lg:justify-start lg:px-3"
          >
            <LogOut aria-hidden="true" />
            Sair
          </Button>
        </div>
      </header>

      <div className="flex min-w-0 flex-col">
        <section
          aria-label="Onde você está"
          className="sticky top-0 z-30 border-b border-line/70 bg-background/75 backdrop-blur-md"
        >
          <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <Trilha />
            <p className="hidden items-center gap-2 rounded-full bg-card px-3 py-1 text-sm text-muted-foreground shadow-painel sm:flex">
              <CalendarDays className="size-4 text-primary" aria-hidden="true" />
              <span className="inline-block first-letter:uppercase">{dataDeHoje}</span>
            </p>
          </div>
        </section>

        <main
          id="conteudo"
          tabIndex={-1}
          className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 focus:outline-none sm:px-6 lg:px-8 lg:py-10"
        >
          {/* A chave pela rota faz cada tela entrar com um "surgir" curto (200ms). */}
          <div key={pathname} className="animate-surgir">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
