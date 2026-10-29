/*
 * "Registrar produção" (D69): quanto foi produzido de cada produto da ordem
 * aprovada (no distribuído, quanto há para mandar). O campo vem com o
 * registrado ou, na primeira vez, com o planejado. Valida no navegador com
 * as regras do backend (quantidade.ts) e mostra o erro abaixo do campo.
 *
 * Abaixo do planejado, o romaneio rateia entre as lojas (D70); acima, a
 * sobra fica na central. Com o romaneio em rascunho, corrigir a produção
 * NÃO refaz o rascunho (D87): a tela avisa e oferece "Gerar de novo".
 */
import { useId, useState } from "react"
import { CircleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { ItemProducao } from "@/lib/api/tipos"
import { formatarData, formatarQuantidade } from "@/lib/formato"
import { lerQuantidade } from "../producao/quantidade"
import { nomeCom } from "./situacao"

function paraCampo(valor: string): string {
  return String(Number(valor)).replace(".", ",")
}

export function DialogoProducao({
  aberto,
  dataProducao,
  itens,
  salvando,
  erroApi,
  aoFechar,
  aoSalvar,
}: {
  aberto: boolean
  dataProducao: string
  itens: ItemProducao[]
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoSalvar: (quantidades: { item_id: number; quantidade: string }[]) => void
}) {
  return (
    <Dialog open={aberto} onOpenChange={(a) => !a && aoFechar()}>
      <DialogContent className="sm:max-w-xl">
        {aberto && (
          <Formulario
            dataProducao={dataProducao}
            itens={itens}
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

function Formulario({
  dataProducao,
  itens,
  salvando,
  erroApi,
  aoFechar,
  aoSalvar,
}: {
  dataProducao: string
  itens: ItemProducao[]
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoSalvar: (quantidades: { item_id: number; quantidade: string }[]) => void
}) {
  const id = useId()
  const [valores, setValores] = useState<Record<number, string>>(() =>
    Object.fromEntries(itens.map((i) => [i.item_id, paraCampo(i.produzido ?? i.planejado)])),
  )
  const [erros, setErros] = useState<Record<number, string>>({})

  function salvar(evento: React.FormEvent) {
    evento.preventDefault()
    const novosErros: Record<number, string> = {}
    const quantidades: { item_id: number; quantidade: string }[] = []
    for (const item of itens) {
      const lida = lerQuantidade(valores[item.item_id] ?? "", item.unidade)
      if (lida.ok) quantidades.push({ item_id: item.item_id, quantidade: lida.valor })
      else novosErros[item.item_id] = lida.erro
    }
    setErros(novosErros)
    if (Object.keys(novosErros).length === 0) aoSalvar(quantidades)
  }

  return (
    <form onSubmit={salvar} noValidate className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>Registrar a produção de {formatarData(dataProducao)}</DialogTitle>
        <DialogDescription>
          Informe quanto foi produzido de cada produto (nos distribuídos, quanto há para mandar). Se faltar, o romaneio
          divide entre as lojas na proporção do que cada uma pediu.
        </DialogDescription>
      </DialogHeader>
      <div className="flex max-h-[50vh] flex-col gap-4 overflow-y-auto pr-1">
        {itens.map((item) => {
          const campo = `${id}-${item.item_id}`
          const erro = erros[item.item_id]
          return (
            <div key={item.item_id} className="flex flex-col gap-1">
              <Label htmlFor={campo}>{nomeCom(item.produto)}</Label>
              <p id={`${campo}-planejado`} className="text-sm text-muted-foreground">
                Planejado na ordem: {formatarQuantidade(item.planejado, item.unidade)}
              </p>
              <div className="flex items-center gap-2">
                <Input
                  id={campo}
                  inputMode="decimal"
                  autoComplete="off"
                  value={valores[item.item_id] ?? ""}
                  onChange={(e) => setValores((v) => ({ ...v, [item.item_id]: e.target.value }))}
                  aria-invalid={erro !== undefined}
                  aria-describedby={erro ? `${campo}-planejado ${campo}-erro` : `${campo}-planejado`}
                  className="max-w-40 text-right numero"
                />
                <span className="font-semibold text-muted-foreground">{item.unidade === "KG" ? "kg" : "un"}</span>
              </div>
              {erro && (
                <p id={`${campo}-erro`} className="flex items-center gap-1 text-sm text-error">
                  <CircleAlert className="size-4" aria-hidden="true" />
                  {erro}
                </p>
              )}
            </div>
          )
        })}
      </div>
      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A produção não foi registrada. {erroApi}</AlertTitle>
          <AlertDescription>Confira as quantidades e tente de novo.</AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>
          Cancelar
        </Button>
        <Button type="submit" carregando={salvando} textoCarregando="Registrando…">
          Registrar produção
        </Button>
      </DialogFooter>
    </form>
  )
}
