/*
 * Lojas do produto (Fase 6 / C3, D100): cada loja da central e a situação
 * do produto nela, com "Ativar nesta loja" / "Desativar nesta loja"
 * (botões secundários: a ação principal da tela é salvar o produto).
 *
 * Desativar não apaga a habilitação: o histórico e a data de início
 * continuam, e o produto some da contagem no app, da previsão e da ordem
 * daquela loja. Muda na hora (sem salvar o formulário), com aviso.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { cn } from "cn"
import { CircleAlert, CircleCheck, CircleSlash, Store } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { LojaDoProduto } from "@/lib/api/tipos"

const PILL = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap"

function nomeLoja(l: LojaDoProduto): string {
  return l.codigo ? `${l.codigo} · ${l.nome}` : l.nome
}

function Situacao({ loja }: { loja: LojaDoProduto }) {
  if (loja.ativo) {
    return (
      <span className={cn(PILL, "bg-success-bg text-success")}>
        <CircleCheck className="size-4" aria-hidden="true" />
        Ativo
      </span>
    )
  }
  return (
    <span className={cn(PILL, "bg-surface text-foreground")}>
      <CircleSlash className="size-4" aria-hidden="true" />
      {loja.habilitado ? "Desativado" : "Nunca ativado"}
    </span>
  )
}

export function LojasDoProduto({ produtoId, produtoAtivo }: { produtoId: number; produtoAtivo: boolean }) {
  const queryClient = useQueryClient()
  const chave = ["cadastro", "produto", String(produtoId), "lojas"]
  const lojas = useQuery({
    queryKey: chave,
    queryFn: () => apiJson<LojaDoProduto[]>(`/web/produtos/${produtoId}/lojas`),
  })
  const mudar = useMutation({
    mutationFn: ({ loja, ativo }: { loja: LojaDoProduto; ativo: boolean }) =>
      apiJson<LojaDoProduto>(`/web/produtos/${produtoId}/lojas/${loja.loja_id}`, { method: "PUT", json: { ativo } }),
    onSuccess: async (r) => {
      toast.success(r.ativo ? `Produto ativado em ${nomeLoja(r)}.` : `Produto desativado em ${nomeLoja(r)}.`)
      queryClient.setQueryData<LojaDoProduto[]>(chave, (atual) => atual?.map((l) => (l.loja_id === r.loja_id ? r : l)))
      await queryClient.invalidateQueries({ queryKey: ["cadastro", "produtos"] })
    },
  })

  return (
    <section aria-labelledby={`lojas-${produtoId}`} className="flex flex-col gap-4">
      <div>
        <h2 id={`lojas-${produtoId}`} className="flex items-center gap-2 text-[22px]">
          <Store className="size-5" aria-hidden="true" />
          Lojas da central
        </h2>
        <p className="mt-1 max-w-2xl text-muted-foreground">
          Onde o produto é contado, previsto e enviado. Muda na hora, sem precisar salvar o produto.
        </p>
      </div>
      {!produtoAtivo && (
        <Alert variant="aviso">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>O produto está inativo.</AlertTitle>
          <AlertDescription>Enquanto estiver inativo, ele não aparece em nenhuma loja, mesmo nas ativas abaixo.</AlertDescription>
        </Alert>
      )}
      {mudar.isError && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A loja não foi alterada. {mudar.error.message}</AlertTitle>
          <AlertDescription>Tente de novo.</AlertDescription>
        </Alert>
      )}
      {lojas.isError ? (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{lojas.error.message}</AlertTitle>
          <AlertDescription>Recarregue a página.</AlertDescription>
        </Alert>
      ) : lojas.isPending ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : lojas.data.length === 0 ? (
        <p className="rounded-lg bg-surface p-6">A sua central ainda não tem lojas.</p>
      ) : (
        <Table aria-label="Lojas do produto">
          <TableHeader>
            <TableRow>
              <TableHead>Loja</TableHead>
              <TableHead>Situação do produto</TableHead>
              <TableHead className="text-right">Ação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lojas.data.map((l) => {
              const ocupada = mudar.isPending && mudar.variables?.loja.loja_id === l.loja_id
              return (
                <TableRow key={l.loja_id}>
                  <TableCell>
                    {nomeLoja(l)}
                    {!l.loja_ativa && <span className="text-muted-foreground"> (loja inativa)</span>}
                  </TableCell>
                  <TableCell>
                    <Situacao loja={l} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="secondary"
                      carregando={ocupada}
                      textoCarregando="Salvando…"
                      disabled={mudar.isPending && !ocupada}
                      aria-label={`${l.ativo ? "Desativar nesta loja" : "Ativar nesta loja"}: ${nomeLoja(l)}`}
                      onClick={() => mudar.mutate({ loja: l, ativo: !l.ativo })}
                    >
                      {l.ativo ? "Desativar nesta loja" : "Ativar nesta loja"}
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </section>
  )
}
