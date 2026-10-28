/*
 * "Registrar saída" (D76): o gestor escolhe as lojas cuja entrega saiu da
 * central. "Todas as que faltam" vem marcado; desmarcando, escolhe uma ou
 * várias. A saída não se desfaz: por isso o diálogo, com o verbo no botão
 * (skill: confirmação só para o que não se desfaz). Depois dela, a loja vê
 * a entrega no app para confirmar o recebimento.
 */
import { useId, useState } from "react"
import { CircleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { EntregaRomaneio } from "@/lib/api/tipos"
import { contar } from "@/lib/formato"
import { nomeCom } from "./situacao"

const CAIXA =
  "size-5 shrink-0 accent-[var(--fr-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"

const ESCOLHA_VAZIA = "Escolha pelo menos uma loja."

export function DialogoSaida({
  aberto,
  pendentes,
  salvando,
  erroApi,
  aoFechar,
  aoConfirmar,
}: {
  aberto: boolean
  /** Entregas aguardando saída, na ordem do código da loja. */
  pendentes: EntregaRomaneio[]
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  /** null = todas as que faltam. */
  aoConfirmar: (entregaIds: number[] | null) => void
}) {
  return (
    <Dialog open={aberto} onOpenChange={(a) => !a && aoFechar()}>
      <DialogContent>
        {aberto && (
          <Formulario
            pendentes={pendentes}
            salvando={salvando}
            erroApi={erroApi}
            aoFechar={aoFechar}
            aoConfirmar={aoConfirmar}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function Formulario({
  pendentes,
  salvando,
  erroApi,
  aoFechar,
  aoConfirmar,
}: {
  pendentes: EntregaRomaneio[]
  salvando: boolean
  erroApi: string | null
  aoFechar: () => void
  aoConfirmar: (entregaIds: number[] | null) => void
}) {
  const id = useId()
  const [todas, setTodas] = useState(true)
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())
  const [erro, setErro] = useState<string | null>(null)

  function alternar(entregaId: number) {
    setTodas(false)
    setMarcadas((atual) => {
      const nova = new Set(atual)
      if (nova.has(entregaId)) nova.delete(entregaId)
      else nova.add(entregaId)
      return nova
    })
  }

  function confirmar() {
    if (todas) {
      setErro(null)
      aoConfirmar(null)
      return
    }
    const escolhidas = pendentes.map((e) => e.id).filter((i) => marcadas.has(i))
    if (escolhidas.length === 0) {
      setErro(ESCOLHA_VAZIA)
      return
    }
    setErro(null)
    aoConfirmar(escolhidas)
  }

  return (
    <div className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>Registrar a saída das entregas?</DialogTitle>
        <DialogDescription>
          A saída não se desfaz. Depois dela, a loja vê a entrega no app e confirma o que recebeu.
        </DialogDescription>
      </DialogHeader>
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-2 text-sm font-semibold">Lojas</legend>
        <label htmlFor={`${id}-todas`} className="flex min-h-11 items-center gap-3 font-semibold">
          <input
            id={`${id}-todas`}
            type="checkbox"
            className={CAIXA}
            checked={todas}
            onChange={(e) => {
              setTodas(e.target.checked)
              if (e.target.checked) setMarcadas(new Set())
            }}
          />
          Todas as que faltam ({contar(pendentes.length, "loja", "lojas")})
        </label>
        {pendentes.map((e) => (
          <label key={e.id} htmlFor={`${id}-${e.id}`} className="flex min-h-11 items-center gap-3 pl-6">
            <input
              id={`${id}-${e.id}`}
              type="checkbox"
              className={CAIXA}
              checked={todas || marcadas.has(e.id)}
              onChange={() => alternar(e.id)}
            />
            {nomeCom(e.loja)}
          </label>
        ))}
      </fieldset>
      {(erro || erroApi) && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{erro ?? `A saída não foi registrada. ${erroApi}`}</AlertTitle>
          {erro !== ESCOLHA_VAZIA && <AlertDescription>Confira o romaneio e tente de novo.</AlertDescription>}
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>
          Cancelar
        </Button>
        <Button type="button" onClick={confirmar} carregando={salvando} textoCarregando="Registrando…">
          Registrar saída
        </Button>
      </DialogFooter>
    </div>
  )
}
