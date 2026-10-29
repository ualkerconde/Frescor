/**
 * Contas e validações da tela de Recebimento (Fase 5 / E11). Espelham as
 * regras do backend (D78, D91) só para avisar o operador antes de enviar;
 * quem decide continua sendo o backend.
 */

export const MOTIVOS = [
  { valor: 'falta', rotulo: 'Faltou' },
  { valor: 'avaria', rotulo: 'Avaria' },
  { valor: 'a_mais', rotulo: 'Veio a mais' },
  { valor: 'outro', rotulo: 'Outro' },
]

const numero = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 })

/** A API manda "KG"/"UN"; na tela vai minúsculo, como no SaaS ("18,5 kg"). */
export function unidadeCurta(unidade) {
  return String(unidade).toLowerCase()
}

/** "18.200" + "KG" -> "18,2 kg"; "24.000" + "UN" -> "24 un". */
export function formatarQuantidade(valor, unidade) {
  return `${numero.format(Number(valor))} ${unidadeCurta(unidade)}`
}

/** Data "2026-10-28" -> "28/10". */
export function formatarDia(iso) {
  const [, mes, dia] = iso.split('-')
  return `${dia}/${mes}`
}

/** Data e hora em UTC sem fuso (como o backend grava) -> hora local "06:15". */
export function formatarHora(isoUtc) {
  const texto = /Z$|[+-]\d\d:\d\d$/.test(isoUtc) ? isoUtc : `${isoUtc}Z`
  return new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(new Date(texto))
}

/** Texto digitado ("18,5") -> número, ou null se não for número. */
export function lerQuantidade(texto) {
  const limpo = String(texto ?? '').trim().replace(',', '.')
  if (limpo === '' || !/^-?\d*\.?\d+$/.test(limpo)) return null
  return Number(limpo)
}

/** Valor inicial do campo: o enviado, no formato da loja ("18,2"). */
export function textoInicial(valor) {
  return numero.format(Number(valor)).replace(/\./g, '')
}

/**
 * Confere um item no modo "com diferença". Devolve o erro (texto) ou null.
 * `campo` = { texto, motivo, observacao }.
 */
export function erroDoItem(item, campo) {
  const q = lerQuantidade(campo.texto)
  if (q === null) return 'Informe quanto chegou.'
  if (q < 0) return 'A quantidade não pode ser negativa.'
  if (unidadeCurta(item.unidade) === 'un' && !Number.isInteger(q)) return 'Produto vendido por unidade: informe um número inteiro.'
  const decimais = String(campo.texto).trim().replace(',', '.').split('.')[1] ?? ''
  if (decimais.length > 3) return 'Informe no máximo 3 casas decimais.'
  if (q === Number(item.quantidade_expedida)) return null
  if (!campo.motivo) return 'Chegou diferente do enviado: escolha o motivo.'
  if (campo.motivo === 'outro' && !campo.observacao?.trim()) return 'Com o motivo "Outro", descreva o que aconteceu.'
  if ((campo.observacao ?? '').length > 255) return 'A descrição pode ter no máximo 255 caracteres.'
  return null
}

/** Itens que chegaram diferentes, no formato da API (só esses vão no corpo, D91). */
export function montarDiferencas(itens, campos) {
  return itens
    .filter((item) => lerQuantidade(campos[item.id].texto) !== Number(item.quantidade_expedida))
    .map((item) => {
      const campo = campos[item.id]
      const observacao = campo.observacao?.trim()
      return {
        item_id: item.id,
        quantidade_recebida: String(lerQuantidade(campo.texto)),
        motivo: campo.motivo,
        observacao: observacao ? observacao : null,
      }
    })
}
