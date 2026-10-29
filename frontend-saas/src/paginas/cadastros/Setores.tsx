/*
 * Setores de produção da central (Fase 6 / C1 e C4; D67, D102): cada setor
 * é uma bancada (pães, bolos, salgados) e vira uma folha na impressão da
 * ordem aprovada.
 *
 * - "Novo setor" (ação principal) e "Renomear" abrem um diálogo com o nome.
 * - "Subir"/"Descer" mudam a ordem das folhas: a tela renumera os setores
 *   (1, 2, 3...) e grava só os que mudaram de posição.
 * - "Desativar" tira o setor da escolha; os produtos dele saem na folha
 *   "Sem setor" até ele ser reativado. Não há apagar.
 */
import { useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { cn } from "cn"
import { ArrowDown, ArrowUp, CircleAlert, CircleCheck, CircleSlash, Pencil, Plus } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiJson } from "@/lib/api/cliente"
import type { SetorProducao } from "@/lib/api/tipos"

const PILL = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap"
const CHAVE = ["cadastro", "setores"]

type Edicao = { tipo: "novo" } | { tipo: "renomear"; setor: SetorProducao }

export function Setores() {
  const queryClient = useQueryClient()
  const [edicao, setEdicao] = useState<Edicao | null>(null)
  const setores = useQuery({ queryKey: CHAVE, queryFn: () => apiJson<SetorProducao[]>("/producao/setores") })

  async function atualizar() {
    await queryClient.invalidateQueries({ queryKey: CHAVE })
    await queryClient.invalidateQueries({ queryKey: ["cadastro", "produtos"] })
  }

  const salvarNome = useMutation({
    mutationFn: ({ edicao, nome }: { edicao: Edicao; nome: string }) =>
      edicao.tipo === "novo"
        ? apiJson<SetorProducao>("/producao/setores", { method: "POST", json: { nome } })
        : apiJson<SetorProducao>(`/producao/setores/${edicao.setor.id}`, { method: "PATCH", json: { nome } }),
    onSuccess: async (s, { edicao }) => {
      toast.success(edicao.tipo === "novo" ? `Setor “${s.nome}” criado.` : `Setor renomeado para “${s.nome}”.`)
      setEdicao(null)
      await atualizar()
    },
  })

  const situacao = useMutation({
    mutationFn: (s: SetorProducao) =>
      apiJson<SetorProducao>(`/producao/setores/${s.id}`, { method: "PATCH", json: { ativo: !s.ativo } }),
    onSuccess: async (s) => {
      toast.success(s.ativo ? `Setor “${s.nome}” reativado.` : `Setor “${s.nome}” desativado.`)
      await atualizar()
    },
  })

  const ordem = useMutation({
    mutationFn: async (novaOrdem: SetorProducao[]) => {
      for (const [i, s] of novaOrdem.entries()) {
        if (s.ordem !== i + 1) {
          await apiJson<SetorProducao>(`/producao/setores/${s.id}`, { method: "PATCH", json: { ordem: i + 1 } })
        }
      }
    },
    onSettled: atualizar,
  })

  function mover(indice: number, direcao: -1 | 1) {
    const lista = [...(setores.data ?? [])]
    const alvo = indice + direcao
    if (alvo < 0 || alvo >= lista.length) return
    ;[lista[indice], lista[alvo]] = [lista[alvo], lista[indice]]
    ordem.mutate(lista)
  }

  const erroAcao = situacao.error ?? ordem.error
  const ocupado = situacao.isPending || ordem.isPending

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="max-w-2xl text-muted-foreground">
          Cada setor sai numa folha própria na impressão da ordem de produção aprovada, nesta ordem. Produto sem setor
          (ou de setor desativado) sai na folha “Sem setor”.
        </p>
        <Button onClick={() => setEdicao({ tipo: "novo" })}>
          <Plus aria-hidden="true" />
          Novo setor
        </Button>
      </div>

      {erroAcao && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>O setor não foi alterado. {erroAcao.message}</AlertTitle>
          <AlertDescription>Tente de novo.</AlertDescription>
        </Alert>
      )}

      <div aria-live="polite">
        {setores.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{setores.error.message}</AlertTitle>
            <AlertDescription>Recarregue a página.</AlertDescription>
          </Alert>
        ) : setores.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : setores.data.length === 0 ? (
          <div className="rounded-lg bg-surface p-6">
            <p>Nenhum setor cadastrado ainda.</p>
            <p className="mt-1 text-muted-foreground">
              Sem setores, a ordem aprovada sai numa folha só. Crie um setor para cada bancada da produção.
            </p>
          </div>
        ) : (
          <Table aria-label="Setores de produção">
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">Folha</TableHead>
                <TableHead>Setor</TableHead>
                <TableHead>Situação</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {setores.data.map((s, i) => (
                <TableRow key={s.id}>
                  <TableCell className="text-right numero">{i + 1}</TableCell>
                  <TableCell className="font-semibold">{s.nome}</TableCell>
                  <TableCell>
                    {s.ativo ? (
                      <span className={cn(PILL, "bg-success-bg text-success")}>
                        <CircleCheck className="size-4" aria-hidden="true" />
                        Ativo
                      </span>
                    ) : (
                      <span className={cn(PILL, "bg-surface text-foreground")}>
                        <CircleSlash className="size-4" aria-hidden="true" />
                        Desativado
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button
                        variant="ghost"
                        disabled={i === 0 || ocupado}
                        aria-label={`Subir: ${s.nome}`}
                        onClick={() => mover(i, -1)}
                      >
                        <ArrowUp aria-hidden="true" />
                        Subir
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={i === setores.data.length - 1 || ocupado}
                        aria-label={`Descer: ${s.nome}`}
                        onClick={() => mover(i, 1)}
                      >
                        <ArrowDown aria-hidden="true" />
                        Descer
                      </Button>
                      <Button variant="ghost" aria-label={`Renomear: ${s.nome}`} onClick={() => setEdicao({ tipo: "renomear", setor: s })}>
                        <Pencil aria-hidden="true" />
                        Renomear
                      </Button>
                      <Button
                        variant="secondary"
                        disabled={ocupado}
                        aria-label={`${s.ativo ? "Desativar" : "Reativar"}: ${s.nome}`}
                        onClick={() => situacao.mutate(s)}
                      >
                        {s.ativo ? "Desativar" : "Reativar"}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <DialogoNome
        edicao={edicao}
        salvando={salvarNome.isPending}
        erroApi={salvarNome.isError ? salvarNome.error.message : null}
        aoFechar={() => {
          setEdicao(null)
          salvarNome.reset()
        }}
        aoSalvar={(nome) => edicao && salvarNome.mutate({ edicao, nome })}
      />
    </div>
  )
}

function DialogoNome({
  edicao,
  salvando,
  erroApi,
  aoFechar,
  aoSalvar,
}: {
  edicao: Edicao | null
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoSalvar: (nome: string) => void
}) {
  return (
    <Dialog open={edicao !== null} onOpenChange={(a) => !a && aoFechar()}>
      <DialogContent>
        {edicao && (
          <FormularioNome
            key={edicao.tipo === "novo" ? "novo" : edicao.setor.id}
            edicao={edicao}
            salvando={salvando}
            erroApi={erroApi}
            aoFechar={aoFechar}
            aoSalvar={aoSalvar}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function FormularioNome({
  edicao,
  salvando,
  erroApi,
  aoFechar,
  aoSalvar,
}: {
  edicao: Edicao
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoSalvar: (nome: string) => void
}) {
  const id = useId()
  const [nome, setNome] = useState(edicao.tipo === "renomear" ? edicao.setor.nome : "")
  const [erro, setErro] = useState<string | null>(null)

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    if (!nome.trim()) {
      setErro("Informe o nome do setor.")
      return
    }
    setErro(null)
    aoSalvar(nome.trim())
  }

  return (
    <form onSubmit={enviar} noValidate className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{edicao.tipo === "novo" ? "Novo setor de produção" : `Renomear “${edicao.setor.nome}”`}</DialogTitle>
        <DialogDescription>Use o nome que a equipe conhece, por exemplo “Pães” ou “Bolos e doces”.</DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-nome`}>Nome do setor</Label>
        <Input
          id={`${id}-nome`}
          value={nome}
          maxLength={80}
          onChange={(e) => setNome(e.target.value)}
          aria-invalid={erro !== null}
          aria-describedby={erro ? `${id}-erro` : undefined}
        />
        {erro && (
          <p id={`${id}-erro`} className="flex items-center gap-1 text-sm text-error">
            <CircleAlert className="size-4" aria-hidden="true" />
            {erro}
          </p>
        )}
      </div>
      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>O setor não foi salvo. {erroApi}</AlertTitle>
          <AlertDescription>Escolha outro nome e tente de novo.</AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>
          Cancelar
        </Button>
        <Button type="submit" carregando={salvando} textoCarregando="Salvando…">
          {edicao.tipo === "novo" ? "Criar setor" : "Salvar nome"}
        </Button>
      </DialogFooter>
    </form>
  )
}
