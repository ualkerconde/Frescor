/*
 * Explicação de cada previsão em português simples, montada só com os
 * componentes que o backend grava (F7/F8). Nenhuma conta nova é feita aqui:
 * o número exibido é sempre o do backend; este arquivo só descreve como ele
 * foi formado (base × tendência, cold start, eventos).
 *
 * - `resumo`: uma frase curta, sempre visível na linha da tabela.
 * - `passos`: a conta passo a passo, para quem abre a linha.
 * - `situacao`: o que a linha precisa mostrar (etiqueta, destaque).
 */
import type { ItemPrevisao } from "@/lib/api/tipos"
import { diaDaSemana, formatarData, formatarPrevisao, formatarVariacao } from "@/lib/formato"

/** Janelas do motor (D18 e D19; backend/app/services/previsao_calculo.py). */
const SEMANAS_BASE = 6
const DIAS_TENDENCIA = 7
const MINIMO_DIAS_TENDENCIA = 5

export type Situacao = "normal" | "pouco_historico" | "sem_previsao" | "valor_fixo"

export interface Explicacao {
  resumo: string
  passos: string[]
  situacao: Situacao
}

const fator = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 })
const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })

const ORIGEM_PROXY: Record<NonNullable<ItemPrevisao["origem_proxy"]>, string> = {
  outras_lojas: "do mesmo produto nas outras lojas da central",
  categoria: "dos produtos da mesma categoria nesta loja",
  unidade: "dos produtos vendidos na mesma unidade nesta loja",
}

const ORIGEM_PROXY_CURTA: Record<NonNullable<ItemPrevisao["origem_proxy"]>, string> = {
  outras_lojas: "outras lojas",
  categoria: "produtos da mesma categoria",
  unidade: "produtos da mesma unidade",
}

function qtd(item: ItemPrevisao, valor: string | null): string {
  return valor === null ? "—" : formatarPrevisao(valor, item.unidade)
}

/** "Mediana das últimas 6 terças" / "Mediana de 4 das últimas 6 terças". */
function nomeBase(item: ItemPrevisao): string {
  if (item.metodo === "sazonal") return "Mediana do mesmo período do ano passado"
  const dias = diaDaSemana(item.data, true)
  return item.semanas_na_base >= SEMANAS_BASE
    ? `Mediana das últimas ${SEMANAS_BASE} ${dias}`
    : `Mediana de ${item.semanas_na_base} das últimas ${SEMANAS_BASE} ${dias}`
}

/** "× tendência +10%" / ", vendas estáveis" / ", sem ajuste de tendência". */
function tendenciaCurta(item: ItemPrevisao): string {
  if (item.tendencia_bruta === null) return ", sem ajuste de tendência"
  const variacao = formatarVariacao(item.tendencia)
  return variacao === "0%" ? ", vendas estáveis" : ` × tendência ${variacao}`
}

function passoBase(item: ItemPrevisao): string {
  if (item.metodo === "sazonal") {
    return `Mediana das vendas no mesmo dia da semana, no mesmo período do ano passado (${item.semanas_na_base} dias): ${qtd(item, item.base)}.`
  }
  const dias = diaDaSemana(item.data, true)
  const quais =
    item.semanas_na_base >= SEMANAS_BASE
      ? `das últimas ${SEMANAS_BASE} ${dias}`
      : `de ${item.semanas_na_base} das últimas ${SEMANAS_BASE} ${dias} (as outras não tinham venda registrada)`
  return `Mediana ${quais}: ${qtd(item, item.base)}. A mediana é o valor do meio, que não se deixa levar por um dia fora do comum.`
}

function passoTendencia(item: ItemPrevisao): string {
  // "do normal" / "do mesmo período do ano passado" (já com a contração).
  const comparacao = item.metodo === "sazonal" ? "do mesmo período do ano passado" : "do normal"
  if (item.tendencia_bruta === null) {
    return `Tendência: sem ajuste. Só ${item.dias_na_tendencia} dos últimos ${DIAS_TENDENCIA} dias tinham venda para comparar (são precisos ${MINIMO_DIAS_TENDENCIA}).`
  }
  const bruta = Math.round((Number(item.tendencia_bruta) - 1) * 100)
  const descricao =
    bruta === 0
      ? `os últimos ${DIAS_TENDENCIA} dias venderam no mesmo ritmo ${comparacao}`
      : `os últimos ${DIAS_TENDENCIA} dias venderam ${inteiro.format(Math.abs(bruta))}% ${bruta > 0 ? "acima" : "abaixo"} ${comparacao}`
  const limitada = Number(item.tendencia) !== Number(item.tendencia_bruta)
  return limitada
    ? `Tendência: ${descricao}; o ajuste é limitado a ${formatarVariacao(item.tendencia)}.`
    : `Tendência: ${descricao} (${formatarVariacao(item.tendencia)}).`
}

