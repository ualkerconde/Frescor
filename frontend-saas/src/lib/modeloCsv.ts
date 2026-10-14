/*
 * Modelo de CSV para o gestor baixar (passo W6), no formato da decisão D7:
 * separador ";", vírgula decimal, data dd/mm/aaaa, loja e produto pelo
 * código. Gravado em UTF-8 COM BOM: assim o Excel em português abre com os
 * acentos certos e já separa as colunas pelo ";".
 */
import type { TipoImportacao } from "@/lib/api/tipos"

export const CABECALHO_CSV = "data;codigo_loja;codigo_produto;quantidade"

const EXEMPLOS: Record<TipoImportacao, string[]> = {
  vendas: ["01/10/2026;001;INT-007;25,500", "01/10/2026;001;INT-001;40"],
  perdas: ["01/10/2026;001;INT-007;1,250", "01/10/2026;001;INT-001;3"],
}

export function conteudoModeloCsv(tipo: TipoImportacao): string {
  return "﻿" + [CABECALHO_CSV, ...EXEMPLOS[tipo]].join("\r\n") + "\r\n"
}

export function nomeModeloCsv(tipo: TipoImportacao): string {
  return `modelo_${tipo}.csv`
}

/** Dispara o download do modelo no navegador. */
export function baixarModeloCsv(tipo: TipoImportacao): void {
  const blob = new Blob([conteudoModeloCsv(tipo)], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = nomeModeloCsv(tipo)
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
