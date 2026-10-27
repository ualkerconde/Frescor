/*
 * Impressão da ordem aprovada (N9b, D67): o gestor escolhe os setores
 * ("Todos os setores" marcado por padrão; ou um ou vários, mais "Sem setor")
 * e o PDF abre numa aba nova, uma folha por setor (gerado no backend).
 *
 * O PDF exige o token: a tela baixa o arquivo (apiFetch) e abre o endereço
 * local dele. A aba é aberta já no clique (antes do download), para o
 * navegador não bloquear como pop-up; se mesmo assim for bloqueada, o PDF
 * é baixado como arquivo.
 */
import { useId, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CircleAlert, FileText } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { apiFetch, apiJson } from "@/lib/api/cliente"
import type { SetorProducao } from "@/lib/api/tipos"
import { formatarData } from "@/lib/formato"

/** Código do backend para "produtos sem setor". */
const SEM_SETOR = "sem"

const CAIXA =
  "size-5 shrink-0 accent-[var(--fr-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"

function caminhoPdf(ordemId: number, escolhidos: string[] | null): string {
  const base = `/producao/ordens/${ordemId}/pdf`
  return escolhidos === null ? base : `${base}?setores=${escolhidos.join(",")}`
}

export function DialogoImprimir({
  aberto,
  ordemId,
  dataProducao,
  aoFechar,
}: {
  aberto: boolean
  ordemId: number
  dataProducao: string
  aoFechar: () => void
}) {
  const setores = useQuery({
    queryKey: ["producao", "setores"],
    queryFn: () => apiJson<SetorProducao[]>("/producao/setores"),
    enabled: aberto,
  })
  return (
    <Dialog open={aberto} onOpenChange={(a) => !a && aoFechar()}>
      <DialogContent>
        {aberto && (
          <Formulario
            ordemId={ordemId}
            dataProducao={dataProducao}
            setores={(setores.data ?? []).filter((s) => s.ativo)}
            carregandoSetores={setores.isPending}
            erroSetores={setores.isError ? setores.error.message : null}
            aoFechar={aoFechar}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function Formulario({
  ordemId,
  dataProducao,
  setores,
  carregandoSetores,
  erroSetores,
  aoFechar,
}: {
  ordemId: number
  dataProducao: string
  setores: SetorProducao[]
  carregandoSetores: boolean
  erroSetores: string | null
  aoFechar: () => void
}) {
  const id = useId()
  const [todos, setTodos] = useState(true)
  const [marcados, setMarcados] = useState<Set<string>>(new Set())
  const [gerando, setGerando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const opcoes = [...setores.map((s) => ({ chave: String(s.id), nome: s.nome })), { chave: SEM_SETOR, nome: "Sem setor" }]

  function alternar(chave: string) {
    setTodos(false)
    setMarcados((atual) => {
      const novo = new Set(atual)
      if (novo.has(chave)) novo.delete(chave)
      else novo.add(chave)
      return novo
    })
  }

  async function abrir() {
    const escolhidos = todos ? null : opcoes.map((o) => o.chave).filter((c) => marcados.has(c))
    if (escolhidos !== null && escolhidos.length === 0) {
      setErro("Escolha pelo menos um setor.")
      return
    }
    setErro(null)
    setGerando(true)
    // Aberta já no clique: depois do download, o navegador trataria como pop-up.
    const aba = window.open("", "_blank")
    try {
      const resposta = await apiFetch(caminhoPdf(ordemId, escolhidos))
      const url = URL.createObjectURL(await resposta.blob())
      if (aba) {
        aba.location.href = url
      } else {
        const link = document.createElement("a")
        link.href = url
        link.download = `ordem-producao-${dataProducao}.pdf`
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
        <DialogTitle>Imprimir a ordem de {formatarData(dataProducao)}</DialogTitle>
        <DialogDescription>Cada setor sai em uma folha própria, para entregar a cada equipe.</DialogDescription>
      </DialogHeader>
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-2 text-sm font-semibold">Setores</legend>
        <label htmlFor={`${id}-todos`} className="flex min-h-11 items-center gap-3 font-semibold">
          <input
            id={`${id}-todos`}
            type="checkbox"
            className={CAIXA}
            checked={todos}
            onChange={(e) => {
              setTodos(e.target.checked)
              if (e.target.checked) setMarcados(new Set())
            }}
          />
          Todos os setores
        </label>
        {carregandoSetores ? (
          <p className="text-muted-foreground">Carregando os setores…</p>
        ) : (
          opcoes.map((o) => (
            <label key={o.chave} htmlFor={`${id}-${o.chave}`} className="flex min-h-11 items-center gap-3 pl-6">
              <input
                id={`${id}-${o.chave}`}
                type="checkbox"
                className={CAIXA}
                checked={todos || marcados.has(o.chave)}
                onChange={() => alternar(o.chave)}
              />
              {o.nome}
            </label>
          ))
        )}
      </fieldset>
      {(erro || erroSetores) && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{erro ?? erroSetores}</AlertTitle>
          {erro !== "Escolha pelo menos um setor." && (
            <AlertDescription>Confira a escolha e tente de novo.</AlertDescription>
          )}
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
