/*
 * Estrutura das telas autenticadas do SaaS (passo W5; redesenhada em
 * 28/10/2026, em 11/11/2026 no padrão da referência do sócio do Ualker e em
 * 13/11/2026 no visual "Comando" azul-noite e âmbar, D117).
 *
 * - Barra lateral de ícones (76px, --rail), lisa, é o <header> da página
 *   (papel "banner"): selo do Frescor no topo, um ícone por tela, separados
 *   por seção, e no pé "Trocar senha", "Sair" e o avatar de quem está logado.
 *   Item atual: fundo --primary-soft, ícone âmbar e um traço âmbar de 2px à
 *   esquerda.
 * - Ícone nunca fica sem nome (skill): cada ícone tem o rótulo em texto, que
 *   aparece como dica ao lado ao passar o mouse ou focar pelo teclado, e é o
 *   nome que o leitor de tela lê. O nome da seção fica para o leitor de tela.
 * - Abaixo de 1024px a barra vira uma faixa no topo, com ícone + rótulo
 *   visíveis e a navegação rolando de lado.
 * - Barra do topo (fixa): seção em maiúsculas e o nome da tela
 *   ("PLANEJAMENTO / Produção") e a busca de telas (Ctrl K). O título da
 *   tela (h1) continua no conteúdo.
 *
 * "Sair" é discreto: a ação principal de cada tela fica com o conteúdo, não
 * com a navegação (skill: uma ação principal por tela). Link "Pular para o
 * conteúdo" para teclado.
 */
import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { KeyRound, LogOut } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router"
import { Logo } from "@/components/marca/Logo"
import { apiJson } from "@/lib/api/cliente"
import type { Me } from "@/lib/api/tipos"
import { useSessao } from "@/lib/sessao/contexto"
import { BuscaTelas } from "./BuscaTelas"
import { GRUPOS_MENU, localizar } from "./menu"

/** Quadrado de 44px do ícone na barra (área de toque da skill). */
const ITEM =
  "group relative inline-flex h-11 shrink-0 items-center gap-2 rounded-xl px-3 text-ink-muted transition-colors duration-150 hover:bg-surface hover:text-foreground lg:w-11 lg:justify-center lg:px-0"

/**
 * Dica com o nome do ícone: no desktop flutua à direita da barra e aparece
 * no hover e no foco; no celular é o rótulo visível ao lado do ícone.
 */
const DICA =
  "text-sm font-semibold whitespace-nowrap lg:pointer-events-none lg:absolute lg:top-1/2 lg:left-full lg:z-50 lg:ml-3 lg:-translate-y-1/2 lg:rounded-lg lg:border lg:border-line lg:bg-surface lg:px-2.5 lg:py-1.5 lg:text-foreground lg:opacity-0 lg:shadow-elevado lg:transition-opacity lg:duration-150 lg:group-hover:opacity-100 lg:group-focus-visible:opacity-100"

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

  const detalhe = isPending ? (
    <span className="text-sm text-ink-muted">Carregando…</span>
  ) : isError || !data ? (
    <span className="text-sm text-ink-muted">Não foi possível carregar seus dados.</span>
  ) : (
    <span className="flex flex-col leading-tight">
      <span className="text-sm font-semibold text-foreground">{data.usuario.nome}</span>
      <span className="text-xs text-ink-muted">
        {data.central.nome} · {data.negocio.nome}
      </span>
    </span>
  )

  return (
    // tabIndex 0: dá para ver no teclado quem está logado (a dica abre no foco).
    <span tabIndex={0} className="group relative inline-flex shrink-0 items-center rounded-full">
      <span
        aria-hidden="true"
        className="grid size-10 place-items-center rounded-full border border-line bg-primary-soft text-[13px] font-semibold text-foreground"
      >
        {data ? iniciais(data.usuario.nome) : "··"}
      </span>
      <span
        className={cn(
          "pointer-events-none absolute top-full right-0 z-50 mt-2 rounded-lg border border-line bg-surface px-3 py-2 whitespace-nowrap opacity-0 shadow-elevado transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100",
          "lg:top-auto lg:right-auto lg:bottom-0 lg:left-full lg:mt-0 lg:ml-3",
        )}
      >
        {detalhe}
      </span>
    </span>
  )
}

