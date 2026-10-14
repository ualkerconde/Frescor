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
