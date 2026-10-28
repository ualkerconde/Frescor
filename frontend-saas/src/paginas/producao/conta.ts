/*
 * "Ver a conta" de uma linha da ordem: passos em português montados só com
 * os componentes gravados pelo backend (nenhuma conta nova aqui), como na
 * tela de previsão.
 */
import type { ContaNecessidade, Unidade } from '@/lib/api/tipos'
import { diaDaSemana, formatarPrevisao, formatarQuantidade } from '@/lib/formato'
import { descreverAviso } from './avisos'

const ORIGEM_MARGEM: Record<string, string> = {
  produto: 'do produto',
  padrao: 'padrão',
  pouco_historico: 'pouco histórico: no mínimo 20%',
}

/** "2026-10-16" -> "sex 16/10" */
function diaCurto(iso: string): string {
  return `${diaDaSemana(iso).slice(0, 3)} ${iso.slice(8, 10)}/${iso.slice(5, 7)}`
}

/** "2026-10-15T21:00:00-03:00" -> "15/10 às 21:00" (hora local da loja, sem converter fuso). */
function momento(iso: string): string {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} às ${iso.slice(11, 16)}`
}

function percentual(valor: string): string {
  return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(Number(valor))}%`
}

export function passosDaConta(c: Partial<ContaNecessidade>, unidade: Unidade): string[] {
  const q = (v: string | null | undefined) => formatarQuantidade(v ?? 0, unidade)
  const p = (v: string | null | undefined) => formatarPrevisao(v ?? 0, unidade)
  const passos: string[] = []
  const dias = c.dias_cobertura ?? []

  if (dias.length > 0) {
    const limite =
      c.dias_cobertura_sem_limite && c.dias_cobertura_sem_limite > dias.length
        ? ` (seriam ${c.dias_cobertura_sem_limite} até a próxima entrega; a validade limita)`
        : ''
    passos.push(`Cobre ${dias.length === 1 ? '1 dia' : `${dias.length} dias`}: ${dias.map(diaCurto).join(', ')}${limite}.`)
  }
  if (c.minimo == null || c.alvo == null) {
    const motivos = (c.avisos ?? []).map((a) => descreverAviso(a).explicacao)
    passos.push(motivos.length > 0 ? motivos.join(' ') : 'Não foi possível calcular: informe a quantidade.')
    return passos
  }
  passos.push(`Previsão de venda somada nesses dias: ${p(c.minimo)}.`)
  passos.push(
    `Margem de ${percentual(c.margem ?? '0')} (${ORIGEM_MARGEM[c.origem_margem ?? ''] ?? 'padrão'}): alvo de ${p(c.alvo)}.`,
  )

  if (c.estoque_contado == null) {
    passos.push('A loja nunca contou este produto: estoque considerado 0.')
  } else if (c.contagem_valida) {
    passos.push(`Contagem da loja: ${q(c.estoque_contado)}${c.contagem_local ? `, em ${momento(c.contagem_local)}` : ''}.`)
  } else {
    passos.push(
      `Contagem de ${q(c.estoque_contado)}${c.contagem_local ? ` em ${momento(c.contagem_local)}` : ''} é anterior ao fechamento da véspera${c.limite_contagem_local ? ` (vale a partir de ${momento(c.limite_contagem_local)})` : ''}: estoque considerado 0.`,
    )
  }

  if ((c.dias_ate_chegada ?? []).length > 0) {
    const transito = Number(c.transito_considerado ?? 0) > 0 ? ` e recebe ${q(c.transito_considerado)} já aprovados` : ''
    passos.push(
      `Antes da chegada (${(c.dias_ate_chegada ?? []).map(diaCurto).join(', ')}), a loja vende ${q(c.consumo_ate_chegada)}${transito}.`,
    )
  } else if (Number(c.transito_considerado ?? 0) > 0) {
    passos.push(`Em trânsito, já aprovado: ${q(c.transito_considerado)}.`)
  }
  if (Number(c.recebido_apos_contagem ?? 0) > 0) {
    passos.push(`Recebido depois da contagem (confirmado pela loja): ${q(c.recebido_apos_contagem)}.`)
  }
  if (Number(c.recebimento_presumido ?? 0) > 0) {
    passos.push(
      `Entrega anterior sem confirmação da loja: ${q(c.recebimento_presumido)} considerados recebidos e já na contagem (não somam de novo).`,
    )
  }
  if (Number(c.vencido_ate_chegada ?? 0) > 0) {
    passos.push(`Vence antes da chegada e não conta: ${q(c.vencido_ate_chegada)}.`)
  }
  passos.push(`Estoque na chegada: ${q(c.estoque_na_chegada)}.`)
  passos.push(
    `Necessidade: ${p(c.alvo)} − ${q(c.estoque_na_chegada)} = ${p(c.necessidade_bruta)}, arredondada para ${q(c.necessidade)}.`,
  )
  return passos
}
