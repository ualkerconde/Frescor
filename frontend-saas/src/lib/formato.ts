/*
 * Formatos pt-BR da skill Frescor: "1.240 un", "18,5 kg", "14/10/2026".
 */

const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })

/** 1232 -> "1.232" */
export function formatarInteiro(valor: number): string {
  return inteiro.format(valor)
}

/** Número com a palavra no singular ou no plural: (1, "linha", "linhas") -> "1 linha". */
export function contar(valor: number, singular: string, plural: string): string {
  return `${formatarInteiro(valor)} ${valor === 1 ? singular : plural}`
}

const quantidade = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 3 })

/**
 * Quantidade com a unidade (skill: nunca número sem unidade):
 * ("171.000", "UN") -> "171 un"; ("3.750", "KG") -> "3,75 kg".
 */
export function formatarQuantidade(valor: string | number, unidade: "UN" | "KG"): string {
  return `${quantidade.format(Number(valor))} ${unidade === "KG" ? "kg" : "un"}`
}

const previsaoUn = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 })
const previsaoKg = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 })

/**
 * Número previsto para exibir: o backend grava 4 casas (D21, sem
 * arredondar); na tela, 1 casa em UN e 2 em KG bastam para ler.
 * ("44.1234", "UN") -> "44,1 un"; ("25.4567", "KG") -> "25,46 kg".
 */
export function formatarPrevisao(valor: string | number, unidade: "UN" | "KG"): string {
  const n = Number(valor)
  return unidade === "KG" ? `${previsaoKg.format(n)} kg` : `${previsaoUn.format(n)} un`
}

const percentual = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 })

/** Fração -> percentual: "0.0960" -> "9,6%"; "-0.03" -> "-3%". */
export function formatarPercentual(fracao: string | number): string {
  return percentual.format(Number(fracao))
}

/**
 * Fator -> variação em % arredondada: "1.10" -> "+10%"; "0.85" -> "-15%";
 * "1.004" -> "0%".
 */
export function formatarVariacao(fator: string | number): string {
  const pontos = Math.round((Number(fator) - 1) * 100)
  if (pontos === 0) return "0%"
  return `${pontos > 0 ? "+" : "−"}${formatarInteiro(Math.abs(pontos))}%`
}

const DIAS_SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"]
const DIAS_SEMANA_PLURAL = ["domingos", "segundas", "terças", "quartas", "quintas", "sextas", "sábados"]

function diaDaSemanaIndice(iso: string): number {
  const [a, m, d] = iso.slice(0, 10).split("-").map(Number)
  return new Date(Date.UTC(a, m - 1, d)).getUTCDay()
}

/** "2026-10-14" -> "terça" (ou "terças" no plural), sem erro de fuso. */
export function diaDaSemana(iso: string, plural = false): string {
  return (plural ? DIAS_SEMANA_PLURAL : DIAS_SEMANA)[diaDaSemanaIndice(iso)]
}

/** Soma dias a uma data ISO: ("2026-10-14", -7) -> "2026-10-07". */
export function somarDias(iso: string, dias: number): string {
  const [a, m, d] = iso.slice(0, 10).split("-").map(Number)
  const data = new Date(Date.UTC(a, m - 1, d + dias))
  return data.toISOString().slice(0, 10)
}

/** "2026-09-01" -> "01/09/2026", sem passar por Date (evita erro de fuso horário). */
export function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-")
  return `${dia}/${mes}/${ano}`
}

/** Date local -> "AAAA-MM-DD" (para a API e para <input type="date">). */
export function dataIso(data: Date): string {
  const mes = String(data.getMonth() + 1).padStart(2, "0")
  const dia = String(data.getDate()).padStart(2, "0")
  return `${data.getFullYear()}-${mes}-${dia}`
}

/** Dias do período, contando o primeiro e o último ("2026-09-01", "2026-09-07") -> 7. */
export function diasNoPeriodo(inicioIso: string, fimIso: string): number {
  const utc = (iso: string) => {
    const [a, m, d] = iso.split("-").map(Number)
    return Date.UTC(a, m - 1, d)
  }
  return Math.round((utc(fimIso) - utc(inicioIso)) / 86_400_000) + 1
}

/** 5242880 -> "5 MB"; 1536 -> "1,5 KB". */
export function formatarTamanho(bytes: number): string {
  const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 })
  if (bytes < 1024) return `${numero.format(bytes)} bytes`
  if (bytes < 1024 * 1024) return `${numero.format(bytes / 1024)} KB`
  return `${numero.format(bytes / (1024 * 1024))} MB`
}
