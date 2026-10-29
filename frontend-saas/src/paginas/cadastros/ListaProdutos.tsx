/*
 * Lista de produtos do cadastro (Fase 6 / C4): busca por código ou nome
 * (o backend ignora acentos e maiúsculas), 50 por página, e a ação
 * principal "Novo produto". Cada linha leva ao formulário do produto.
 * A busca espera 300 ms depois da última tecla e fica na URL (?busca=).
 */
import { useEffect, useId, useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { CircleAlert, CircleCheck, CircleSlash, Plus } from "lucide-react"
import { Link, useSearchParams } from "react-router"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { ProdutosWeb } from "@/lib/api/tipos"
import { contar } from "@/lib/formato"

const POR_PAGINA = 50
const PILL = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap"

export function SituacaoProduto({ ativo }: { ativo: boolean }) {
  return ativo ? (
    <span className={cn(PILL, "bg-success-bg text-success")}>
      <CircleCheck className="size-4" aria-hidden="true" />
      Ativo
    </span>
  ) : (
    <span className={cn(PILL, "bg-surface text-foreground")}>
      <CircleSlash className="size-4" aria-hidden="true" />
      Inativo
    </span>
  )
}

export function ListaProdutos() {
  const [params, setParams] = useSearchParams()
  const busca = params.get("busca") ?? ""
  const pagina = Math.max(0, Number(params.get("pagina") ?? 0) || 0)
  const [digitado, setDigitado] = useState(busca)
  const id = useId()

  useEffect(() => {
    const t = setTimeout(() => {
      if (digitado.trim() !== busca) setParams(digitado.trim() ? { busca: digitado.trim() } : {}, { replace: true })
    }, 300)
    return () => clearTimeout(t)
  }, [digitado, busca, setParams])

  const lista = useQuery({
    queryKey: ["cadastro", "produtos", busca, pagina],
    queryFn: () => {
      const q = new URLSearchParams({ limit: String(POR_PAGINA), offset: String(pagina * POR_PAGINA) })
      if (busca) q.set("busca", busca)
      return apiJson<ProdutosWeb>(`/web/produtos?${q}`)
    },
    placeholderData: keepPreviousData,
  })

  function irPara(p: number) {
    const q: Record<string, string> = {}
    if (busca) q.busca = busca
    if (p > 0) q.pagina = String(p)
    setParams(q)
  }

  const total = lista.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex w-full max-w-md flex-col gap-2">
          <Label htmlFor={`${id}-busca`}>Buscar produto</Label>
          <Input
            id={`${id}-busca`}
            type="search"
            placeholder="Código ou nome"
            value={digitado}
            onChange={(e) => setDigitado(e.target.value)}
          />
        </div>
        <Button asChild>
          <Link to="/cadastros/produtos/novo">
            <Plus aria-hidden="true" />
            Novo produto
          </Link>
        </Button>
      </div>

      <div aria-live="polite">
        {lista.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{lista.error.message}</AlertTitle>
            <AlertDescription>Recarregue a página. Se continuar, tente de novo em alguns minutos.</AlertDescription>
          </Alert>
        ) : lista.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : lista.data.itens.length === 0 ? (
          <div className="rounded-lg bg-surface p-6">
            {busca ? (
              <p>Nenhum produto com “{busca}” no código ou no nome.</p>
            ) : (
              <>
                <p>Nenhum produto cadastrado ainda.</p>
                <p className="mt-1 text-muted-foreground">
                  Cadastre o primeiro produto para ele entrar na previsão e na ordem de produção.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">{contar(total, "produto", "produtos")}</p>
            <Table aria-label="Produtos">
              <TableHeader>
                <TableRow>
                  <TableHead>Código</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead>Unidade</TableHead>
                  <TableHead>Abastecimento</TableHead>
                  <TableHead>Setor</TableHead>
                  <TableHead className="text-right">Lojas ativas</TableHead>
                  <TableHead>Situação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lista.data.itens.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="numero">{p.codigo ?? "sem código"}</TableCell>
                    <TableCell>
                      <Link to={`/cadastros/produtos/${p.id}`} className="font-semibold text-primary underline">
                        {p.nome}
                      </Link>
                    </TableCell>
                    <TableCell>{p.unidade === "KG" ? "kg" : "un"}</TableCell>
                    <TableCell>{p.tipo_abastecimento === "distribuido" ? "Distribuído" : "Produzido"}</TableCell>
                    <TableCell>{p.setor ?? <span className="text-muted-foreground">Sem setor</span>}</TableCell>
                    <TableCell className="text-right numero">{p.lojas_ativas ?? 0}</TableCell>
                    <TableCell>
                      <SituacaoProduto ativo={p.ativo} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {paginas > 1 && (
              <div className="flex items-center gap-3">
                <Button variant="secondary" disabled={pagina === 0} onClick={() => irPara(pagina - 1)}>
                  Anterior
                </Button>
                <span className="text-sm text-muted-foreground">
                  Página {pagina + 1} de {paginas}
                </span>
                <Button variant="secondary" disabled={pagina + 1 >= paginas} onClick={() => irPara(pagina + 1)}>
                  Próxima
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
