/*
 * Cadastros do SaaS (Fase 6 / C4), pela skill Frescor. Carregada só quando
 * aberta (React.lazy em App.tsx).
 *
 * Três partes, cada uma com o endereço próprio (e uma ação principal só):
 * - /cadastros/produtos: lista com busca; "Novo produto"; cada produto abre
 *   o formulário (/cadastros/produtos/novo e /cadastros/produtos/:id), com
 *   as lojas da central logo abaixo (ativar e desativar por loja, D100);
 * - /cadastros/setores: setores de produção (D67, D102);
 * - /cadastros/central: nome e prazo de entrega da central (D103).
 */
import { cn } from "cn"
import { Building2, Layers, Package } from "lucide-react"
import { Navigate, NavLink, Route, Routes } from "react-router"
import { Toaster } from "@/components/ui/sonner"
import { Central } from "./cadastros/Central"
import { EditarProduto, NovoProduto } from "./cadastros/PaginaProduto"
import { ListaProdutos } from "./cadastros/ListaProdutos"
import { Setores } from "./cadastros/Setores"

const PARTES = [
  { para: "/cadastros/produtos", rotulo: "Produtos", Icone: Package },
  { para: "/cadastros/setores", rotulo: "Setores de produção", Icone: Layers },
  { para: "/cadastros/central", rotulo: "Central", Icone: Building2 },
]

export function Cadastros() {
  return (
    <section className="flex flex-col gap-8">
      <div>
        <h1 className="text-[28px]">Cadastros</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Produtos, setores de produção e a sua central. O que você muda aqui vale para a próxima previsão e a próxima
          ordem de produção; as ordens já aprovadas não mudam.
        </p>
      </div>

      <nav aria-label="Cadastros" className="flex flex-wrap gap-2 border-b border-line pb-3">
        {PARTES.map(({ para, rotulo, Icone }) => (
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

      <Routes>
        <Route index element={<Navigate to="produtos" replace />} />
        <Route path="produtos" element={<ListaProdutos />} />
        <Route path="produtos/novo" element={<NovoProduto />} />
        <Route path="produtos/:produtoId" element={<EditarProduto />} />
        <Route path="setores" element={<Setores />} />
        <Route path="central" element={<Central />} />
        <Route path="*" element={<Navigate to="produtos" replace />} />
      </Routes>

      {/* Avisos de sucesso montados aqui (e não no layout): a biblioteca vai no pacote desta tela. */}
      <Toaster position="bottom-right" />
    </section>
  )
}
