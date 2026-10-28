/*
 * Avisos de cada linha da ordem (gravados pelo backend como códigos) em
 * linguagem da loja: um rótulo curto para a etiqueta e uma frase do que
 * aconteceu / o que fazer. Código desconhecido não some: aparece como
 * "Atenção".
 */

export type GravidadeAviso = 'erro' | 'aviso' | 'info'

export interface DescricaoAviso {
  rotulo: string
  gravidade: GravidadeAviso
  explicacao: string
}

export const AVISOS: Record<string, DescricaoAviso> = {
  sem_calendario: {
    rotulo: 'Sem calendário',
    gravidade: 'erro',
    explicacao: 'O produto não tem dias de produção cadastrados. Informe a quantidade ou cadastre o calendário.',
  },
  sem_previsao: {
    rotulo: 'Sem previsão',
    gravidade: 'erro',
    explicacao: 'Falta a previsão de algum dia da cobertura. Informe a quantidade.',
  },
  validade_menor_que_prazo: {
    rotulo: 'Chega vencido',
    gravidade: 'erro',
    explicacao: 'Com o prazo de entrega da central, o produto chega à loja já vencido.',
  },
  sem_contagem: {
    rotulo: 'Sem contagem',
    gravidade: 'aviso',
    explicacao: 'A loja nunca contou este produto: o estoque foi considerado zero.',
  },
  contagem_desatualizada: {
    rotulo: 'Contagem antiga',
    gravidade: 'aviso',
    explicacao: 'A última contagem é de antes do fechamento da véspera: o estoque foi considerado zero.',
  },
  cobertura_maior_que_validade: {
    rotulo: 'Ajuste o calendário',
    gravidade: 'aviso',
    explicacao: 'O produto vence antes da próxima produção: a quantidade cobre só os dias da validade.',
  },
  estoque_acima_do_maximo: {
    rotulo: 'Estoque acima do máximo',
    gravidade: 'info',
    explicacao: 'A loja já tem mais do que precisa até a próxima entrega.',
  },
  recebimento_nao_confirmado: {
    rotulo: 'Recebimento não confirmado',
    gravidade: 'info',
    explicacao:
      'A entrega anterior não teve a saída registrada no romaneio: foi considerada recebida pela quantidade aprovada.',
  },
  sem_confirmacao: {
    rotulo: 'Sem confirmação',
    gravidade: 'aviso',
    explicacao:
      'A loja não confirmou a entrega anterior até o fim do dia: ela foi considerada recebida pela quantidade enviada.',
  },
  confirmada_com_atraso: {
    rotulo: 'Confirmada com atraso',
    gravidade: 'info',
    explicacao: 'A loja confirmou a entrega anterior só no dia seguinte: a conta não muda, só fica registrado.',
  },
}

export function descreverAviso(codigo: string): DescricaoAviso {
  return AVISOS[codigo] ?? { rotulo: 'Atenção', gravidade: 'aviso', explicacao: 'Confira esta linha.' }
}
