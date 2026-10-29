import { describe, expect, it } from 'vitest'
import { erroDoItem, formatarQuantidade, lerQuantidade, montarDiferencas, textoInicial } from './regras'

const kg = { id: 1, unidade: 'KG', quantidade_expedida: '18.200' }
const un = { id: 2, unidade: 'UN', quantidade_expedida: '24.000' }

describe('regras do recebimento', () => {
  it('formata no padrão da loja', () => {
    expect(formatarQuantidade('18.200', 'KG')).toBe('18,2 kg')
    expect(formatarQuantidade('1240.000', 'UN')).toBe('1.240 un')
    expect(textoInicial('1240.500')).toBe('1240,5')
  })

  it('lê vírgula ou ponto e recusa texto', () => {
    expect(lerQuantidade('16,5')).toBe(16.5)
    expect(lerQuantidade(' 3 ')).toBe(3)
    expect(lerQuantidade('')).toBeNull()
    expect(lerQuantidade('abc')).toBeNull()
  })

  it('confere cada item como o backend (D78, D91)', () => {
    const campo = (texto, motivo = null, observacao = '') => ({ texto, motivo, observacao })
    expect(erroDoItem(kg, campo('18,2'))).toBeNull()
    expect(erroDoItem(kg, campo(''))).toMatch(/Informe quanto chegou/)
    expect(erroDoItem(kg, campo('-1', 'falta'))).toMatch(/negativa/)
    expect(erroDoItem(kg, campo('1,2345', 'falta'))).toMatch(/3 casas/)
    expect(erroDoItem(un, campo('20,5', 'falta'))).toMatch(/inteiro/)
    expect(erroDoItem(kg, campo('16'))).toMatch(/escolha o motivo/)
    expect(erroDoItem(kg, campo('16', 'outro', '  '))).toMatch(/descreva/)
    expect(erroDoItem(kg, campo('16', 'avaria'))).toBeNull()
    expect(erroDoItem(kg, campo('0', 'falta'))).toBeNull()
  })

  it('manda só os itens diferentes, com o número em texto', () => {
    const campos = {
      1: { texto: '18,2', motivo: null, observacao: '' },
      2: { texto: '26', motivo: 'a_mais', observacao: ' ' },
    }
    expect(montarDiferencas([kg, un], campos)).toEqual([
      { item_id: 2, quantidade_recebida: '26', motivo: 'a_mais', observacao: null },
    ])
  })
})
