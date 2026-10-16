/*
 * Tela da ordem de produção (Fase 4 / N9), pela skill Frescor. Carregada só
 * quando aberta (React.lazy em App.tsx).
 *
 * - Data de produção (padrão: amanhã; de hoje até 6 dias à frente, D61) na
 *   URL. Sem ordem no dia: estado vazio com "Gerar ordem".
 * - Rascunho: ação principal "Aprovar ordem"; secundárias "Gerar de novo" e
 *   "Apagar rascunho". Gerar de novo um rascunho com ajustes pede
 *   confirmação dizendo quantas linhas ajustadas serão perdidas (D58).
 *   Aprovar e apagar também confirmam (não se desfazem).
 * - Aprovada: só leitura (sem ajustar, gerar de novo nem apagar).
 * - Produtos em duas tabelas, "Produção" e "A distribuir" (D39), cada uma
 *   abrindo as lojas com avisos, perda (D66), "Ajustar" e "Ver a conta".
 * - Erros da API (404/409/422) aparecem com a frase do backend, em
 *   português e sem ids; sucesso num aviso que some sozinho.
 */
import { useId, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleAlert, ClipboardCheck, Factory, Lock, RefreshCw, Trash2 } from "lucide-react"
import { useSearchParams } from "react-router"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Toaster } from "@/components/ui/sonner"
import { apiFetch, apiJson } from "@/lib/api/cliente"
import type { GeracaoOrdem, OrdemDetalhe, OrdensDoDia } from "@/lib/api/tipos"
import { contar, dataIso, formatarData, somarDias } from "@/lib/formato"
import { DialogoAjuste, DialogoConfirmar, type AlvoAjuste } from "./producao/Dialogos"
import { ResumoOrdem } from "./producao/ResumoOrdem"
import { TabelaOrdem } from "./producao/TabelaOrdem"

/** A ordem pode ser gerada de hoje até 6 dias à frente (D61). */
const DIAS_A_FRENTE = 6

type Confirmacao = "aprovar" | "apagar" | "regerar" | null

function hoje(): string {
  return dataIso(new Date())
}

function mensagem(erro: unknown): string {
  return erro instanceof Error ? erro.message : String(erro)
}

