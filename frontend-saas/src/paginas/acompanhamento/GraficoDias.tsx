/*
 * Previsto × vendido por dia (D116), em SVG simples (o projeto não usa
 * biblioteca de gráfico).
 *
 * Regras da skill de dataviz:
 * - Duas séries de identidade: previsto (azul) e vendido (laranja), par
 *   validado com o validate_palette (CVD ΔE 24,7, contraste ≥ 3:1 no branco).
 *   A marca (#0E6B5C) reprova no piso de croma para série: fica para a UI.
 * - Um eixo só (mesma unidade), linhas de 2px, marcadores de 8px, grade
 *   recessiva, legenda sempre presente e rótulo direto no último ponto.
 * - Passar o mouse (ou o dedo) mostra a linha vertical e o valor do dia.
 * - A tabela do dia a dia, logo abaixo, é a visão em tabela.
 * Dia sem registro fica sem ponto (não vira zero).
 */
import { useId, useState } from "react"
import { diaDaSemana, formatarData, formatarPrevisao } from "@/lib/formato"
import type { Unidade } from "@/lib/api/tipos"

export const COR_PREVISTO = "#2a78d6"
export const COR_VENDIDO = "#eb6834"

interface Ponto {
  data: string
  previsto: number | null
  vendido: number | null
}

const LARGURA = 720
const ALTURA = 240
const M = { topo: 16, direita: 72, base: 32, esquerda: 48 }

function passo(maximo: number): number {
  if (maximo <= 0) return 1
  const bruto = maximo / 4
  const potencia = 10 ** Math.floor(Math.log10(bruto))
  const n = bruto / potencia
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * potencia
}

