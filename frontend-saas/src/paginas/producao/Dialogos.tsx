/*
 * Diálogos da ordem de produção (skill Frescor).
 *
 * - DialogoAjuste: quantidade final de uma loja, com a unidade fixa ao lado
 *   do campo (inputmode decimal) e o motivo opcional. Valida no navegador
 *   com as regras do backend (quantidade.ts) e mostra o erro abaixo do campo;
 *   erro da API (ex.: a ordem foi aprovada nesse meio tempo) num alerta.
 * - DialogoConfirmar: para o que não se desfaz (aprovar, apagar, gerar de
 *   novo perdendo ajustes), com o verbo no botão.
 */
import { useId, useState } from "react"
import { CircleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { Unidade } from "@/lib/api/tipos"
import { formatarQuantidade } from "@/lib/formato"
import { lerQuantidade } from "./quantidade"

export interface AlvoAjuste {
  linhaId: number
  produto: string
  loja: string
  unidade: Unidade
  sugerida: string | null
  final: string | null
  motivo: string | null
}

const DICA_ORDEM = "Confira a ordem e tente de novo."

function paraCampo(valor: string | null): string {
  if (valor === null) return ""
  return String(Number(valor)).replace(".", ",")
}

export function DialogoAjuste({
  alvo,
  salvando,
  erroApi,
  dica = DICA_ORDEM,
  aoFechar,
  aoSalvar,
}: {
  alvo: AlvoAjuste | null
  salvando: boolean
  erroApi: string | null
  /** O que fazer quando a API recusa (padrão: conferir a ordem). */
  dica?: string
  aoFechar: () => void
  aoSalvar: (quantidade: string, motivo: string) => void
}) {
  return (
    <Dialog open={alvo !== null} onOpenChange={(aberto) => !aberto && aoFechar()}>
      <DialogContent>
        {/* `key` zera o formulário a cada linha aberta. */}
        {alvo && <FormularioAjuste key={alvo.linhaId} alvo={alvo} salvando={salvando} erroApi={erroApi} dica={dica} aoFechar={aoFechar} aoSalvar={aoSalvar} />}
      </DialogContent>
    </Dialog>
  )
}

function FormularioAjuste({
  alvo,
  salvando,
  erroApi,
  dica,
  aoFechar,
  aoSalvar,
}: {
  alvo: AlvoAjuste
  salvando: boolean
  erroApi: string | null
  dica: string
  aoFechar: () => void
  aoSalvar: (quantidade: string, motivo: string) => void
}) {
  const id = useId()
  const [quantidade, setQuantidade] = useState(paraCampo(alvo.final))
  const [motivo, setMotivo] = useState(alvo.motivo ?? "")
  const [erro, setErro] = useState<string | null>(null)
  const unidade = alvo.unidade === "KG" ? "kg" : "un"

  function salvar(evento: React.FormEvent) {
    evento.preventDefault()
    const lida = lerQuantidade(quantidade, alvo.unidade)
    if (!lida.ok) {
      setErro(lida.erro)
      return
    }
    setErro(null)
    aoSalvar(lida.valor, motivo.trim())
  }

  return (
    <form onSubmit={salvar} noValidate className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>Ajustar {alvo.produto}</DialogTitle>
        <DialogDescription>
          {alvo.loja} · sugestão do sistema:{" "}
          {alvo.sugerida === null ? "sem sugestão" : formatarQuantidade(alvo.sugerida, alvo.unidade)}
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-qtd`}>Quantidade para a loja</Label>
        <div className="flex items-center gap-2">
          <Input
            id={`${id}-qtd`}
            inputMode="decimal"
            autoComplete="off"
            value={quantidade}
            onChange={(e) => setQuantidade(e.target.value)}
            aria-invalid={erro !== null}
            aria-describedby={erro ? `${id}-erro` : undefined}
            className="max-w-40 text-right numero"
            autoFocus
          />
          <span className="font-semibold text-muted-foreground">{unidade}</span>
        </div>
        {erro && (
          <p id={`${id}-erro`} className="flex items-center gap-1 text-sm text-error">
            <CircleAlert className="size-4" aria-hidden="true" />
            {erro}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-motivo`}>Motivo (opcional)</Label>
        <Textarea
          id={`${id}-motivo`}
          value={motivo}
          maxLength={255}
          rows={2}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Ex.: festa no bairro, loja pediu mais"
        />
      </div>
      {erroApi && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A quantidade não foi salva. {erroApi}</AlertTitle>
          <AlertDescription>{dica}</AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>
          Cancelar
        </Button>
        <Button type="submit" carregando={salvando} textoCarregando="Salvando…">
          Salvar quantidade
        </Button>
      </DialogFooter>
    </form>
  )
}

export function DialogoConfirmar({
  aberto,
  titulo,
  descricao,
  verbo,
  verboCarregando,
  perigo = false,
  carregando,
  erroApi,
  dica = DICA_ORDEM,
  bloqueio,
  aoFechar,
  aoConfirmar,
}: {
  aberto: boolean
  titulo: string
  descricao: React.ReactNode
  verbo: string
  verboCarregando: string
  perigo?: boolean
  carregando: boolean
  erroApi: string | null
  /** O que fazer quando a API recusa (padrão: conferir a ordem). */
  dica?: string
  /** Quando preenchido, explica por que a ação não pode ser feita agora (sem o botão de confirmar). */
  bloqueio?: string | null
  aoFechar: () => void
  aoConfirmar: () => void
}) {
  return (
    <Dialog open={aberto} onOpenChange={(a) => !a && aoFechar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription asChild>
            <div>{descricao}</div>
          </DialogDescription>
        </DialogHeader>
        {bloqueio && (
          <Alert variant="aviso">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{bloqueio}</AlertTitle>
          </Alert>
        )}
        {erroApi && (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{erroApi}</AlertTitle>
            <AlertDescription>{dica}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={aoFechar}>
            {bloqueio ? "Voltar" : "Cancelar"}
          </Button>
          {!bloqueio && (
            <Button
              type="button"
              variant={perigo ? "destructive" : "default"}
              carregando={carregando}
              textoCarregando={verboCarregando}
              onClick={aoConfirmar}
            >
              {verbo}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
