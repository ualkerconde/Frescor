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

/** 5242880 -> "5 MB"; 1536 -> "1,5 KB". */
export function formatarTamanho(bytes: number): string {
  const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 })
  if (bytes < 1024) return `${numero.format(bytes)} bytes`
  if (bytes < 1024 * 1024) return `${numero.format(bytes / 1024)} KB`
  return `${numero.format(bytes / (1024 * 1024))} MB`
}
