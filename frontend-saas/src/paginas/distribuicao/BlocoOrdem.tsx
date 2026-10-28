/*
 * Uma ordem do dia de entrega na tela de distribuição (E10), com o que dá
 * para fazer em cada situação (uma ação principal por vez):
 *
 * - Ordem em rascunho: só o aviso e o caminho para aprová-la em Produção.
 * - Ordem aprovada sem romaneio: "Registrar produção" (principal enquanto
 *   falta registrar) e "Gerar romaneio" (principal depois).
 * - Romaneio em rascunho: "Aprovar romaneio" (principal; o navegador já
 *   avisa, antes de chamar a API, se a soma das lojas passa do produzido,
 *   D71), "Ajustar" por loja + produto, "Corrigir produção", "Gerar de
 *   novo" (confirma se houver ajustes, que se perdem, como a D58) e
 *   "Apagar romaneio". Não há "Registrar saída" no rascunho.
 * - Romaneio aprovado: "Registrar saída" (principal enquanto falta alguma
 *   loja; diálogo, porque não se desfaz, D76) e "Imprimir" (D81); o
 *   acompanhamento por loja mostra a situação de cada entrega.
 *
 * Erros da API aparecem com a frase do backend (em português, sem código).
 */
import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { CircleAlert, ClipboardCheck, ClipboardList, Factory, Printer, RefreshCw, Trash2, Truck } from "lucide-react"
import { Link } from "react-router"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { apiFetch, apiJson } from "@/lib/api/cliente"
import type { GeracaoRomaneio, OrdemDistribuicao, ResultadoProducao, ResultadoSaida, RomaneioDetalhe } from "@/lib/api/tipos"
import { contar, formatarData, formatarQuantidade } from "@/lib/formato"
import { DialogoAjuste, DialogoConfirmar, type AlvoAjuste } from "../producao/Dialogos"
import { DialogoImprimirRomaneio } from "./Imprimir"
import { SituacaoRomaneio } from "./Marcadores"
import { DialogoProducao } from "./RegistrarProducao"
import { DialogoSaida } from "./Saida"
import { acimaDoProduzido, aguardandoSaida, descreverSituacao, itensAjustados } from "./situacao"
import { TabelaAcompanhamento, TabelaProducao, TabelaProducaoOrdem, TabelaRascunho } from "./TabelasRomaneio"

const DICA_ROMANEIO = "Confira o romaneio e tente de novo."

type Confirmacao = "aprovar" | "apagar" | "regerar" | null

function mensagem(erro: unknown): string {
  return erro instanceof Error ? erro.message : String(erro)
}

