/*
 * Estrutura das telas autenticadas do SaaS (passo W5; redesenhada em
 * 28/10/2026 e de novo em 11/11/2026 no padrão da referência que o sócio do
 * Ualker mandou), pela skill Frescor:
 *
 * - Barra lateral em --secondary, lisa (é o <header> da página, papel
 *   "banner"): bloco da marca (logo + "Central de produção"), navegação por
 *   seções com rótulo em maiúsculas (Visão, Dados, Planejamento, Operação,
 *   Configuração), item atual com fundo branco a 8% e ícone dourado, e no
 *   rodapé o cartão de quem está logado (gestor · central · negócio, de
 *   GET /web/me) com "Sair". Abaixo de 1024px vira uma faixa no topo, com a
 *   navegação rolando de lado.
 * - Barra do topo, branca e fixa: seção em maiúsculas e o nome da tela
 *   ("PLANEJAMENTO / Produção"), a busca de telas (Ctrl K). A data fica no cabeçalho de cada tela.
 *   O título da tela (h1) continua no conteúdo.
 *
 * "Sair" é um botão discreto (ghost): a ação principal de cada tela fica
 * com o conteúdo, não com a navegação (skill: uma ação principal por tela).
 * Ícones sempre com texto. Link "Pular para o conteúdo" para teclado.
 */
import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { LogOut } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router"
import { Logo } from "@/components/marca/Logo"
import { Button } from "@/components/ui/button"
import { apiJson } from "@/lib/api/cliente"
import type { Me } from "@/lib/api/tipos"
import { useSessao } from "@/lib/sessao/contexto"
import { BuscaTelas } from "./BuscaTelas"
import { GRUPOS_MENU, localizar } from "./menu"


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
        className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-sm font-semibold text-white"
      >
        {iniciais(data.usuario.nome)}
      </span>
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate text-sm font-semibold text-white">{data.usuario.nome}</span>
        <span className="truncate text-xs text-ink-muted">
          {data.central.nome} · {data.negocio.nome}
        </span>
      </span>
    </span>
  )
}

function Navegacao() {
  return (
    <nav aria-label="Principal" className="-mx-1 overflow-x-auto px-1 lg:mx-0 lg:overflow-visible lg:px-0">
      <div className="flex gap-1 lg:flex-col lg:gap-4">
        {GRUPOS_MENU.map(({ grupo, itens }) => (
          <div key={grupo} className="flex gap-1 lg:flex-col lg:gap-0.5">
            <p className="hidden px-3 pb-1.5 text-xs font-semibold tracking-[0.08em] text-ink-muted uppercase lg:block">
              {grupo}
            </p>
            {itens.map(({ para, rotulo, Icone }) => (
              <NavLink
                key={para}
                to={para}
                className={({ isActive }) =>
                  cn(
                    "group inline-flex h-11 shrink-0 items-center gap-3 rounded-lg px-3 text-[15px] font-semibold transition-colors duration-150",
                    FOCO_ESCURO,
                    isActive ? "bg-white/[0.08] text-white" : "text-ink-muted hover:bg-white/[0.04] hover:text-white",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icone className={cn("size-[18px]", isActive && "text-highlight")} aria-hidden="true" />
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

function BarraLateral() {
  const { sair } = useSessao()
  return (
    <header className="bg-heading text-white lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
      {/*
        No desktop esta parte ocupa a altura que sobra e rola sozinha. `lg:flex-nowrap` é obrigatório: com
        `flex-wrap` + coluna, numa janela baixa (ex.: notebook 1366×768 com a barra do navegador) o menu
        quebrava numa segunda coluna, cortada pela largura da barra (bug visto pelo Ualker em 11/11/2026).
      */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 pt-4 pb-3 [scrollbar-color:var(--fr-ink-line)_transparent] [scrollbar-width:thin] lg:min-h-0 lg:flex-1 lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-0 lg:overflow-x-hidden lg:overflow-y-auto lg:px-3 lg:pt-5 lg:pb-4">
        <div className="flex shrink-0 flex-col gap-1 lg:border-b lg:border-ink-line lg:px-3 lg:pb-5">
          <Logo tamanho={28} sobreEscuro className="[&>span:last-child]:text-[21px]" />
          <span className="hidden pl-[38px] text-xs font-semibold tracking-[0.08em] text-ink-muted uppercase lg:block">
            Central de produção
          </span>
        </div>
        <div className="order-3 w-full lg:order-none lg:mt-6">
          <Navegacao />
        </div>
      </div>

      {/* Rodapé fixo: usuário e "Sair" numa linha só, para sobrar altura para o menu. */}
      <div className="flex shrink-0 items-center gap-3 border-t border-ink-line px-4 py-3 lg:gap-2 lg:px-3">
        <div className="min-w-0 flex-1 lg:pl-3">
          <QuemEsta />
        </div>
        <Button
          variant="ghost"
          onClick={sair}
          className={cn("text-ink-muted hover:bg-white/[0.04] hover:text-white lg:px-2.5", FOCO_ESCURO)}
        >
          <LogOut aria-hidden="true" />
          Sair
        </Button>
      </div>
    </header>
  )
}

function BarraTopo() {
  const { pathname } = useLocation()
  const onde = localizar(pathname)

  return (
    <section aria-label="Barra superior" className="sticky top-0 z-30 border-b border-line bg-card">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <div className="min-w-0">
          {onde && (
            <>
              <p className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">{onde.grupo}</p>
              <p className="truncate font-heading text-lg leading-tight font-semibold text-heading">
                {onde.item.rotulo}
              </p>
            </>
          )}
        </div>
        <BuscaTelas />
      </div>
    </section>
  )
}

export function LayoutAutenticado() {
  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[256px_minmax(0,1fr)]">
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