export function GraficoDias({ pontos, unidade, titulo }: { pontos: Ponto[]; unidade: Unidade; titulo: string }) {
  const id = useId()
  const [ativo, setAtivo] = useState<number | null>(null)
  const valores = pontos.flatMap((p) => [p.previsto, p.vendido]).filter((v): v is number => v !== null)
  const maximo = Math.max(1, ...valores)
  const intervalo = passo(maximo)
  const topo = Math.ceil(maximo / intervalo) * intervalo
  const marcas = Array.from({ length: Math.round(topo / intervalo) + 1 }, (_, i) => i * intervalo)
  const largura = LARGURA - M.esquerda - M.direita
  const altura = ALTURA - M.topo - M.base
  const x = (i: number) => M.esquerda + (pontos.length === 1 ? largura / 2 : (i * largura) / (pontos.length - 1))
  const y = (v: number) => M.topo + altura - (v / topo) * altura
  const fmt = (v: number) => formatarPrevisao(v, unidade)

  function caminho(serie: "previsto" | "vendido"): string {
    let d = ""
    let aberto = false
    pontos.forEach((p, i) => {
      const v = p[serie]
      if (v === null) {
        aberto = false
        return
      }
      d += `${aberto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`
      aberto = true
    })
    return d
  }

  function ultimo(serie: "previsto" | "vendido"): { i: number; v: number } | null {
    for (let i = pontos.length - 1; i >= 0; i--) {
      const v = pontos[i][serie]
      if (v !== null) return { i, v }
    }
    return null
  }

  function aoMover(evento: React.PointerEvent<SVGSVGElement>) {
    const caixa = evento.currentTarget.getBoundingClientRect()
    const px = ((evento.clientX - caixa.left) / caixa.width) * LARGURA
    let melhor = 0
    pontos.forEach((_, i) => {
      if (Math.abs(x(i) - px) < Math.abs(x(melhor) - px)) melhor = i
    })
    setAtivo(melhor)
  }

  const rotulos = (["previsto", "vendido"] as const).map((s) => ({ s, u: ultimo(s) }))
  // Rótulos diretos no fim da linha; se colidirem, o de cima sobe.
  const yRotulo: Record<string, number> = {}
  for (const { s, u } of rotulos) if (u) yRotulo[s] = y(u.v)
  if (yRotulo.previsto !== undefined && yRotulo.vendido !== undefined && Math.abs(yRotulo.previsto - yRotulo.vendido) < 14) {
    const [cima, baixo] = yRotulo.previsto <= yRotulo.vendido ? ["previsto", "vendido"] : ["vendido", "previsto"]
    const meio = (yRotulo[cima] + yRotulo[baixo]) / 2
    yRotulo[cima] = meio - 7
    yRotulo[baixo] = meio + 7
  }

  const pontoAtivo = ativo === null ? null : pontos[ativo]
  const resumo = `${titulo}: ${pontos.length} dias. Valores dia a dia na tabela abaixo.`
  const cada = Math.max(1, Math.ceil(pontos.length / 8))

  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-semibold">{titulo}</span>
        <span className="flex items-center gap-4 text-sm text-muted-foreground" aria-hidden="true">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded-full" style={{ background: COR_PREVISTO }} />
            Previsto
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded-full" style={{ background: COR_VENDIDO }} />
            Vendido
          </span>
        </span>
      </figcaption>
      <div className="relative">
        <svg
          viewBox={`0 0 ${LARGURA} ${ALTURA}`}
          className="h-auto w-full touch-none"
          role="img"
          aria-labelledby={`${id}-resumo`}
          onPointerMove={aoMover}
          onPointerDown={aoMover}
          onPointerLeave={() => setAtivo(null)}
        >
          <title id={`${id}-resumo`}>{resumo}</title>
          {marcas.map((m) => (
            <g key={m}>
              <line x1={M.esquerda} x2={LARGURA - M.direita} y1={y(m)} y2={y(m)} stroke="var(--fr-line)" strokeWidth={1} />
              <text x={M.esquerda - 8} y={y(m)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--fr-muted)">
                {new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(m)}
              </text>
            </g>
          ))}
          {pontos.map((p, i) =>
            i % cada === 0 || i === pontos.length - 1 ? (
              <text key={p.data} x={x(i)} y={ALTURA - 10} textAnchor="middle" fontSize={11} fill="var(--fr-muted)">
                {formatarData(p.data).slice(0, 5)}
              </text>
            ) : null,
          )}
          {pontoAtivo && ativo !== null && (
            <line x1={x(ativo)} x2={x(ativo)} y1={M.topo} y2={M.topo + altura} stroke="var(--fr-input-border)" strokeWidth={1} />
          )}
          {(["previsto", "vendido"] as const).map((s) => {
            const cor = s === "previsto" ? COR_PREVISTO : COR_VENDIDO
            return (
              <g key={s}>
                <path d={caminho(s)} fill="none" stroke={cor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                {pontos.map((p, i) => {
                  const v = p[s]
                  if (v === null) return null
                  const grande = ativo === i
                  return (
                    <circle key={p.data} cx={x(i)} cy={y(v)} r={grande ? 5 : 4} fill={cor} stroke="#fff" strokeWidth={2} />
                  )
                })}
              </g>
            )
          })}
          {rotulos.map(({ s, u }) =>
            u ? (
              <text key={s} x={x(u.i) + 10} y={yRotulo[s]} dy="0.32em" fontSize={12} fill="var(--fr-text)">
                {s === "previsto" ? "Previsto" : "Vendido"}
              </text>
            ) : null,
          )}
        </svg>
        {pontoAtivo && ativo !== null && (
          <div
            className="pointer-events-none absolute top-0 z-10 min-w-40 rounded-lg border bg-card p-3 text-sm shadow-elevado"
            style={{
              left: `${(x(ativo) / LARGURA) * 100}%`,
              transform: x(ativo) > LARGURA / 2 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
            }}
          >
            <p className="font-semibold">
              {diaDaSemana(pontoAtivo.data)}, {formatarData(pontoAtivo.data)}
            </p>
            <p className="mt-1 flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: COR_PREVISTO }} />
                Previsto
              </span>
              <span className="numero">{pontoAtivo.previsto === null ? "—" : fmt(pontoAtivo.previsto)}</span>
            </p>
            <p className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: COR_VENDIDO }} />
                Vendido
              </span>
              <span className="numero">{pontoAtivo.vendido === null ? "—" : fmt(pontoAtivo.vendido)}</span>
            </p>
          </div>
        )}
      </div>
    </figure>
  )
}
