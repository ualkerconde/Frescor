/*
 * Textos da distribuição em linguagem da loja (Fase 5 / E10): situação de
 * cada entrega (calculada pelo backend na leitura, D79/D85), motivo da
 * diferença no recebimento (D78) e as contas simples da tela (o que passa
 * do produzido). Nenhuma regra de negócio nova aqui.
 */
import type { EntregaRomaneio, MotivoDivergencia, ProducaoRomaneio, SituacaoDaEntrega } from '@/lib/api/tipos'

export type GravidadeSituacao = 'sucesso' | 'aviso' | 'andamento' | 'neutra'

export interface DescricaoSituacao {
  rotulo: string
  gravidade: GravidadeSituacao
  explicacao: string
}

/**
 * Situação da entrega para a etiqueta. "Sem confirmação" nunca vira
 * "Recebido": a loja não confirmou, a conta só presume (D79 (4)).
 */
export function descreverSituacao(s: SituacaoDaEntrega): DescricaoSituacao {
  switch (s.situacao) {
    case 'aguardando_saida':
      return { rotulo: 'Aguardando saída', gravidade: 'neutra', explicacao: 'A saída da central ainda não foi registrada.' }
    case 'a_caminho':
      return {
        rotulo: 'A caminho',
        gravidade: 'andamento',
        explicacao: 'Saiu da central. A loja confirma o recebimento pelo app.',
      }
    case 'sem_confirmacao':
      return {
        rotulo: 'Sem confirmação',
        gravidade: 'aviso',
        explicacao: s.pode_confirmar
          ? 'O dia da entrega terminou sem a loja confirmar: conta como recebida pelo que foi enviado. A loja ainda pode confirmar até o fim de hoje.'
          : 'A loja não confirmou: conta como recebida pelo que foi enviado.',
      }
    case 'confirmada_com_atraso':
      return {
        rotulo: s.com_diferenca ? 'Confirmado com atraso, com diferença' : 'Confirmado com atraso',
        gravidade: s.com_diferenca ? 'aviso' : 'sucesso',
        explicacao: 'A loja confirmou no dia seguinte ao da entrega.',
      }
    case 'recebida':
      return s.com_diferenca
        ? { rotulo: 'Recebido com diferença', gravidade: 'aviso', explicacao: 'A loja confirmou com diferença em algum produto.' }
        : { rotulo: 'Recebido', gravidade: 'sucesso', explicacao: 'A loja confirmou que recebeu tudo certo.' }
  }
}

export const MOTIVOS: Record<MotivoDivergencia, string> = {
  falta: 'Faltou',
  avaria: 'Avaria',
  a_mais: 'Veio a mais',
  outro: 'Outro',
}

const horario = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })

/** Data e hora gravadas em UTC sem fuso pelo backend -> hora local do navegador ("28/10/2026, 06:15"). */
export function quando(isoUtc: string): string {
  return horario.format(new Date(isoUtc.endsWith('Z') || isoUtc.includes('+') ? isoUtc : `${isoUtc}Z`))
}

export function nomeCom(ref: { codigo: string | null; nome: string }): string {
  return ref.codigo ? `${ref.codigo} · ${ref.nome}` : ref.nome
}

/** Produtos em que a soma das lojas passa do produzido (D71): a aprovação seria recusada. */
export function acimaDoProduzido(producao: ProducaoRomaneio[]): ProducaoRomaneio[] {
  return producao.filter((p) => Number(p.total_final) > Number(p.produzido ?? 0))
}

/** Entregas que ainda podem ter a saída registrada, na ordem do código da loja (como vêm da API). */
export function aguardandoSaida(entregas: EntregaRomaneio[]): EntregaRomaneio[] {
  return entregas.filter((e) => e.situacao.situacao === 'aguardando_saida')
}

/** Itens com quantidade ajustada pelo gestor (gerar de novo perde os ajustes, como a D58). */
export function itensAjustados(entregas: EntregaRomaneio[]): number {
  return entregas.reduce((n, e) => n + e.itens.filter((i) => i.editado_em !== null).length, 0)
}
