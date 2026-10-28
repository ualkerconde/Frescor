/*
 * Tela de previsão (Fase 3 / F9), pela skill Frescor. Carregada só quando
 * aberta (React.lazy em App.tsx; regra do W8 sobre o tamanho do JS).
 *
 * - Filtros: dia previsto (padrão: amanhã), loja e produto. Aplicam na hora
 *   e ficam na URL (recarregar ou compartilhar mantém a tela).
 * - Ordem (pedido do Ualker): resumo do dia no topo, depois a tabela com a
 *   explicação de cada número, e por fim a qualidade da previsão.
 * - Uma ação principal: "Gerar previsão" (nada gerado para o dia) ou
 *   "Atualizar previsão" (já existe). Gera os 7 dias a partir de hoje, com
 *   as vendas até ontem; o resultado vai num aviso que some sozinho, o erro
 *   fica na tela até a próxima tentativa.
 * - Produto sem previsão ou com pouco histórico nunca some: aparece na
 *   tabela com etiqueta e é citado pelo nome no resumo.
 */
import { useId, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleAlert, RefreshCw, Sparkles } from "lucide-react"
import { useSearchParams } from "react-router"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Toaster } from "@/components/ui/sonner"
import { apiJson } from "@/lib/api/cliente"
import type { GeracaoPrevisoes, LojaWeb, Previsoes } from "@/lib/api/tipos"
import { contar, dataIso, formatarData, somarDias } from "@/lib/formato"
import { SeletorProduto, type ProdutoEscolhido } from "./consultar/SeletorProduto"
import { CardQualidade } from "./previsao/CardQualidade"
import { ResumoDia } from "./previsao/ResumoDia"
import { TabelaPrevisao } from "./previsao/TabelaPrevisao"

const TODAS_AS_LOJAS = "todas"
/** A geração cobre 7 dias: de hoje (referência = ontem) até hoje + 6 (D22). */
const DIAS_HORIZONTE = 7

function hoje(): string {
  return dataIso(new Date())
}

interface Filtros {
  data: string
  loja: string // id ou TODAS_AS_LOJAS
  produto: ProdutoEscolhido | null
}

function lerFiltros(params: URLSearchParams): Filtros {
  const produtoId = Number(params.get("produto"))
  return {
    data: params.get("data") || somarDias(hoje(), 1),
    loja: params.get("loja") ?? TODAS_AS_LOJAS,
    produto: produtoId ? { id: produtoId, rotulo: params.get("produto_rotulo") ?? `Produto ${produtoId}` } : null,
  }
}

function caminhoLista(f: Filtros): string {
  const q = new URLSearchParams({ data: f.data })
  if (f.loja !== TODAS_AS_LOJAS) q.set("loja_id", f.loja)
  if (f.produto) q.set("produto_id", String(f.produto.id))
  return `/previsoes?${q.toString()}`
}

