import React, { useMemo, useState } from 'react'

/**
 * Filtro por classificação (níveis configurados pelo negócio, ex.:
 * Categoria/Subcategoria, Departamento/Seção...). Os níveis e valores
 * disponíveis são descobertos dinamicamente a partir dos produtos já
 * carregados — nada fixo no código, já que cada negócio configura os
 * seus próprios níveis (até 4).
 *
 * Filtro em cascata: ao selecionar um valor num nível, os valores
 * disponíveis nos demais níveis são recalculados considerando apenas os
 * produtos que já batem com a seleção atual (evita mostrar combinações
 * que resultariam em lista vazia).
 */

const s = {
  wrap: { background: '#fff', borderBottom: '1px solid #E5E5E5', flexShrink: 0 },
  toggleRow: { display: 'flex', alignItems: 'center', padding: '8px 16px', gap: 10 },
  toggleBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    border: '1.5px solid #E5E5E5',
    borderRadius: 20,
    background: '#fff',
    fontSize: 13,
    fontWeight: 500,
    color: '#1A1A1A',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  toggleBtnActive: { borderColor: '#2563EB', color: '#2563EB', background: '#EFF6FF' },
  badge: {
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    background: '#2563EB',
    color: '#fff',
    fontSize: 10,
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 4px',
  },
  clearBtn: {
    fontSize: 12,
    color: '#6B6B6B',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    textDecoration: 'underline',
    fontFamily: 'inherit',
  },
  panel: { padding: '0 16px 12px' },
  nivelRow: { marginBottom: 10 },
  nivelLabel: {
    fontSize: 11,
    color: '#9CA3AF',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: 6,
  },
  chipsRow: { display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 2 },
  chip: {
    flexShrink: 0,
    padding: '6px 12px',
    borderRadius: 16,
    border: '1.5px solid #E5E5E5',
    background: '#fff',
    fontSize: 13,
    color: '#1A1A1A',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    fontFamily: 'inherit',
  },
  chipActive: { background: '#2563EB', borderColor: '#2563EB', color: '#fff' },
}

export function FiltroClassificacao({ produtos, filtros, onChange }) {
  const [aberto, setAberto] = useState(false)

  // Níveis presentes no catálogo, na ordem configurada pelo negócio
  // (backend já entrega produto.classificacao ordenado por nível).
  const niveis = useMemo(() => {
    const mapa = new Map()
    produtos.forEach((p) =>
      (p.classificacao || []).forEach((c) => {
        if (!mapa.has(c.nivel)) mapa.set(c.nivel, c.ordem)
      })
    )
    return [...mapa.entries()].sort((a, b) => a[1] - b[1]).map(([nome]) => nome)
  }, [produtos])

  if (niveis.length === 0) return null

  const totalAtivos = Object.values(filtros).filter(Boolean).length

  // Valores disponíveis para um nível, considerando apenas produtos que já
  // batem com os filtros ativos NOS OUTROS níveis (filtro em cascata).
  function valoresDoNivel(nivel) {
    const outros = Object.entries(filtros).filter(([chave, valor]) => chave !== nivel && valor)
    const base = produtos.filter((p) =>
      outros.every(([chave, valor]) => (p.classificacao || []).some((c) => c.nivel === chave && c.valor === valor))
    )
    const valores = new Set()
    base.forEach((p) =>
      (p.classificacao || []).forEach((c) => {
        if (c.nivel === nivel) valores.add(c.valor)
      })
    )
    return [...valores].sort((a, b) => a.localeCompare(b, 'pt-BR'))
  }

  function toggleValor(nivel, valor) {
    const atual = filtros[nivel]
    const novos = { ...filtros, [nivel]: atual === valor ? undefined : valor }
    onChange(novos)
  }

  return (
    <div style={s.wrap}>
      <div style={s.toggleRow}>
        <button
          style={{ ...s.toggleBtn, ...(totalAtivos > 0 ? s.toggleBtnActive : {}) }}
          onClick={() => setAberto((a) => !a)}
          aria-expanded={aberto}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
          Filtrar
          {totalAtivos > 0 && <span style={s.badge}>{totalAtivos}</span>}
        </button>
        {totalAtivos > 0 && (
          <button style={s.clearBtn} onClick={() => onChange({})}>
            Limpar filtros
          </button>
        )}
      </div>

      {aberto && (
        <div style={s.panel}>
          {niveis.map((nivel) => {
            const valores = valoresDoNivel(nivel)
            if (valores.length === 0) return null
            return (
              <div key={nivel} style={s.nivelRow}>
                <div style={s.nivelLabel}>{nivel}</div>
                <div style={s.chipsRow}>
                  {valores.map((valor) => {
                    const ativo = filtros[nivel] === valor
                    return (
                      <button
                        key={valor}
                        style={{ ...s.chip, ...(ativo ? s.chipActive : {}) }}
                        onClick={() => toggleValor(nivel, valor)}
                      >
                        {valor}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
