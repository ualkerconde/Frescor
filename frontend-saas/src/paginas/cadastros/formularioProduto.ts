/*
 * Modelo do formulário de produto (Fase 6 / C4): converte o cadastro da API
 * em campos de texto e de volta, conferindo no navegador as mesmas regras
 * do backend (cadastro_produto_service.py). O backend confere de novo; a
 * mensagem dele aparece se algo escapar daqui.
 *
 * Vigência (D105) vira uma escolha de três: permanente (sem datas),
 * temporário (início e/ou fim, ciclo semanal) e sazonal (as duas datas,
 * repete todo ano: ciclo sazonal + vigência recorrente).
 */
import type { DiaSemana, ProdutoDetalhe, ProdutoEnvio, TipoAbastecimento, Unidade } from '@/lib/api/tipos'

export type Vigencia = 'permanente' | 'temporario' | 'sazonal'

export const DIAS: { valor: DiaSemana; rotulo: string }[] = [
  { valor: 'segunda', rotulo: 'Segunda' },
  { valor: 'terca', rotulo: 'Terça' },
  { valor: 'quarta', rotulo: 'Quarta' },
  { valor: 'quinta', rotulo: 'Quinta' },
  { valor: 'sexta', rotulo: 'Sexta' },
  { valor: 'sabado', rotulo: 'Sábado' },
  { valor: 'domingo', rotulo: 'Domingo' },
]

export interface CamposProduto {
  nome: string
  codigo: string
  codigo_barras: string
  unidade: Unidade
  peso_medio_kg: string
  ativo: boolean
  tipo_abastecimento: TipoAbastecimento
  dias_validade: string
  margem: string
  vigencia: Vigencia
  inicio: string
  fim: string
  setor_id: string
  dias: DiaSemana[]
  habilitar_lojas: boolean
}

export type ErrosProduto = Partial<Record<keyof CamposProduto, string>>

export const SEM_SETOR = 'sem'

export function camposVazios(): CamposProduto {
  return {
    nome: '', codigo: '', codigo_barras: '', unidade: 'UN', peso_medio_kg: '', ativo: true,
    tipo_abastecimento: 'produzido', dias_validade: '', margem: '', vigencia: 'permanente', inicio: '', fim: '',
    setor_id: SEM_SETOR, dias: [], habilitar_lojas: true,
  }
}

function decimalParaCampo(valor: string | null): string {
  if (valor === null) return ''
  return String(Number(valor)).replace('.', ',')
}

export function camposDoProduto(p: ProdutoDetalhe): CamposProduto {
  const vigencia: Vigencia = p.vigencia_recorrente
    ? 'sazonal'
    : p.data_inicio_vigencia || p.data_fim_vigencia
      ? 'temporario'
      : 'permanente'
  return {
    nome: p.nome,
    codigo: p.codigo ?? '',
    codigo_barras: p.codigo_barras ?? '',
    unidade: p.unidade,
    peso_medio_kg: decimalParaCampo(p.peso_medio_kg),
    ativo: p.ativo,
    tipo_abastecimento: p.tipo_abastecimento,
    dias_validade: p.dias_validade === null ? '' : String(p.dias_validade),
    margem: decimalParaCampo(p.margem_maxima_percentual),
    vigencia,
    inicio: p.data_inicio_vigencia ?? '',
    fim: p.data_fim_vigencia ?? '',
    setor_id: p.setor ? String(p.setor.id) : SEM_SETOR,
    dias: p.dias_producao,
    habilitar_lojas: false,
  }
}

function casas(texto: string): number {
  return texto.includes('.') ? texto.split('.')[1].replace(/0+$/, '').length : 0
}

/** Decimal digitado (vírgula ou ponto) -> texto para a API, ou o erro. */
function lerDecimal(texto: string, maxCasas: number): { ok: true; valor: string } | { ok: false; erro: string } {
  const limpo = texto.trim().replace(',', '.')
  if (!/^-?\d+(\.\d+)?$/.test(limpo)) return { ok: false, erro: 'Use só números, por exemplo 12 ou 4,5.' }
  if (casas(limpo) > maxCasas) return { ok: false, erro: `Informe no máximo ${maxCasas} casas decimais.` }
  return { ok: true, valor: limpo }
}

