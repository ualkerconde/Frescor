/*
 * Importação de CSV de vendas e perdas (passo W6), pela skill Frescor.
 *
 * - Uma ação principal: "Importar vendas" / "Importar perdas" (primário).
 *   "Baixar modelo de CSV" é secundário.
 * - O arquivo é escolhido pelo seletor ou arrastado para a área. Acima de
 *   5 MB é recusado no navegador, antes de enviar (o backend também recusa).
 * - Resultado: resumo grande no topo e depois erros e avisos
 *   (ResultadoImportacao). Outros problemas (sem conexão, arquivo grande
 *   demais, servidor) num alerta com o que houve e o que fazer.
 */
import { useId, useRef, useState, type ChangeEvent, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { cn } from "cn"
import { CircleAlert, Download, FileText, Upload } from "lucide-react"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { ErroApi, apiUpload } from "@/lib/api/cliente"
import type { RelatorioImportacao, TipoImportacao } from "@/lib/api/tipos"
import { formatarTamanho } from "@/lib/formato"
import { baixarModeloCsv, CABECALHO_CSV } from "@/lib/modeloCsv"
import { ResultadoImportacao } from "./importar/ResultadoImportacao"

const LIMITE_ARQUIVO_BYTES = 5 * 1024 * 1024 // o mesmo do backend

const OPCOES: { valor: TipoImportacao; rotulo: string }[] = [
  { valor: "vendas", rotulo: "Vendas" },
  { valor: "perdas", rotulo: "Perdas" },
]

type Resultado = { tipo: "relatorio"; relatorio: RelatorioImportacao } | { tipo: "erro"; mensagem: string }

/** O 422 da importação traz o relatório completo no corpo. */
function relatorioDoErro(erro: unknown): RelatorioImportacao | null {
  if (erro instanceof ErroApi && erro.status === 422 && typeof erro.corpo === "object" && erro.corpo !== null) {
    if ("sucesso" in erro.corpo && "erros" in erro.corpo) return erro.corpo as RelatorioImportacao
  }
  return null
}

export function Importar() {
  const [tipo, setTipo] = useState<TipoImportacao>("vendas")
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [erroArquivo, setErroArquivo] = useState<string | null>(null)
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [arrastando, setArrastando] = useState(false)
  const campoArquivo = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const id = useId()

  const importacao = useMutation({
    mutationFn: ({ tipoEnviado, arquivoEnviado }: { tipoEnviado: TipoImportacao; arquivoEnviado: File }) => {
      const formulario = new FormData()
      formulario.append("arquivo", arquivoEnviado)
      return apiUpload<RelatorioImportacao>(`/${tipoEnviado}/importar`, formulario)
    },
    onSuccess: (relatorio) => {
      setResultado({ tipo: "relatorio", relatorio })
      // As consultas de vendas/perdas (W7) passam a ver os dados novos.
      queryClient.invalidateQueries({ queryKey: ["consulta"] })
    },
    onError: (erro) => {
      const relatorio = relatorioDoErro(erro)
      if (relatorio) setResultado({ tipo: "relatorio", relatorio })
      else setResultado({ tipo: "erro", mensagem: erro instanceof Error ? erro.message : String(erro) })
    },
  })

  function escolher(novo: File | null) {
    setResultado(null)
    if (novo && novo.size > LIMITE_ARQUIVO_BYTES) {
      setArquivo(null)
      setErroArquivo(
        `O arquivo tem ${formatarTamanho(novo.size)}; o máximo é 5 MB. Divida em arquivos menores e envie cada um.`,
      )
      return
    }
    setErroArquivo(null)
    setArquivo(novo)
  }

  function aoEscolherArquivo(evento: ChangeEvent<HTMLInputElement>) {
    escolher(evento.target.files?.[0] ?? null)
  }

  function aoSoltar(evento: DragEvent<HTMLLabelElement>) {
    evento.preventDefault()
    setArrastando(false)
    const solto = evento.dataTransfer.files?.[0]
    if (solto) escolher(solto)
  }

  function importar() {
    if (!arquivo) {
      setErroArquivo("Escolha o arquivo CSV antes de importar.")
      campoArquivo.current?.focus()
      return
    }
    setResultado(null)
    importacao.mutate({ tipoEnviado: tipo, arquivoEnviado: arquivo })
  }

  function trocarTipo(novo: TipoImportacao) {
    setTipo(novo)
    setResultado(null)
  }

  const rotuloTipo = tipo === "vendas" ? "vendas" : "perdas"

  return (
    <section className="flex flex-col gap-8">
      <div>
        <h1 className="text-[32px] leading-tight">Importar vendas e perdas</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Envie o arquivo CSV com as vendas ou as perdas das lojas. Se alguma linha tiver erro, nada é gravado e você
          vê o que corrigir.
        </p>
      </div>

      <div className="flex max-w-2xl flex-col gap-6 painel p-6">
        <fieldset>
          <legend className="text-sm font-semibold text-foreground">O que você vai importar?</legend>
          <div className="mt-2 inline-flex rounded-lg bg-surface p-1">
            {OPCOES.map((opcao) => (
              <label
                key={opcao.valor}
                className={cn(
                  "inline-flex h-11 min-w-28 cursor-pointer items-center justify-center rounded-md px-4 font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
                  tipo === opcao.valor ? "bg-card text-primary shadow-elevado" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <input
                  type="radio"
                  name={`${id}-tipo`}
                  value={opcao.valor}
                  checked={tipo === opcao.valor}
                  onChange={() => trocarTipo(opcao.valor)}
                  className="sr-only"
                />
                {opcao.rotulo}
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <span id={`${id}-arquivo-rotulo`} className="text-sm font-semibold text-foreground">
            Arquivo CSV
          </span>
          <label
            onDragOver={(e) => {
              e.preventDefault()
              setArrastando(true)
            }}
            onDragLeave={() => setArrastando(false)}
            onDrop={aoSoltar}
            className={cn(
              "mt-2 flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
              erroArquivo ? "border-error" : arrastando ? "border-primary bg-surface" : "border-input-border hover:bg-surface",
            )}
          >
            <input
              ref={campoArquivo}
              type="file"
              accept=".csv,text/csv"
              onChange={aoEscolherArquivo}
              className="sr-only"
              aria-labelledby={`${id}-arquivo-rotulo`}
              aria-invalid={erroArquivo ? true : undefined}
              aria-describedby={`${id}-arquivo-ajuda${erroArquivo ? ` ${id}-arquivo-erro` : ""}`}
            />
            {arquivo ? (
              <>
                <FileText className="size-8 text-primary" aria-hidden="true" />
                <span className="font-semibold text-foreground">{arquivo.name}</span>
                <span className="text-sm text-muted-foreground numero">
                  {formatarTamanho(arquivo.size)} · clique para trocar
                </span>
              </>
            ) : (
              <>
                <Upload className="size-8 text-primary" aria-hidden="true" />
                <span className="font-semibold text-primary">Escolher arquivo</span>
                <span className="text-sm text-muted-foreground">ou arraste o arquivo para cá (até 5 MB)</span>
              </>
            )}
          </label>
          {erroArquivo && (
            <p id={`${id}-arquivo-erro`} className="mt-2 flex items-start gap-2 text-sm text-error">
              <CircleAlert className="size-5 shrink-0" aria-hidden="true" />
              {erroArquivo}
            </p>
          )}
          <p id={`${id}-arquivo-ajuda`} className="mt-3 text-sm text-muted-foreground">
            Colunas: <code className="rounded-sm bg-surface px-1">{CABECALHO_CSV}</code>. Datas como 01/10/2026,
            quantidade com vírgula (25,500), loja e produto pelo código.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button onClick={importar} carregando={importacao.isPending} textoCarregando="Importando…">
            <Upload aria-hidden="true" />
            Importar {rotuloTipo}
          </Button>
          <Button variant="secondary" onClick={() => baixarModeloCsv(tipo)}>
            <Download aria-hidden="true" />
            Baixar modelo de CSV
          </Button>
        </div>
      </div>

      <div aria-live="polite">
        {resultado?.tipo === "relatorio" && <ResultadoImportacao relatorio={resultado.relatorio} />}
        {resultado?.tipo === "erro" && (
          <Alert variant="erro" className="max-w-2xl">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{resultado.mensagem}</AlertTitle>
          </Alert>
        )}
      </div>
    </section>
  )
}
