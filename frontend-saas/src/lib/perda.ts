/*
 * Faixas do indicador de perda (D35, D53, D66): perda ÷ venda das 4
 * semanas até a véspera, calculada pelo backend em cada linha da ordem.
 *
 *   até 3%            perda baixa       (verde)
 *   acima de 3% a 5%  normal            (sem destaque)
 *   acima de 5% a 8%  perda alta        (amarelo)
 *   acima de 8%       perda muito alta  (vermelho)
 *
 * Os limites ficam SÓ aqui (constante única). Configuração por negócio é
 * trabalho futuro (docs/STATUS.md).
 */

export const LIMITES_PERDA = {
  /** Até este valor (inclusive): perda baixa. */
  baixa: 0.03,
  /** Acima de `baixa` até este valor: normal. */
  normal: 0.05,
  /** Acima de `normal` até este valor: perda alta. Acima: muito alta. */
  alta: 0.08,
} as const

export type FaixaPerda = 'baixa' | 'normal' | 'alta' | 'muito_alta'

export const ROTULO_FAIXA: Record<FaixaPerda, string> = {
  baixa: 'perda baixa',
  normal: 'normal',
  alta: 'perda alta',
  muito_alta: 'perda muito alta',
}

/** Fração (texto ou número) -> faixa; null quando não houve venda. */
export function faixaPerda(taxa: string | number | null | undefined): FaixaPerda | null {
  if (taxa === null || taxa === undefined || taxa === '') return null
  const valor = Number(taxa)
  if (!Number.isFinite(valor)) return null
  if (valor <= LIMITES_PERDA.baixa) return 'baixa'
  if (valor <= LIMITES_PERDA.normal) return 'normal'
  if (valor <= LIMITES_PERDA.alta) return 'alta'
  return 'muito_alta'
}