function Navegacao() {
  return (
    <nav aria-label="Principal" className="-mx-1 min-w-0 overflow-x-auto px-1 lg:mx-0 lg:overflow-visible lg:px-0">
      <div className="flex gap-1 lg:flex-col lg:items-center lg:gap-0">
        {GRUPOS_MENU.map(({ grupo, itens }, i) => (
          <div
            key={grupo}
            className={cn("flex gap-1 lg:flex-col lg:items-center", i > 0 && "lg:mt-2 lg:border-t lg:border-ink-line lg:pt-2")}
          >
            <p className="sr-only">{grupo}</p>
            {itens.filter((it) => !it.foraDoMenu).map(({ para, rotulo, Icone }) => (
              <NavLink
                key={para}
                to={para}
                className={({ isActive }) =>
                  cn(ITEM, isActive && "bg-primary-soft text-primary shadow-[inset_2px_0_0_var(--fr-primary)] hover:text-primary")
                }
              >
                <Icone className="size-5" aria-hidden="true" />
                <span className={DICA}>{rotulo}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </div>
    </nav>
  )
}

function BarraLateral() {
  const { sair } = useSessao()
  return (
    // No celular: selo e conta numa linha, a navegação inteira na linha de baixo (rolando de lado).
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-rail px-3 py-2 lg:sticky lg:top-0 lg:z-40 lg:h-screen lg:flex-col lg:flex-nowrap lg:border-r lg:border-b-0 lg:px-0 lg:py-5">
      <Logo comNome={false} tamanho={40} className="shrink-0 lg:mb-4" />
      <div className="order-last w-full min-w-0 lg:order-none">
        <Navegacao />
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1 lg:mt-auto lg:ml-0 lg:flex-col lg:gap-1">
        <NavLink
          to="/senha"
          className={({ isActive }) => cn(ITEM, isActive && "bg-primary-soft text-primary hover:text-primary")}
        >
          <KeyRound className="size-5" aria-hidden="true" />
          <span className={cn(DICA, "max-lg:sr-only")}>Trocar senha</span>
        </NavLink>
        <button type="button" onClick={sair} className={ITEM}>
          <LogOut className="size-5" aria-hidden="true" />
          <span className={cn(DICA, "max-lg:sr-only")}>Sair</span>
        </button>
        <span className="ml-1 lg:mt-2 lg:ml-0">
          <QuemEsta />
        </span>
      </div>
    </header>
  )
}

function BarraTopo() {
  const { pathname } = useLocation()
  const onde = localizar(pathname)

  return (
    <section
      aria-label="Barra superior"
      className="sticky top-0 z-30 border-b border-line bg-background"
    >
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <div className="min-w-0">
          {onde && (
            <p className="flex min-w-0 items-baseline gap-2 truncate">
              <span className="text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">{onde.grupo}</span>
              <span aria-hidden="true" className="text-muted-foreground">
                /
              </span>
              <span className="truncate font-heading text-base font-semibold text-heading">{onde.item.rotulo}</span>
            </p>
          )}
        </div>
        <BuscaTelas />
      </div>
    </section>
  )
}

export function LayoutAutenticado() {
  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[76px_minmax(0,1fr)]">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-lg bg-card px-4 py-2 font-semibold text-primary focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Pular para o conteúdo
      </a>

      <BarraLateral />

      <div className="flex min-w-0 flex-col">
        <BarraTopo />
        <main
          id="conteudo"
          tabIndex={-1}
          className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 focus:outline-none sm:px-6 lg:px-8"
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
