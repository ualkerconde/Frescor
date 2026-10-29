import { describe, expect, it } from 'vitest'
import { produtoDetalhe } from '@/test/cadastros'
import { camposDoProduto, camposVazios, descreverDias, montarEnvio } from './formularioProduto'

describe('modelo do formulário de produto (C4)', () => {
  it('novo: nome e código obrigatórios (D97)', () => {
    const r = montarEnvio(camposVazios(), true)
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.erros.nome).toBe('Informe o nome do produto.')
      expect(r.erros.codigo).toMatch(/^Informe o código/)
    }
  })

  it('converte vírgula, ordena os dias e marca o sazonal com as duas flags (D105)', () => {
    const r = montarEnvio(
      {
        ...camposVazios(), nome: ' Panetone ', codigo: 'PAN', unidade: 'KG', peso_medio_kg: '0,5', margem: '12,5',
        dias_validade: '20', vigencia: 'sazonal', inicio: '2026-11-01', fim: '2027-01-06', dias: ['sexta', 'segunda'],
        setor_id: '2',
      },
      true,
    )
    expect(r).toEqual({
      ok: true,
      envio: {
        nome: 'Panetone', codigo: 'PAN', codigo_barras: null, unidade_medida: 'KG', peso_medio_kg: '0.5', ativo: true,
        tipo_abastecimento: 'produzido', dias_validade: 20, margem_maxima_percentual: '12.5',
        data_inicio_vigencia: '2026-11-01', data_fim_vigencia: '2027-01-06', vigencia_recorrente: true,
        ciclo_previsao: 'sazonal', setor_producao_id: 2, dias_producao: ['segunda', 'sexta'], habilitar_lojas: true,
      },
    })
  })

  it('peso médio só vai em KG; permanente não manda datas', () => {
    const r = montarEnvio({ ...camposVazios(), nome: 'x', codigo: 'x', peso_medio_kg: '0,5', inicio: '2026-01-01' }, true)
    expect(r.ok && r.envio.peso_medio_kg).toBe(null)
    expect(r.ok && r.envio.data_inicio_vigencia).toBe(null)
  })

  it('confere faixas: validade, margem, peso, datas', () => {
    const r = montarEnvio(
      {
        ...camposVazios(), nome: 'x', codigo: 'x', unidade: 'KG', peso_medio_kg: '0', dias_validade: '400',
        margem: '10,123', vigencia: 'temporario', inicio: '2026-12-10', fim: '2026-12-01',
      },
      true,
    )
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.erros.peso_medio_kg).toBe('O peso médio deve ser maior que zero.')
      expect(r.erros.dias_validade).toBe('Informe de 1 a 365 dias, ou deixe vazio.')
      expect(r.erros.margem).toBe('Informe no máximo 2 casas decimais.')
      expect(r.erros.fim).toBe('A data final não pode ser antes da inicial.')
    }
    const sazonal = montarEnvio({ ...camposVazios(), nome: 'x', codigo: 'x', vigencia: 'sazonal', inicio: '2026-12-01' }, true)
    expect(!sazonal.ok && sazonal.erros.fim).toBe('Informe o fim da temporada.')
  })

  it('edição: código existente não pode ser apagado; produto antigo sem código pode ficar sem', () => {
    const comCodigo = montarEnvio({ ...camposVazios(), nome: 'x', codigo: '' }, false, 'INT-007')
    expect(!comCodigo.ok && comCodigo.erros.codigo).toMatch(/^Informe o código/)
    const semCodigo = montarEnvio({ ...camposVazios(), nome: 'x', codigo: '' }, false, null)
    expect(semCodigo.ok).toBe(true)
    expect(semCodigo.ok && 'codigo' in semCodigo.envio).toBe(false)
    expect(semCodigo.ok && 'habilitar_lojas' in semCodigo.envio).toBe(false)
  })

  it('cadastro da API vira campos e volta igual', () => {
    const p = produtoDetalhe({ margem_maxima_percentual: '15.50', data_fim_vigencia: '2026-12-31' })
    const c = camposDoProduto(p)
    expect(c).toMatchObject({ peso_medio_kg: '0,05', margem: '15,5', vigencia: 'temporario', setor_id: '1', dias_validade: '1' })
    const r = montarEnvio(c, false, p.codigo)
    expect(r.ok && r.envio).toMatchObject({
      peso_medio_kg: '0.05', margem_maxima_percentual: '15.5', data_fim_vigencia: '2026-12-31', setor_producao_id: 1,
      dias_producao: ['segunda', 'quarta'],
    })
  })

  it('descreve os dias de produção', () => {
    expect(descreverDias([])).toBe('nenhum dia')
    expect(descreverDias(camposVazios().dias)).toBe('todos os dias')
    expect(descreverDias(['sexta'])).toBe('sexta')
    expect(descreverDias(['sexta', 'segunda', 'quarta'])).toBe('segunda, quarta e sexta')
  })
})