export function Previsao() {
  const [params, setParams] = useSearchParams()
  const filtros = useMemo(() => lerFiltros(params), [params])
  const [erroGeracao, setErroGeracao] = useState<string | null>(null)
  // O campo de data tem estado próprio: enquanto a pessoa digita, o valor
  // fica vazio (data incompleta) e só vai para a URL quando é uma data.
  // Voltar/avançar do navegador muda a URL: o campo acompanha.
  const [dataDigitada, setDataDigitada] = useState(filtros.data)
  const [dataVista, setDataVista] = useState(filtros.data)
  if (filtros.data !== dataVista) {
    setDataVista(filtros.data)
    setDataDigitada(filtros.data)
  }
  const queryClient = useQueryClient()
  const id = useId()

  const ultimoDia = somarDias(hoje(), DIAS_HORIZONTE - 1)
  const foraDoHorizonte = filtros.data > ultimoDia
  const noPassado = filtros.data < hoje()

  const lojas = useQuery({ queryKey: ["lojas"], queryFn: () => apiJson<LojaWeb[]>("/web/lojas") })
  const lista = useQuery({
    queryKey: ["previsoes", "lista", filtros.data, filtros.loja, filtros.produto?.id ?? null],
    queryFn: () => apiJson<Previsoes>(caminhoLista(filtros)),
  })

  const geracao = useMutation({
    mutationFn: () => apiJson<GeracaoPrevisoes>("/previsoes/gerar", { method: "POST", json: {} }),
    onMutate: () => setErroGeracao(null),
    onSuccess: (r) => {
      const semNumero = r.sem_previsao > 0 ? `, ${contar(r.sem_previsao, "sem previsão", "sem previsão")}` : ""
      toast.success(
        `Previsão pronta de ${formatarData(r.data_inicio)} a ${formatarData(r.data_fim)}: ${contar(r.gravadas, "item", "itens")}${semNumero}.`,
      )
      queryClient.invalidateQueries({ queryKey: ["previsoes", "lista"] })
    },
    onError: (erro) => setErroGeracao(erro instanceof Error ? erro.message : String(erro)),
  })

  function atualizarUrl(mudancas: Record<string, string | null>) {
    const novos = new URLSearchParams(params)
    for (const [chave, valor] of Object.entries(mudancas)) {
      if (valor === null) novos.delete(chave)
      else novos.set(chave, valor)
    }
    setParams(novos)
  }

  const itens = lista.data?.itens ?? []
  const temPrevisao = itens.length > 0
  const mostrarLoja = filtros.loja === TODAS_AS_LOJAS
  const filtrado = filtros.loja !== TODAS_AS_LOJAS || filtros.produto !== null
  // Uma ação principal por tela: o botão fica no estado vazio quando é ele
  // que resolve; nos outros casos, no topo. Enquanto a lista carrega ele não
  // aparece em nenhum dos dois (sem "pular" de lugar quando a lista chega).
  const botaoNoVazio = !lista.isError && !temPrevisao && !foraDoHorizonte && !noPassado

  const botaoGerar = (
    <Button onClick={() => geracao.mutate()} carregando={geracao.isPending} textoCarregando="Gerando…">
      {temPrevisao ? <RefreshCw aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
      {temPrevisao ? "Atualizar previsão" : "Gerar previsão"}
    </Button>
  )

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight">Previsão de vendas</h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Quanto cada loja deve vender por produto, calculado com as vendas importadas. Use como ponto de partida para
            a produção.
          </p>
        </div>
        {!botaoNoVazio && botaoGerar}
      </div>

      <div className="grid gap-4 painel p-6 md:grid-cols-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-data`}>Dia previsto</Label>
          <Input
            id={`${id}-data`}
            type="date"
            value={dataDigitada}
            max={ultimoDia}
            onChange={(e) => {
              setDataDigitada(e.target.value)
              if (e.target.value) atualizarUrl({ data: e.target.value })
            }}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-loja`}>Loja</Label>
          <Select
            value={filtros.loja}
            onValueChange={(loja) => atualizarUrl({ loja: loja === TODAS_AS_LOJAS ? null : loja })}
          >
            <SelectTrigger id={`${id}-loja`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TODAS_AS_LOJAS}>Todas as lojas da central</SelectItem>
              {(lojas.data ?? []).map((l) => (
                <SelectItem key={l.id} value={String(l.id)}>
                  {l.codigo ? `${l.codigo} · ${l.nome}` : l.nome}
                  {!l.ativo && " (inativa)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-produto`}>Produto</Label>
          <SeletorProduto
            id={`${id}-produto`}
            valor={filtros.produto}
            aoMudar={(produto) =>
              atualizarUrl({
                produto: produto ? String(produto.id) : null,
                produto_rotulo: produto ? produto.rotulo : null,
              })
            }
          />
        </div>
      </div>

      {erroGeracao && (
        <Alert variant="erro">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A previsão não foi gerada. {erroGeracao}</AlertTitle>
          <AlertDescription>Tente de novo. Se continuar, confira se as vendas foram importadas.</AlertDescription>
        </Alert>
      )}

      <div aria-live="polite" className="flex flex-col gap-8">
        {lista.isError ? (
          <Alert variant="erro">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{lista.error.message}</AlertTitle>
          </Alert>
        ) : lista.isPending ? (
          <p className="text-muted-foreground">Carregando…</p>
        ) : !temPrevisao ? (
          <div className="painel-vazio p-6">
            {foraDoHorizonte ? (
              <>
                <p className="text-foreground">A previsão cobre só os próximos {DIAS_HORIZONTE} dias.</p>
                <p className="mt-1 text-muted-foreground">Escolha um dia até {formatarData(ultimoDia)}.</p>
              </>
            ) : noPassado ? (
              <>
                <p className="text-foreground">Nenhuma previsão foi gerada para {formatarData(filtros.data)}.</p>
                <p className="mt-1 text-muted-foreground">Escolha outro dia, de hoje até {formatarData(ultimoDia)}.</p>
              </>
            ) : (
              <>
                <p className="text-foreground">
                  Nenhuma previsão gerada para {formatarData(filtros.data)}
                  {filtrado ? " com esses filtros" : ""}.
                </p>
                <p className="mt-1 mb-4 text-muted-foreground">
                  Gere a previsão para ver quanto cada loja deve vender nos próximos {DIAS_HORIZONTE} dias.
                </p>
                {botaoGerar}
              </>
            )}
          </div>
        ) : (
          <>
            <ResumoDia data={lista.data.data} itens={itens} totais={lista.data.totais} mostrarLoja={mostrarLoja} />
            <div className="flex flex-col gap-3">
              <h2 className="text-[22px]">Por produto</h2>
              <TabelaPrevisao itens={itens} mostrarLoja={mostrarLoja} />
            </div>
          </>
        )}
      </div>

      <CardQualidade
        lojaId={filtros.loja === TODAS_AS_LOJAS ? null : Number(filtros.loja)}
        produtoId={filtros.produto?.id ?? null}
      />

      {/* Aviso de "previsão pronta" (some sozinho, skill). Montado aqui, e não
          no layout, para a biblioteca de avisos ir no pacote desta tela e não
          no JS principal (que já estava perto do limite de 500 kB). */}
      <Toaster position="bottom-right" />
    </section>
  )
}