export function BlocoOrdem({ ordem, atualizar }: { ordem: OrdemDistribuicao; atualizar: () => Promise<unknown> }) {
  const [registrando, setRegistrando] = useState(false)
  const [alvoAjuste, setAlvoAjuste] = useState<AlvoAjuste | null>(null)
  const [confirmacao, setConfirmacao] = useState<Confirmacao>(null)
  const [saindo, setSaindo] = useState(false)
  const [imprimindo, setImprimindo] = useState(false)
  const [erroAcao, setErroAcao] = useState<string | null>(null)

  const resumo = ordem.romaneio
  const detalhe = useQuery({
    queryKey: ["distribuicao", "romaneio", resumo?.id],
    queryFn: () => apiJson<RomaneioDetalhe>(`/distribuicao/romaneios/${resumo?.id}`),
    enabled: resumo !== null,
  })
  const romaneio = detalhe.data ?? null
  const urlRomaneio = `/distribuicao/romaneios/${resumo?.id}`

  const producao = useMutation({
    mutationFn: (itens: { item_id: number; quantidade: string }[]) =>
      apiJson<ResultadoProducao>(`/distribuicao/ordens/${ordem.ordem_id}/producao`, { method: "POST", json: { itens } }),
    onSuccess: async (r) => {
      setRegistrando(false)
      if (r.romaneio_desatualizado) {
        toast.warning("Produção registrada. O rascunho do romaneio não mudou: use “Gerar de novo” para refazer a sugestão.")
      } else {
        toast.success(`Produção registrada: ${contar(r.itens_registrados, "produto", "produtos")}.`)
      }
      await atualizar()
    },
  })

  const geracao = useMutation({
    mutationFn: () => apiJson<GeracaoRomaneio>("/distribuicao/romaneios/gerar", { method: "POST", json: { ordem_id: ordem.ordem_id } }),
    onMutate: () => setErroAcao(null),
    onSuccess: async (r) => {
      setConfirmacao(null)
      const falta = r.produtos_com_escassez.length > 0
        ? ` ${contar(r.produtos_com_escassez.length, "produto ficou", "produtos ficaram")} abaixo do planejado: a sugestão divide entre as lojas.`
        : ""
      toast.success(`Romaneio ${r.substituiu_rascunho ? "gerado de novo" : "gerado"}: ${contar(r.entregas, "loja", "lojas")}.${falta}`)
      await atualizar()
    },
    onError: (erro) => {
      if (confirmacao === null) setErroAcao(`O romaneio não foi gerado. ${mensagem(erro)}`)
    },
  })

  const ajuste = useMutation({
    mutationFn: (v: { itemId: number; quantidade: string; motivo: string }) =>
      apiJson(`${urlRomaneio}/itens/${v.itemId}`, {
        method: "PATCH",
        json: { quantidade_final: v.quantidade, motivo: v.motivo || null },
      }),
    onSuccess: async () => {
      setAlvoAjuste(null)
      toast.success("Quantidade salva.")
      await atualizar()
    },
  })

  const aprovacao = useMutation({
    mutationFn: () => apiJson(`${urlRomaneio}/aprovar`, { method: "POST" }),
    onSuccess: async () => {
      setConfirmacao(null)
      toast.success(`Romaneio de ${formatarData(ordem.data_entrega)} aprovado.`)
      await atualizar()
    },
  })

  const exclusao = useMutation({
    mutationFn: () => apiFetch(urlRomaneio, { method: "DELETE" }),
    onSuccess: async () => {
      setConfirmacao(null)
      toast.success("Rascunho do romaneio apagado.")
      await atualizar()
    },
  })

  const saida = useMutation({
    mutationFn: (entregaIds: number[] | null) =>
      apiJson<ResultadoSaida>(`${urlRomaneio}/saida`, {
        method: "POST",
        ...(entregaIds === null ? {} : { json: { entrega_ids: entregaIds } }),
      }),
    onSuccess: async (r) => {
      setSaindo(false)
      toast.success(`Saída registrada: ${contar(r.entregas.length, "loja", "lojas")}.`)
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
    if (romaneio && itensAjustados(romaneio.entregas) > 0) abrirConfirmacao("regerar")
    else geracao.mutate()
  }

  const faltaRegistrar = ordem.itens.some((i) => i.produzido === null)
  const rascunho = romaneio?.status === "rascunho"
  const pendentes = romaneio && !rascunho ? aguardandoSaida(romaneio.entregas) : []
  const acima = romaneio ? acimaDoProduzido(romaneio.producao) : []

  const botaoProducao = (principal: boolean) => (
    <Button
      variant={principal ? "default" : "secondary"}
      onClick={() => {
        producao.reset()
        setRegistrando(true)
      }}
    >
      <ClipboardList aria-hidden="true" />
      {faltaRegistrar ? "Registrar produção" : "Corrigir produção"}
    </Button>
  )

  let acoes: React.ReactNode = null
  if (ordem.status_ordem === "aprovada" && !resumo) {
    acoes = faltaRegistrar ? (
      botaoProducao(true)
    ) : (
      <>
        {botaoProducao(false)}
        <Button onClick={() => geracao.mutate()} carregando={geracao.isPending} textoCarregando="Gerando…">
          <Factory aria-hidden="true" />
          Gerar romaneio
        </Button>
      </>
    )
  } else if (romaneio && rascunho) {
    acoes = (
      <>
        {botaoProducao(false)}
        <Button variant="secondary" onClick={gerarDeNovo} carregando={geracao.isPending && confirmacao === null} textoCarregando="Gerando…">
          <RefreshCw aria-hidden="true" />
          Gerar de novo
        </Button>
        <Button variant="secondary" onClick={() => abrirConfirmacao("apagar")}>
          <Trash2 aria-hidden="true" />
          Apagar romaneio
        </Button>
        <Button onClick={() => abrirConfirmacao("aprovar")}>
          <ClipboardCheck aria-hidden="true" />
          Aprovar romaneio
        </Button>
      </>
    )
  } else if (romaneio) {
    acoes = (
      <>
        <Button variant={pendentes.length > 0 ? "secondary" : "default"} onClick={() => setImprimindo(true)}>
          <Printer aria-hidden="true" />
          Imprimir
        </Button>
        {pendentes.length > 0 && (
          <Button
            onClick={() => {
              saida.reset()
              setSaindo(true)
            }}
          >
            <Truck aria-hidden="true" />
            Registrar saída
          </Button>
        )}
      </>
    )
  }

  const situacoes = romaneio
    ? Object.entries(
        romaneio.entregas.reduce<Record<string, number>>((acc, e) => {
          const r = descreverSituacao(e.situacao).rotulo.toLowerCase()
          acc[r] = (acc[r] ?? 0) + 1
          return acc
        }, {}),
      )
        .map(([r, n]) => `${n} ${r}`)
        .join(" · ")
    : ""

  return (
    <article
      aria-label={`Ordem de produção de ${formatarData(ordem.data_producao)}`}
      className="flex flex-col gap-6 rounded-lg border border-line bg-card p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex flex-wrap items-center gap-3 text-[22px]">
            Produção de {formatarData(ordem.data_producao)}
            {romaneio && <SituacaoRomaneio status={romaneio.status} />}
          </h2>
          <p className="mt-1 text-muted-foreground">
            Entrega em {formatarData(ordem.data_entrega)}
            {romaneio ? ` · ${contar(romaneio.entregas.length, "loja", "lojas")}: ${situacoes}` : ""}
          </p>
        </div>
        {acoes && <div className="flex flex-wrap gap-2">{acoes}</div>}
      </div>

      {erroAcao && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{erroAcao}</AlertTitle>
          <AlertDescription>{DICA_ROMANEIO}</AlertDescription>
        </Alert>
      )}

      {ordem.status_ordem !== "aprovada" ? (
        <div className="rounded-lg bg-surface p-4">
          <p>A ordem de produção deste dia ainda é um rascunho.</p>
          <p className="mt-1 text-muted-foreground">
            Aprove a ordem para registrar a produção e montar o romaneio.{" "}
            <Link to={`/producao?data=${ordem.data_producao}`} className="font-semibold text-primary underline">
              Abrir a ordem de produção
            </Link>
          </p>
        </div>
      ) : !resumo ? (
        <>
          {faltaRegistrar && (
            <p className="text-muted-foreground">
              Registre quanto foi produzido de cada produto. Depois, gere o romaneio com quanto vai para cada loja.
            </p>
          )}
          <TabelaProducaoOrdem itens={ordem.itens} />
        </>
      ) : detalhe.isError ? (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{mensagem(detalhe.error)}</AlertTitle>
          <AlertDescription>Recarregue a página. Se continuar, tente de novo em alguns minutos.</AlertDescription>
        </Alert>
      ) : !romaneio ? (
        <p className="text-muted-foreground">Carregando o romaneio…</p>
      ) : (
        <>
          {rascunho && romaneio.desatualizado && (
            <Alert variant="aviso">
              <CircleAlert aria-hidden="true" />
              <AlertTitle>A produção mudou depois que o romaneio foi gerado.</AlertTitle>
              <AlertDescription>Use “Gerar de novo” para refazer a sugestão com a produção de agora.</AlertDescription>
            </Alert>
          )}
          <TabelaProducao producao={romaneio.producao} />
          {rascunho ? (
            <TabelaRascunho
              entregas={romaneio.entregas}
              aoAjustar={(alvo) => {
                ajuste.reset()
                setAlvoAjuste(alvo)
              }}
            />
          ) : (
            <TabelaAcompanhamento entregas={romaneio.entregas} />
          )}
        </>
      )}

      <DialogoProducao
        aberto={registrando}
        dataProducao={ordem.data_producao}
        itens={ordem.itens}
        salvando={producao.isPending}
        erroApi={producao.isError ? mensagem(producao.error) : null}
        aoFechar={() => setRegistrando(false)}
        aoSalvar={(itens) => producao.mutate(itens)}
      />
      <DialogoAjuste
        alvo={alvoAjuste}
        salvando={ajuste.isPending}
        erroApi={ajuste.isError ? mensagem(ajuste.error) : null}
        dica={DICA_ROMANEIO}
        aoFechar={() => setAlvoAjuste(null)}
        aoSalvar={(quantidade, motivo) =>
          alvoAjuste && ajuste.mutate({ itemId: alvoAjuste.linhaId, quantidade, motivo })
        }
      />
      {romaneio && (
        <>
          <DialogoConfirmar
            aberto={confirmacao === "aprovar"}
            titulo={`Aprovar o romaneio de ${formatarData(ordem.data_entrega)}?`}
            descricao={
              <p>
                Depois de aprovado, o romaneio não pode ser ajustado, gerado de novo nem apagado. Em seguida, imprima e
                registre a saída de cada loja.
              </p>
            }
            bloqueio={
              acima.length > 0
                ? `Mais do que o produzido em ${acima
                    .map((p) => `${p.produto.nome} (${formatarQuantidade(p.total_final, p.unidade)} para ${formatarQuantidade(p.produzido ?? 0, p.unidade)} produzidos)`)
                    .join("; ")}. Ajuste as lojas ou corrija a produção antes de aprovar.`
                : null
            }
            verbo="Aprovar romaneio"
            verboCarregando="Aprovando…"
            carregando={aprovacao.isPending}
            erroApi={aprovacao.isError ? mensagem(aprovacao.error) : null}
            dica={DICA_ROMANEIO}
            aoFechar={() => setConfirmacao(null)}
            aoConfirmar={() => aprovacao.mutate()}
          />
          <DialogoConfirmar
            aberto={confirmacao === "apagar"}
            titulo="Apagar o rascunho do romaneio?"
            descricao={<p>O rascunho e os ajustes feitos nele serão apagados. Depois, é possível gerar o romaneio de novo.</p>}
            verbo="Apagar romaneio"
            verboCarregando="Apagando…"
            perigo
            carregando={exclusao.isPending}
            erroApi={exclusao.isError ? mensagem(exclusao.error) : null}
            dica={DICA_ROMANEIO}
            aoFechar={() => setConfirmacao(null)}
            aoConfirmar={() => exclusao.mutate()}
          />
          <DialogoConfirmar
            aberto={confirmacao === "regerar"}
            titulo="Gerar o romaneio de novo?"
            descricao={
              <p>
                {contar(itensAjustados(romaneio.entregas), "quantidade ajustada", "quantidades ajustadas")}{" "}
                {itensAjustados(romaneio.entregas) === 1 ? "será perdida" : "serão perdidas"}: as quantidades voltam à
                sugestão, calculada com a produção registrada agora.
              </p>
            }
            verbo="Gerar de novo"
            verboCarregando="Gerando…"
            carregando={geracao.isPending}
            erroApi={geracao.isError && confirmacao === "regerar" ? mensagem(geracao.error) : null}
            dica={DICA_ROMANEIO}
            aoFechar={() => setConfirmacao(null)}
            aoConfirmar={() => geracao.mutate()}
          />
          <DialogoSaida
            aberto={saindo}
            pendentes={pendentes}
            salvando={saida.isPending}
            erroApi={saida.isError ? mensagem(saida.error) : null}
            aoFechar={() => setSaindo(false)}
            aoConfirmar={(ids) => saida.mutate(ids)}
          />
          <DialogoImprimirRomaneio
            aberto={imprimindo}
            romaneioId={romaneio.id}
            dataEntrega={romaneio.data_entrega}
            entregas={romaneio.entregas}
            aoFechar={() => setImprimindo(false)}
          />
        </>
      )}
    </article>
  )
}
