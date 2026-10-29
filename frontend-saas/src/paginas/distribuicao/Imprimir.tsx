/*
 * Impressão do romaneio aprovado (D81, E8): o gestor escolhe as lojas
 * ("Todas as lojas" marcado por padrão) e o PDF abre numa aba nova: folha
 * de carga (soma só as lojas escolhidas) e uma folha por loja.
 *
 * Como na ordem de produção: o PDF exige o token, então a tela baixa o
 * arquivo e abre o endereço local dele; a aba abre já no clique, para o
 * navegador não bloquear como pop-up; se bloquear, o PDF é baixado.
 */
import { useId, useState } from "react"
import { CircleAlert, FileText } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { apiFetch } from "@/lib/api/cliente"
import type { EntregaRomaneio } from "@/lib/api/tipos"
import { formatarData } from "@/lib/formato"
import { nomeCom } from "./situacao"

const CAIXA =
  "size-5 shrink-0 accent-[var(--fr-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
const ESCOLHA_VAZIA = "Escolha pelo menos uma loja."

function caminhoPdf(romaneioId: number, lojas: number[] | null): string {
  const base = `/distribuicao/romaneios/${romaneioId}/pdf`
  return lojas === null ? base : `${base}?lojas=${lojas.join(",")}`
}

export function DialogoImprimirRomaneio({
  aberto,
  romaneioId,
  dataEntrega,
  entregas,
  aoFechar,
}: {
  aberto: boolean
  romaneioId: number
  dataEntrega: string
  entregas: EntregaRomaneio[]
  aoFechar: () => void
}) {
  return (
    <Dialog open={aberto} onOpenChange={(a) => !a && aoFechar()}>
      <DialogContent>
        {aberto && (
          <Formulario romaneioId={romaneioId} dataEntrega={dataEntrega} entregas={entregas} aoFechar={aoFechar} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function Formulario({
  romaneioId,
  dataEntrega,
  entregas,
  aoFechar,
}: {
  romaneioId: number
  dataEntrega: string
  entregas: EntregaRomaneio[]
  aoFechar: () => void
}) {
  const id = useId()
  const [todas, setTodas] = useState(true)
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())
  const [gerando, setGerando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  function alternar(lojaId: number) {
    setTodas(false)
    setMarcadas((atual) => {
      const nova = new Set(atual)
      if (nova.has(lojaId)) nova.delete(lojaId)
      else nova.add(lojaId)
      return nova
    })
  }

  async function abrir() {
    const escolhidas = todas ? null : entregas.map((e) => e.loja.id).filter((l) => marcadas.has(l))
    if (escolhidas !== null && escolhidas.length === 0) {
      setErro(ESCOLHA_VAZIA)
      return
    }
    setErro(null)
    setGerando(true)
    // Aberta já no clique: depois do download, o navegador trataria como pop-up.
    const aba = window.open("", "_blank")
    try {
      const resposta = await apiFetch(caminhoPdf(romaneioId, escolhidas))
      const url = URL.createObjectURL(await resposta.blob())
      if (aba) {
        aba.location.href = url
      } else {
        const link = document.createElement("a")
        link.href = url
        link.download = `romaneio-${dataEntrega}.pdf`
        link.click()
      }
      aoFechar()
    } catch (e) {
      aba?.close()
      setErro(e instanceof Error ? e.message : String(e))
    } finally {
      setGerando(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>Imprimir o romaneio de {formatarData(dataEntrega)}</DialogTitle>
        <DialogDescription>
          Sai a folha de carga, com o total de cada produto, e uma folha por loja, para ir junto com a entrega.
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
          Todas as lojas
        </label>
        {entregas.map((e) => (
          <label key={e.loja.id} htmlFor={`${id}-${e.loja.id}`} className="flex min-h-11 items-center gap-3 pl-6">
            <input
              id={`${id}-${e.loja.id}`}
              type="checkbox"
              className={CAIXA}
              checked={todas || marcadas.has(e.loja.id)}
              onChange={() => alternar(e.loja.id)}
            />
            {nomeCom(e.loja)}
          </label>
        ))}
      </fieldset>
      {erro && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{erro}</AlertTitle>
          {erro !== ESCOLHA_VAZIA && <AlertDescription>Confira a escolha e tente de novo.</AlertDescription>}
        </Alert>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={aoFechar}>
          Cancelar
        </Button>
        <Button type="button" onClick={abrir} carregando={gerando} textoCarregando="Gerando PDF…">
          <FileText aria-hidden="true" />
          Abrir PDF
        </Button>
      </DialogFooter>
    </div>
  )
}
