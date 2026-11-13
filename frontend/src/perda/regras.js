/**
 * Contas e validações da tela de Perda do app (D110). Espelham as regras do
 * backend (`perda_lancamento_service`) só para avisar a loja antes de
 * enviar; quem decide continua sendo o backend.
 */

import { lerQuantidade, unidadeCurta } from '../recebimento/regras'

export const MOTIVOS_PERDA = [
  { valor: 'vencido', rotulo: 'Vencido' },
  { valor: 'avariado', rotulo: 'Avariado' },
  { valor: 'outro', rotulo: 'Outro' },
]

export const TAMANHO_OBSERVACAO = 200

export function rotuloMotivo(valor) {
  return MOTIVOS_PERDA.find((m) => m.valor === valor)?.rotulo ?? valor
}

/** Dia local do celular em "AAAA-MM-DD"; `deslocamento` -1 = ontem. */
export function diaLocal(deslocamento = 0, agora = new Date()) {
  const d = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + deslocamento)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/** Sem acento e minúsculo, para a busca achar "pao" em "Pão". */
function normalizar(texto) {
  return String(texto ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()
}

/** Produtos da loja que batem com a busca (nome, código ou código de barras). */
export function filtrarProdutos(produtos, busca, limite = 30) {
  const termo = normalizar(busca)
  const achados = termo
    ? produtos.filter((p) =>
      normalizar(p.nome).includes(termo) || normalizar(p.codigo).includes(termo) || String(p.codigo_barras ?? '') === termo)
    : produtos
  return achados.slice(0, limite)
}

/**
 * Confere o formulário. Devolve { quantidade, motivo, observacao } com o erro
 * de cada campo (texto) ou null. `campo` = { texto, motivo, observacao }.
 */
export function errosDaPerda(unidade, campo) {
  const erros = { quantidade: null, motivo: null, observacao: null }
  const q = lerQuantidade(campo.texto)
  const decimais = String(campo.texto ?? '').trim().replace(',', '.').split('.')[1] ?? ''
  if (q === null) erros.quantidade = 'Informe quanto foi perdido, como 3 ou 1,5.'
  else if (q <= 0) erros.quantidade = 'A quantidade tem de ser maior que zero.'
  else if (unidadeCurta(unidade) === 'un' && !Number.isInteger(q)) erros.quantidade = 'Produto contado por unidade: informe um número inteiro.'
  else if (decimais.length > 3) erros.quantidade = 'Use no máximo 3 casas depois da vírgula.'
  if (!campo.motivo) erros.motivo = 'Escolha o motivo.'
  const obs = (campo.observacao ?? '').trim()
  if (campo.motivo === 'outro' && !obs) erros.observacao = 'Com o motivo "Outro", escreva numa linha o que aconteceu.'
  else if (obs.length > TAMANHO_OBSERVACAO) erros.observacao = `A observação pode ter até ${TAMANHO_OBSERVACAO} caracteres.`
  return erros
}

export function temErro(erros) {
  return Object.values(erros).some(Boolean)
}

/** Corpo da API a partir do formulário. */
export function montarCorpo(campo) {
  const observacao = (campo.observacao ?? '').trim()
  return {
    quantidade: String(lerQuantidade(campo.texto)),
    motivo: campo.motivo,
    observacao: observacao || null,
  }
}
