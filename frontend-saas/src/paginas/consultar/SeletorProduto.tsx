/*
 * Seletor de produto com busca (passo W7): padrão "combobox" do shadcn
 * (Popover + Command), com a filtragem feita pelo backend em
 * GET /web/produtos, que ignora acentos e maiúsculas ("pao" acha "Pão").
 * A busca espera 300 ms depois da última tecla antes de chamar a API.
 */
import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronsUpDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { apiJson } from "@/lib/api/cliente"
import type { ProdutosWeb } from "@/lib/api/tipos"

export interface ProdutoEscolhido {
  id: number
  rotulo: string
}

function rotuloProduto(p: { codigo: string | null; nome: string }): string {
  return p.codigo ? `${p.codigo} · ${p.nome}` : p.nome
}

function useValorAtrasado<T>(valor: T, ms: number): T {
  const [atrasado, setAtrasado] = useState(valor)
  useEffect(() => {
    const t = setTimeout(() => setAtrasado(valor), ms)
    return () => clearTimeout(t)
  }, [valor, ms])
  return atrasado
}

export function SeletorProduto({
  id,
  valor,
  aoMudar,
  textoVazio = "Todos os produtos",
  oferecerTodos = true,
}: {
  id: string
  valor: ProdutoEscolhido | null
  aoMudar: (produto: ProdutoEscolhido | null) => void
  /** O que o botão mostra sem produto escolhido (o cadastro de eventos usa "Adicionar produto"). */
  textoVazio?: string
  /** Mostra a opção "Todos os produtos" na lista. */
  oferecerTodos?: boolean
}) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState("")
  const buscaAtrasada = useValorAtrasado(busca.trim(), 300)

  const { data, isFetching, isError } = useQuery({
    queryKey: ["produtos", buscaAtrasada],
    queryFn: () =>
      apiJson<ProdutosWeb>(`/web/produtos?limit=20${buscaAtrasada ? `&busca=${encodeURIComponent(buscaAtrasada)}` : ""}`),
    enabled: aberto,
  })

  function escolher(produto: ProdutoEscolhido | null) {
    aoMudar(produto)
    setAberto(false)
    setBusca("")
  }

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={aberto}
          className="w-full justify-between font-normal"
        >
          <span className="truncate">{valor ? valor.rotulo : textoVazio}</span>
          <ChevronsUpDown className="text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-1" align="start">
        {/* `label` vira o nome acessível do campo de busca (o cmdk usa aria-labelledby). */}
        <Command shouldFilter={false} label="Buscar produto">
          <CommandInput placeholder="Código ou nome do produto" value={busca} onValueChange={setBusca} />
          <CommandList>
            <CommandEmpty>
              {isError
                ? "Não foi possível buscar os produtos. Tente de novo."
                : isFetching || !data
                  ? "Buscando…"
                  : "Nenhum produto encontrado. Confira o código ou o nome."}
            </CommandEmpty>
            {data && (
              <CommandGroup>
                {oferecerTodos && !buscaAtrasada && (
                  <CommandItem value="todos" onSelect={() => escolher(null)} data-checked={valor === null}>
                    Todos os produtos
                  </CommandItem>
                )}
                {data.itens.map((p) => (
                  <CommandItem
                    key={p.id}
                    value={String(p.id)}
                    onSelect={() => escolher({ id: p.id, rotulo: rotuloProduto(p) })}
                    data-checked={valor?.id === p.id}
                  >
                    <span className="truncate">{rotuloProduto(p)}</span>
                    {!p.ativo && <span className="text-sm text-muted-foreground">(inativo)</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
