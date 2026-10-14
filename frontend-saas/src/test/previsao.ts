/*
 * Itens de previsão para os testes, no formato de GET /previsoes. O padrão é
 * o caso comum: histórico completo, base 40 kg, tendência +10%, previsão 44.
 */
import type { ItemPrevisao } from "@/lib/api/tipos"

export function itemPrevisao(parcial: Partial<ItemPrevisao> = {}): ItemPrevisao {
  return {
    data: "2026-10-14", // quarta-feira
    loja: { id: 1, codigo: "001", nome: "Loja Centro" },
    produto: { id: 17, codigo: "INT-007", nome: "Pão Francês" },
    unidade: "KG",
    previsao: "44.0000",
    previsao_sem_evento: "44.0000",
    previsao_propria: "44.0000",
    venda_semana_passada: "41.500",
    metodo: "semanal",
    estatistica: "mediana",
    base: "40.0000",
    semanas_na_base: 6,
    tendencia: "1.1000",
    tendencia_bruta: "1.1000",
    dias_na_tendencia: 7,
    inicio_historico: "2026-08-01",
    peso_historico: "1.0000",
    pouco_historico: false,
    proxy: null,
    origem_proxy: null,
    eventos: [],
    data_referencia: "2026-10-13",
    gerado_em: "2026-10-14T09:30:00",
    versao_metodo: "2026.10-v2",
    ...parcial,
  }
}
