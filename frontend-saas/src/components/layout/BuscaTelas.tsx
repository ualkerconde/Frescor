/*
 * Busca de telas da barra do topo (padrão de 11/11/2026): botão "Buscar
 * tela…" com o atalho Ctrl K (⌘ K no Mac) que abre uma lista filtrável das
 * telas do menu. Só navega; não procura dados (busca de produto continua
 * na consulta e nos cadastros).
 */
import { useEffect, useState } from "react"
import { Search } from "lucide-react"
import { useNavigate } from "react-router"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { GRUPOS_MENU } from "./menu"

const ehMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)

export function BuscaTelas() {
  const [aberta, setAberta] = useState(false)
  const navegar = useNavigate()

  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        setAberta((a) => !a)
      }
    }
    window.addEventListener("keydown", aoTeclar)
    return () => window.removeEventListener("keydown", aoTeclar)
  }, [])

  function ir(para: string) {
    setAberta(false)
    navegar(para)
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setAberta(true)}
        aria-keyshortcuts={ehMac ? "Meta+K" : "Control+K"}
        className="inline-flex h-11 items-center gap-2 rounded-lg border border-line bg-background px-3 text-muted-foreground transition-colors duration-150 hover:border-input-border hover:text-foreground md:w-72"
      >
        <Search className="size-[18px]" aria-hidden="true" />
        <span className="hidden md:inline">Buscar tela…</span>
        <span className="sr-only md:hidden">Buscar tela</span>
        <kbd
          aria-hidden="true"
          className="ml-auto hidden rounded-sm border border-line bg-card px-1.5 py-0.5 font-sans text-xs font-semibold text-muted-foreground md:inline"
        >
          {ehMac ? "⌘ K" : "Ctrl K"}
        </kbd>
      </button>

      <Dialog open={aberta} onOpenChange={setAberta}>
        {/* Título dentro do conteúdo do diálogo: o CommandDialog do shadcn o deixa fora, no meio da página. */}
        <DialogContent className="top-[20%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-lg" showCloseButton={false}>
          <DialogTitle className="sr-only">Buscar tela</DialogTitle>
          <DialogDescription className="sr-only">Digite o nome da tela e tecle Enter para abrir.</DialogDescription>
          <Command>
          <CommandInput placeholder="Para onde você quer ir?" />
          <CommandList>
            <CommandEmpty>Nenhuma tela com esse nome.</CommandEmpty>
            {GRUPOS_MENU.map(({ grupo, itens }) => (
              <CommandGroup key={grupo} heading={grupo}>
                {itens.map(({ para, rotulo, descricao, Icone }) => (
                  <CommandItem key={para} value={`${rotulo} ${descricao}`} onSelect={() => ir(para)}>
                    <Icone aria-hidden="true" />
                    <span className="flex flex-col">
                      <span className="font-semibold">{rotulo}</span>
                      <span className="text-sm text-muted-foreground">{descricao}</span>
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
          </Command>
        </DialogContent>
      </Dialog>
    </>
  )
}
