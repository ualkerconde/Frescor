/*
 * Cadastro da central (Fase 6 / C1 e C4, D103): o gestor muda o nome e o
 * prazo de entrega da própria central. Seção e situação aparecem só para
 * leitura (desativar a própria central bloquearia o acesso, D4; trocar a
 * seção é trabalho futuro, D14). O prazo novo vale para as ordens geradas
 * depois: as ordens já geradas guardam a data de entrega.
 */
import { useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleAlert } from "lucide-react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { apiJson } from "@/lib/api/cliente"
import type { CentralCadastro } from "@/lib/api/tipos"
import { contar } from "@/lib/formato"

const SECOES: Record<CentralCadastro["secao"], string> = {
  padaria: "Padaria",
  acougue: "Açougue",
  hortifruti: "Hortifrúti",
}

function rotuloPrazo(dias: number): string {
  if (dias === 0) return "No mesmo dia da produção"
  if (dias === 1) return "No dia seguinte (1 dia)"
  return `${dias} dias depois`
}

export function Central() {
  const queryClient = useQueryClient()
  const central = useQuery({ queryKey: ["cadastro", "central"], queryFn: () => apiJson<CentralCadastro>("/web/central") })
  const salvar = useMutation({
    mutationFn: (corpo: { nome: string; prazo_entrega_dias: number }) =>
      apiJson<CentralCadastro>("/web/central", { method: "PATCH", json: corpo }),
    onSuccess: async (c) => {
      toast.success("Central salva. O prazo vale para as próximas ordens de produção.")
      queryClient.setQueryData(["cadastro", "central"], c)
      // O nome da central aparece no cabeçalho (GET /web/me).
      await queryClient.invalidateQueries({ queryKey: ["me"] })
    },
  })

  if (central.isError) {
    return (
      <Alert variant="erro">
        <CircleAlert aria-hidden="true" />
        <AlertTitle>{central.error.message}</AlertTitle>
        <AlertDescription>Recarregue a página.</AlertDescription>
      </Alert>
    )
  }
  if (central.isPending) return <p className="text-muted-foreground">Carregando…</p>
  return (
    <FormularioCentral
      key={JSON.stringify(central.data)}
      central={central.data}
      salvando={salvar.isPending}
      erroApi={salvar.isError ? salvar.error.message : null}
      aoSalvar={(corpo) => salvar.mutate(corpo)}
    />
  )
}

function FormularioCentral({
  central,
  salvando,
  erroApi,
  aoSalvar,
}: {
  central: CentralCadastro
  salvando: boolean
  erroApi: string | null
  aoSalvar: (corpo: { nome: string; prazo_entrega_dias: number }) => void
}) {
  const id = useId()
  const [nome, setNome] = useState(central.nome)
  const [prazo, setPrazo] = useState(String(central.prazo_entrega_dias))
  const [erro, setErro] = useState<string | null>(null)

  function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    if (!nome.trim()) {
      setErro("Informe o nome da central.")
      return
    }
    setErro(null)
    aoSalvar({ nome: nome.trim(), prazo_entrega_dias: Number(prazo) })
  }

  return (
    <form onSubmit={enviar} noValidate className="flex max-w-3xl flex-col gap-6">
      <div className="grid gap-4 rounded-lg border border-line bg-card p-6 md:grid-cols-2">
        <div className="flex flex-col gap-2 md:col-span-2">
          <Label htmlFor={`${id}-nome`}>Nome da central</Label>
          <Input
            id={`${id}-nome`}
            value={nome}
            maxLength={255}
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
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-prazo`}>Entrega nas lojas</Label>
          <Select value={prazo} onValueChange={setPrazo}>
            <SelectTrigger id={`${id}-prazo`} className="w-full" aria-describedby={`${id}-prazo-ajuda`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[0, 1, 2, 3, 4, 5, 6, 7].map((d) => (
                <SelectItem key={d} value={String(d)}>
                  {rotuloPrazo(d)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p id={`${id}-prazo-ajuda`} className="text-sm text-muted-foreground">
            Quantos dias depois da produção a mercadoria chega à loja. Vale para as próximas ordens.
          </p>
        </div>
        <dl className="grid content-start gap-3">
          <div>
            <dt className="text-sm font-semibold">Seção</dt>
            <dd>{SECOES[central.secao]}</dd>
          </div>
          <div>
            <dt className="text-sm font-semibold">Lojas atendidas</dt>
            <dd>{contar(central.lojas, "loja", "lojas")}</dd>
          </div>
          <div>
            <dt className="text-sm font-semibold">Situação</dt>
            <dd>{central.ativa ? "Ativa" : "Inativa"}</dd>
          </div>
        </dl>
        <p className="text-sm text-muted-foreground md:col-span-2">
          Seção, lojas e situação da central são definidas pelo administrador da rede.
        </p>
      </div>

      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A central não foi salva. {erroApi}</AlertTitle>
          <AlertDescription>Corrija e salve de novo.</AlertDescription>
        </Alert>
      )}

      <div>
        <Button type="submit" carregando={salvando} textoCarregando="Salvando…">
          Salvar central
        </Button>
      </div>
    </form>
  )
}
