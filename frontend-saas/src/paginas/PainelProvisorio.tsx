/*
 * Página provisória depois do login (W4). O W5 troca pela estrutura
 * autenticada (cabeçalho com gestor/central, navegação Importar/Consultar).
 */
import { LogOut } from "lucide-react"
import { Logo } from "@/components/marca/Logo"
import { Button } from "@/components/ui/button"
import { useSessao } from "@/lib/sessao/contexto"

export function PainelProvisorio() {
  const { sair } = useSessao()
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <Logo />
      <div>
        <h1 className="text-[28px]">Você entrou</h1>
        <p className="mt-2 text-muted-foreground">
          As telas de importação e de consulta chegam nos próximos passos.
        </p>
      </div>
      <div>
        <Button variant="secondary" onClick={sair}>
          <LogOut aria-hidden="true" />
          Sair
        </Button>
      </div>
    </main>
  )
}