function passoConta(item: ItemPrevisao): string {
  return `Conta: ${qtd(item, item.base)} × ${fator.format(Number(item.tendencia))} = ${qtd(item, item.previsao_propria)}.`
}

function semanasDeHistorico(item: ItemPrevisao): number {
  return Math.round(Number(item.peso_historico) * SEMANAS_BASE)
}

function desde(item: ItemPrevisao): string {
  return item.inicio_historico ? ` (desde ${formatarData(item.inicio_historico)})` : ""
}

function motivoSemPrevisao(item: ItemPrevisao): string {
  if (item.pouco_historico) return "ainda não há vendas deste produto nesta loja nem produto parecido para comparar"
  if (item.metodo === "sazonal") return "não há venda registrada no mesmo período do ano passado"
  return `nenhuma das últimas ${SEMANAS_BASE} ${diaDaSemana(item.data, true)} tem venda registrada nesta loja`
}

export function explicarPrevisao(item: ItemPrevisao): Explicacao {
  const fixo = item.eventos.find((e) => e.tipo_ajuste === "valor_fixo")
  if (fixo && item.previsao !== null) {
    const passos = [`O evento “${fixo.nome}” define ${qtd(item, item.previsao)} para este dia, no lugar do cálculo normal.`]
    if (item.previsao_sem_evento !== null) passos.push(`Sem o evento, a previsão seria ${qtd(item, item.previsao_sem_evento)}.`)
    return { resumo: `Valor fixo do evento “${fixo.nome}”`, passos, situacao: "valor_fixo" }
  }

  if (item.previsao === null) {
    const motivo = motivoSemPrevisao(item)
    return {
      resumo: `Sem previsão: ${motivo}.`,
      passos: [
        `Não foi possível calcular: ${motivo}.`,
        "O que fazer: defina a quantidade deste dia pela sua experiência. A previsão aparece quando houver vendas registradas.",
      ],
      situacao: "sem_previsao",
    }
  }

  const passos: string[] = []
  let resumo: string
  const temPropria = item.previsao_propria !== null && item.base !== null

  if (temPropria) {
    passos.push(passoBase(item), passoTendencia(item), passoConta(item))
  }

  const usaProxy = item.pouco_historico && item.proxy !== null && item.origem_proxy !== null
  if (usaProxy) {
    const origem = ORIGEM_PROXY[item.origem_proxy!]
    const semanas = semanasDeHistorico(item)
    if (temPropria) {
      const peso = Math.round(Number(item.peso_historico) * 100)
      passos.push(
        `Pouco histórico: ${semanas} de ${SEMANAS_BASE} semanas de vendas próprias${desde(item)}. Por isso a previsão junta ${peso}% da conta acima com ${100 - peso}% da média ${origem} (${qtd(item, item.proxy)}) = ${qtd(item, item.previsao_sem_evento)}.`,
      )
      resumo = `Pouco histórico: ${peso}% vendas próprias + ${100 - peso}% média de ${ORIGEM_PROXY_CURTA[item.origem_proxy!]}`
    } else {
      passos.push(
        `Pouco histórico${desde(item)}: ainda não há venda própria para calcular. Vale a média ${origem}: ${qtd(item, item.proxy)}.`,
      )
      resumo = `Pouco histórico: média de ${ORIGEM_PROXY_CURTA[item.origem_proxy!]}`
    }
  } else {
    resumo = `${nomeBase(item)}${tendenciaCurta(item)}`
    if (item.pouco_historico) {
      passos.push(
        `Pouco histórico: ${semanasDeHistorico(item)} de ${SEMANAS_BASE} semanas de vendas próprias${desde(item)} e nenhum produto parecido para comparar. Vale só a conta acima; confira o número.`,
      )
    }
  }

  const multiplicadores = item.eventos.filter((e) => e.tipo_ajuste === "multiplicador")
  if (multiplicadores.length > 0) {
    const nomes = multiplicadores.map((e) => `“${e.nome}” (×${fator.format(Number(e.valor_ajuste))})`).join(" e ")
    passos.push(
      `Evento ${nomes}: ${qtd(item, item.previsao_sem_evento)} → ${qtd(item, item.previsao)}.`,
    )
    resumo += ` × evento ${nomes}`
  }

  return { resumo, passos, situacao: item.pouco_historico ? "pouco_historico" : "normal" }
}
