/*
 * Quantidade final digitada pelo gestor: aceita vírgula ou ponto como
 * decimal e confere as mesmas regras do backend (D13, N6): não negativa,
 * inteira em UN, até 3 casas em KG. Devolve o texto para a API (ponto).
 */
import type { Unidade } from '@/lib/api/tipos'

export type LeituraQuantidade = { ok: true; valor: string } | { ok: false; erro: string }

export function lerQuantidade(texto: string, unidade: Unidade): LeituraQuantidade {
  const limpo = texto.trim().replace(',', '.')
  if (limpo === '') return { ok: false, erro: 'Informe a quantidade.' }
  if (!/^-?\d+(\.\d+)?$/.test(limpo)) return { ok: false, erro: 'Use só números, por exemplo 12 ou 4,5.' }
  if (limpo.startsWith('-')) return { ok: false, erro: 'A quantidade não pode ser negativa.' }
  const casas = limpo.includes('.') ? limpo.split('.')[1].replace(/0+$/, '').length : 0
  if (unidade === 'UN' && casas > 0) {
    return { ok: false, erro: 'Este produto é vendido por unidade: informe um número inteiro.' }
  }
  if (casas > 3) return { ok: false, erro: 'Informe no máximo 3 casas decimais.' }
  return { ok: true, valor: limpo }
}
