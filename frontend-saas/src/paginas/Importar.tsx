/*
 * Carga de histórico de vendas por CSV (passo W6; reduzida em 11/11/2026
 * pela D107), pela skill Frescor.
 *
 * Por que ainda existe: no dia a dia a venda chega pela integração (D108) e
 * a perda é lançada (D110), por isso a tela saiu do menu. Ela continua para
 * a carga inicial do histórico (a previsão precisa do ano anterior, D109 e
 * D114) e como contingência se a integração parar. Abre pela tela de
 * integração e pela busca de telas. A importação de perdas saiu da tela
 * (a rota do backend continua, por compatibilidade).
 *
 * - Uma ação principal: "Importar vendas" (primário).
 *   "Baixar modelo de CSV" é secundário.
 * - O arquivo é escolhido pelo seletor ou arrastado para a área. Acima de
 *   5 MB é recusado no navegador, antes de enviar (o backend também recusa).
 * - Resultado: resumo grande no topo e depois erros e avisos
 *   (ResultadoImportacao). Outros problemas (sem conexão, arquivo grande
 *   demais, servidor) num alerta com o que houve e o que fazer.
 */
import { useId, useRef, useState, type ChangeEvent, type DragEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router"
import { cn } from "cn"
import { ArrowLeft, CircleAlert, Download, FileText, Upload } from "lucide-react"
import { CabecalhoPagina } from "@/components/layout/CabecalhoPagina"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { ErroApi, apiUpload } from "@/lib/api/cliente"
import type { RelatorioImportacao } from "@/lib/api/tipos"
import { formatarTamanho } from "@/lib/formato"
import { baixarModeloCsv, CABECALHO_CSV } from "@/lib/modeloCsv"
import { ResultadoImportacao } from "./importar/ResultadoImportacao"

const LIMITE_ARQUIVO_BYTES = 5 * 1024 * 1024 // o mesmo do backend

type Resultado = { tipo: "relatorio"; relatorio: RelatorioImportacao } | { tipo: "erro"; mensagem: string }

/** O 422 da importação traz o relatório completo no corpo. */
function relatorioDoErro(erro: unknown): RelatorioImportacao | null {
  if (erro instanceof ErroApi && erro.status === 422 && typeof erro.corpo === "object" && erro.corpo !== null) {
    if ("sucesso" in erro.corpo && "erros" in erro.corpo) return erro.corpo as RelatorioImportacao
  }
  return null
}

export function Importar() {
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [erroArquivo, setErroArquivo] = useState<string | null>(null)
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [arrastando, setArrastando] = useState(false)
  const campoArquivo = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const id = useId()

  const importacao = useMutation({
    mutationFn: (arquivoEnviado: File) => {
      const formulario = new FormData()
      formulario.append("arquivo", arquivoEnviado)
      return apiUpload<RelatorioImportacao>("/vendas/importar", formulario)
    },
    onSuccess: (relatorio) => {
      setResultado({ tipo: "relatorio", relatorio })
      // A consulta (W7), a visão geral e o acompanhamento passam a ver os dados novos.
      queryClient.invalidateQueries({ queryKey: ["consulta"] })
      queryClient.invalidateQueries({ queryKey: ["inicio"] })
      queryClient.invalidateQueries({ queryKey: ["acompanhamento"] })
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
    importacao.mutate(arquivo)
  }

  return (
    <section className="flex flex-col gap-8">
      <CabecalhoPagina
        sobretitulo="Configuração"
        titulo="Carga de histórico de vendas"
        descricao="Para a carga inicial (de preferência 1 a 2 anos de venda diária por loja e produto) ou se a integração com o sistema de vendas parar. Se alguma linha tiver erro, nada é gravado e você vê o que corrigir."
        acoes={
          <Link to="/integracao" className={buttonVariants({ variant: "ghost" })}>
            <ArrowLeft aria-hidden="true" />
            Integração de vendas
          </Link>
        }
      />

      <div className="flex max-w-2xl flex-col gap-6 painel p-6">
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
            Importar vendas
          </Button>
          <Button variant="secondary" onClick={() => baixarModeloCsv("vendas")}>
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
