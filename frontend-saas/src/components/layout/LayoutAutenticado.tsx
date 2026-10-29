/*
 * Estrutura das telas autenticadas do SaaS (passo W5), pela skill Frescor:
 * cabeçalho com o logo, a navegação (Importar / Consultar / Previsão / Produção / Distribuição), quem está
 * logado (gestor · central · negócio, de GET /web/me) e "Sair".
 *
 * "Sair" é um botão discreto (ghost): a ação principal de cada tela fica
 * com o conteúdo, não com o cabeçalho (skill: uma ação principal por tela).
 * Ícones sempre com texto. Link "Pular para o conteúdo" para teclado.
 */
import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { ChartLine, Factory, LogOut, Search, Truck, Upload } from "lucide-react"
import { NavLink, Outlet } from "react-router"
import { Logo } from "@/components/marca/Logo"
import { Button } from "@/components/ui/button"
import { apiJson } from "@/lib/api/cliente"
import type { Me } from "@/lib/api/tipos"
import { useSessao } from "@/lib/sessao/contexto"

const ITENS_MENU = [
  { para: "/importar", rotulo: "Importar", Icone: Upload },
  { para: "/consultar", rotulo: "Consultar", Icone: Search },
  { para: "/previsao", rotulo: "Previsão", Icone: ChartLine },
  { para: "/producao", rotulo: "Produção", Icone: Factory },
  { para: "/distribuicao", rotulo: "Distribuição", Icone: Truck },
]

function QuemEsta() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => apiJson<Me>("/web/me"),
  })

  if (isPending) return <span className="text-sm text-muted-foreground">Carregando…</span>
  if (isError || !data) return <span className="text-sm text-muted-foreground">Não foi possível carregar seus dados.</span>

  return (
    <span className="flex flex-col text-right leading-tight">
      <span className="text-sm font-semibold text-foreground">{data.usuario.nome}</span>
      <span className="text-sm text-muted-foreground">
        {data.central.nome} · {data.negocio.nome}
      </span>
    </span>
  )
}

export function LayoutAutenticado() {
  const { sair } = useSessao()

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-lg bg-card px-4 py-2 font-semibold text-primary focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Pular para o conteúdo
      </a>

      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3">
          <Logo tamanho={32} className="[&>span:last-child]:text-[22px]" />

          <nav aria-label="Principal" className="flex gap-2">
            {ITENS_MENU.map(({ para, rotulo, Icone }) => (
              <NavLink
                key={para}
                to={para}
                className={({ isActive }) =>
                  cn(
                    "inline-flex h-11 items-center gap-2 rounded-lg px-3 font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                    isActive ? "bg-surface text-primary" : "text-foreground hover:bg-surface",
                  )
                }
              >
                <Icone className="size-5" aria-hidden="true" />
                {rotulo}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            <QuemEsta />
            <Button variant="ghost" onClick={sair}>
              <LogOut aria-hidden="true" />
              Sair
            </Button>
          </div>
        </div>
      </header>

      <main id="conteudo" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 focus:outline-none">
        <Outlet />
      </main>
    </div>
  )
}