/**
 * Confere os campos e monta o corpo para a API. `novo` = cadastro novo
 * (código obrigatório e a opção de já ativar nas lojas, D97 e D101).
 * `codigoAntigo` = o código que o produto já tinha (não pode ser apagado).
 */
export function montarEnvio(
  c: CamposProduto,
  novo: boolean,
  codigoAntigo: string | null = null,
): { ok: true; envio: ProdutoEnvio } | { ok: false; erros: ErrosProduto } {
  const erros: ErrosProduto = {}
  const nome = c.nome.trim()
  if (!nome) erros.nome = 'Informe o nome do produto.'
  const codigo = c.codigo.trim()
  if (!codigo && (novo || codigoAntigo !== null)) {
    erros.codigo = 'Informe o código. É por ele que a importação de vendas e perdas acha o produto.'
  }

  let peso: string | null = null
  if (c.unidade === 'KG' && c.peso_medio_kg.trim()) {
    const lido = lerDecimal(c.peso_medio_kg, 4)
    if (!lido.ok) erros.peso_medio_kg = lido.erro
    else if (Number(lido.valor) <= 0) erros.peso_medio_kg = 'O peso médio deve ser maior que zero.'
    else peso = lido.valor
  }

  let validade: number | null = null
  if (c.dias_validade.trim()) {
    const texto = c.dias_validade.trim()
    const n = Number(texto)
    if (!/^\d+$/.test(texto) || n < 1 || n > 365) erros.dias_validade = 'Informe de 1 a 365 dias, ou deixe vazio.'
    else validade = n
  }

  let margem: string | null = null
  if (c.margem.trim()) {
    const lido = lerDecimal(c.margem, 2)
    if (!lido.ok) erros.margem = lido.erro
    else if (Number(lido.valor) < 0 || Number(lido.valor) > 500) erros.margem = 'Informe de 0% a 500%, ou deixe vazio.'
    else margem = lido.valor
  }

  let inicio: string | null = null
  let fim: string | null = null
  if (c.vigencia === 'temporario') {
    inicio = c.inicio || null
    fim = c.fim || null
    if (!inicio && !fim) erros.inicio = 'Informe a data de início, a de fim ou as duas.'
    else if (inicio && fim && fim < inicio) erros.fim = 'A data final não pode ser antes da inicial.'
  } else if (c.vigencia === 'sazonal') {
    inicio = c.inicio || null
    fim = c.fim || null
    if (!inicio) erros.inicio = 'Informe o início da temporada.'
    if (!fim) erros.fim = 'Informe o fim da temporada.'
  }

  if (Object.keys(erros).length > 0) return { ok: false, erros }
  const envio: ProdutoEnvio = {
    nome,
    codigo: codigo || null,
    codigo_barras: c.codigo_barras.trim() || null,
    unidade_medida: c.unidade,
    peso_medio_kg: peso,
    ativo: c.ativo,
    tipo_abastecimento: c.tipo_abastecimento,
    dias_validade: validade,
    margem_maxima_percentual: margem,
    data_inicio_vigencia: inicio,
    data_fim_vigencia: fim,
    vigencia_recorrente: c.vigencia === 'sazonal',
    ciclo_previsao: c.vigencia === 'sazonal' ? 'sazonal' : 'semanal',
    setor_producao_id: c.setor_id === SEM_SETOR ? null : Number(c.setor_id),
    dias_producao: DIAS.map((d) => d.valor).filter((d) => c.dias.includes(d)),
  }
  if (novo) envio.habilitar_lojas = c.habilitar_lojas
  // Produto antigo sem código: não manda o campo vazio (o backend aceitaria, mas fica explícito).
  if (!novo && codigoAntigo === null && !codigo) delete (envio as Partial<ProdutoEnvio>).codigo
  return { ok: true, envio }
}

/** "segunda, quarta e sexta"; vazio -> "todos os dias". */
export function descreverDias(dias: DiaSemana[]): string {
  if (dias.length === 0 || dias.length === 7) return 'todos os dias'
  const nomes = DIAS.filter((d) => dias.includes(d.valor)).map((d) => d.rotulo.toLowerCase())
  return nomes.length === 1 ? nomes[0] : `${nomes.slice(0, -1).join(', ')} e ${nomes[nomes.length - 1]}`
}