export function Producao() {
  const [params, setParams] = useSearchParams()
  const data = params.get("data") || somarDias(hoje(), 1)
  const [dataDigitada, setDataDigitada] = useState(data)
  const [dataVista, setDataVista] = useState(data)
  if (data !== dataVista) {
    setDataVista(data)
    setDataDigitada(data)
  }
  const [confirmacao, setConfirmacao] = useState<Confirmacao>(null)
  const [alvoAjuste, setAlvoAjuste] = useState<AlvoAjuste | null>(null)
  const [erroGeracao, setErroGeracao] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const id = useId()

  const ultimoDia = somarDias(hoje(), DIAS_A_FRENTE)
  const foraDoPeriodo = data < hoje() || data > ultimoDia

  const lista = useQuery({
    queryKey: ["producao", "lista", data],
    queryFn: () => apiJson<OrdensDoDia>(`/producao/ordens?data=${data}`),
  })
  const programada = lista.data?.ordens.find((o) => o.tipo === "programada") ?? null
  const detalhe = useQuery({
    queryKey: ["producao", "ordem", programada?.id],
    queryFn: () => apiJson<OrdemDetalhe>(`/producao/ordens/${programada?.id}`),
    enabled: programada !== null,
  })
  const ordem = detalhe.data ?? null
  const rascunho = ordem?.status === "rascunho"

  function atualizar() {
    return queryClient.invalidateQueries({ queryKey: ["producao"] })
  }

  const geracao = useMutation({
    mutationFn: () =>
      apiJson<GeracaoOrdem>("/producao/ordens/gerar", { method: "POST", json: { data_producao: data } }),
    onMutate: () => setErroGeracao(null),
    onSuccess: async (r) => {
      setConfirmacao(null)
      const faltam = r.sem_quantidade > 0 ? ` ${contar(r.sem_quantidade, "linha precisa", "linhas precisam")} de quantidade.` : ""
      const previsao = r.previsao_atualizada ? " A previsão estava desatualizada e foi calculada de novo." : ""
      toast.success(
        `Ordem de ${formatarData(r.data_producao)} ${r.substituiu_rascunho ? "gerada de novo" : "gerada"}: ${contar(r.itens, "produto", "produtos")}.${faltam}${previsao}`,
      )
      await atualizar()
    },
    onError: (erro) => setErroGeracao(mensagem(erro)),
  })

  const aprovacao = useMutation({
    mutationFn: () => apiJson(`/producao/ordens/${ordem?.id}/aprovar`, { method: "POST" }),
    onSuccess: async () => {
      setConfirmacao(null)
      toast.success(`Ordem de ${formatarData(data)} aprovada.`)
      await atualizar()
    },
  })

  const exclusao = useMutation({
    mutationFn: () => apiFetch(`/producao/ordens/${ordem?.id}`, { method: "DELETE" }),
    onSuccess: async () => {
      setConfirmacao(null)
      toast.success(`Rascunho de ${formatarData(data)} apagado.`)
      await atualizar()
    },
  })

  const ajuste = useMutation({
    mutationFn: (v: { linhaId: number; quantidade: string; motivo: string }) =>
      apiJson(`/producao/ordens/${ordem?.id}/linhas/${v.linhaId}`, {
        method: "PATCH",
        json: { quantidade_final: v.quantidade, motivo: v.motivo || null },
      }),
    onSuccess: async () => {
      setAlvoAjuste(null)
      toast.success("Quantidade salva.")
      await atualizar()
    },
  })

  function abrirConfirmacao(tipo: Confirmacao) {
    aprovacao.reset()
    exclusao.reset()
    geracao.reset()
    setConfirmacao(tipo)
  }

  function gerarDeNovo() {
    // D58: com ajustes, confirma antes (eles se perdem); sem ajustes, gera direto.
    if (ordem && ordem.linhas_editadas > 0) abrirConfirmacao("regerar")
    else geracao.mutate()
  }

  const carregando = lista.isPending || (programada !== null && detalhe.isPending)
  const erroCarga = lista.isError ? lista.error : detalhe.isError ? detalhe.error : null
  const botaoGerar = (
    <Button onClick={() => geracao.mutate()} carregando={geracao.isPending} textoCarregando="Gerando…">
      <Factory aria-hidden="true" />
      Gerar ordem
    </Button>
  )

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[28px]">Ordem de produção</h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Quanto produzir e mandar para cada loja, calculado com a previsão, a contagem das lojas e o que já está a
            caminho. Confira, ajuste o que precisar e aprove.
          </p>
        </div>
        {ordem && rascunho && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={gerarDeNovo} carregando={geracao.isPending && confirmacao === null} textoCarregando="Gerando…">
              <RefreshCw aria-hidden="true" />
              Gerar de novo
            </Button>
            <Button variant="secondary" onClick={() => abrirConfirmacao("apagar")}>
              <Trash2 aria-hidden="true" />
              Apagar rascunho
            </Button>
            <Button onClick={() => abrirConfirmacao("aprovar")}>
              <ClipboardCheck aria-hidden="true" />
              Aprovar ordem
            </Button>
          </div>
        )}
      </div>

      <div className="grid gap-4 rounded-lg border border-line bg-card p-6 md:grid-cols-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-data`}>Dia de produção</Label>
          <Input
            id={`${id}-data`}
            type="date"
            value={dataDigitada}
            max={ultimoDia}
            onChange={(e) => {
              setDataDigitada(e.target.value)
              if (e.target.value) setParams({ data: e.target.value })
            }}
          />
        </div>
      </div>

      {erroGeracao && confirmacao === null && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A ordem não foi gerada. {erroGeracao}</AlertTitle>
          <AlertDescription>Confira o dia escolhido e tente de novo.</AlertDescription>
        </Alert>
      )}

      <div aria-live="polite" className="flex flex-col gap-8">
        {erroCarga ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{mensagem(erroCarga)}</AlertTitle>
            <AlertDescription>Recarregue a página. Se continuar, tente de novo em alguns minutos.</AlertDescription>
          </Alert>
        ) : carregando ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : !ordem ? (
          <div className="rounded-lg bg-surface p-6">
            <p className="text-foreground">Nenhuma ordem gerada para {formatarData(data)}.</p>
            {foraDoPeriodo ? (
              <p className="mt-1 text-muted-foreground">
                A ordem pode ser gerada de hoje até {formatarData(ultimoDia)}. Escolha outro dia.
              </p>
            ) : (
              <>
                <p className="mt-1 mb-4 text-muted-foreground">
                  Gere a ordem para ver quanto produzir e mandar para cada loja. Se a previsão estiver desatualizada, ela é
                  calculada de novo antes.
                </p>
                {botaoGerar}
              </>
            )}
          </div>
        ) : (
          <>
            {!rascunho && (
              <Alert variant="sucesso">
                <Lock aria-hidden="true" />
                <AlertTitle>Ordem aprovada: só leitura.</AlertTitle>
                <AlertDescription>
                  Ela não pode mais ser ajustada, gerada de novo nem apagada: é o que as lojas vão receber.
                </AlertDescription>
              </Alert>
            )}
            <ResumoOrdem ordem={ordem} />
            <TabelaOrdem
              titulo="Produção"
              descricao="Produtos feitos na central. Abra um produto para ver e ajustar as lojas."
              itens={ordem.itens.filter((i) => i.tipo_abastecimento === "produzido")}
              somenteLeitura={!rascunho}
              aoAjustar={(alvo) => {
                ajuste.reset()
                setAlvoAjuste(alvo)
              }}
            />
            <TabelaOrdem
              titulo="A distribuir"
              descricao="Produtos que a central não produz, só manda para as lojas."
              itens={ordem.itens.filter((i) => i.tipo_abastecimento === "distribuido")}
              somenteLeitura={!rascunho}
              aoAjustar={(alvo) => {
                ajuste.reset()
                setAlvoAjuste(alvo)
              }}
            />
          </>
        )}
      </div>

      <DialogoAjuste
        alvo={alvoAjuste}
        salvando={ajuste.isPending}
        erroApi={ajuste.isError ? mensagem(ajuste.error) : null}
        aoFechar={() => setAlvoAjuste(null)}
        aoSalvar={(quantidade, motivo) =>
          alvoAjuste && ajuste.mutate({ linhaId: alvoAjuste.linhaId, quantidade, motivo })
        }
      />
      <DialogoConfirmar
        aberto={confirmacao === "aprovar"}
        titulo={`Aprovar a ordem de ${formatarData(data)}?`}
        descricao={
          <p>
            Depois de aprovada, a ordem não pode ser ajustada, gerada de novo nem apagada. Ela passa a ser o que as lojas
            vão receber e entra como estoque a caminho nas próximas ordens.
          </p>
        }
        bloqueio={
          ordem && ordem.linhas_sem_quantidade > 0
            ? `Ainda ${contar(ordem.linhas_sem_quantidade, "linha está", "linhas estão")} sem quantidade. Use “Ajustar” para informar antes de aprovar.`
            : null
        }
        verbo="Aprovar ordem"
        verboCarregando="Aprovando…"
        carregando={aprovacao.isPending}
        erroApi={aprovacao.isError ? mensagem(aprovacao.error) : null}
        aoFechar={() => setConfirmacao(null)}
        aoConfirmar={() => aprovacao.mutate()}
      />
      <DialogoConfirmar
        aberto={confirmacao === "apagar"}
        titulo={`Apagar o rascunho de ${formatarData(data)}?`}
        descricao={<p>O rascunho e os ajustes feitos nele serão apagados. Depois, é possível gerar a ordem de novo.</p>}
        verbo="Apagar rascunho"
        verboCarregando="Apagando…"
        perigo
        carregando={exclusao.isPending}
        erroApi={exclusao.isError ? mensagem(exclusao.error) : null}
        aoFechar={() => setConfirmacao(null)}
        aoConfirmar={() => exclusao.mutate()}
      />
      <DialogoConfirmar
        aberto={confirmacao === "regerar"}
        titulo="Gerar a ordem de novo?"
        descricao={
          <p>
            {ordem ? `${contar(ordem.linhas_editadas, "linha ajustada", "linhas ajustadas")} ` : ""}
            {ordem && ordem.linhas_editadas === 1 ? "será perdida" : "serão perdidas"}: a ordem é calculada de novo com
            a previsão e as contagens de agora, e as quantidades voltam à sugestão do sistema.
          </p>
        }
        verbo="Gerar de novo"
        verboCarregando="Gerando…"
        carregando={geracao.isPending}
        erroApi={geracao.isError && confirmacao === "regerar" ? mensagem(geracao.error) : null}
        aoFechar={() => setConfirmacao(null)}
        aoConfirmar={() => geracao.mutate()}
      />

      {/* Avisos de sucesso montados aqui (e não no layout), como na previsão: a
          biblioteca vai no pacote desta tela, não no JS principal. */}
      <Toaster position="bottom-right" />
    </section>
  )
}
