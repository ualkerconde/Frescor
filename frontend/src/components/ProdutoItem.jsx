import React, { useRef } from 'react'

const s = {
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '13px 16px',
    background: '#fff',
    borderBottom: '1px solid #F0F0F0',
    borderLeft: '3px solid transparent',
    transition: 'border-left-color 0.15s',
  },
  itemCounted: { borderLeftColor: '#22C55E' },
  itemPending: { borderLeftColor: '#F59E0B' },
  info: { flex: 1, minWidth: 0 },
  name: {
    fontSize: 14,
    fontWeight: 500,
    color: '#1A1A1A',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  meta: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 2, flexWrap: 'wrap' },
  unit: {
    fontSize: 11,
    color: '#9CA3AF',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  // Badge do código interno — discreto, estilo "etiqueta"
  codigo: {
    fontSize: 11,
    color: '#6B6B6B',
    background: '#F3F4F6',
    borderRadius: 4,
    padding: '1px 5px',
    fontFamily: 'monospace',
  },
  calc: { fontSize: 11, color: '#6B6B6B' },
  classificacao: {
    fontSize: 11,
    color: '#9CA3AF',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  input: {
    width: 72,
    padding: '8px 6px',
    border: '1.5px solid #E5E5E5',
    borderRadius: 8,
    fontSize: 18,
    fontWeight: 600,
    fontFamily: 'inherit',
    textAlign: 'center',
    color: '#1A1A1A',
    background: '#fff',
    outline: 'none',
    transition: 'border-color 0.15s, background 0.15s, color 0.15s',
    MozAppearance: 'textfield',
  },
  inputHasValue: {
    borderColor: '#22C55E',
    background: '#F0FDF4',
    color: '#15803D',
  },
  inputGroup: { display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'center' },
  inputLabel: { fontSize: 9, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.05em' },
  pesoInput: {
    width: 72,
    padding: '8px 6px',
    border: '1.5px solid #E5E5E5',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    fontFamily: 'inherit',
    textAlign: 'center',
    color: '#1A1A1A',
    background: '#fff',
    outline: 'none',
    transition: 'border-color 0.15s, background 0.15s, color 0.15s',
  },
  pesoInputMissing: {
    borderColor: '#F59E0B',
  },
}

export function ProdutoItem({ produto, quantidade, pesoInformadoKg, isPending, onQtyChange, onFocusNext }) {
  const inputRef = useRef(null)
  const pesoRef = useRef(null)
  const requerPeso = !!produto.requer_peso_informado

  const pesoAtual = pesoInformadoKg != null ? Number(pesoInformadoKg) : null
  const hasValue = requerPeso ? pesoAtual != null && pesoAtual > 0 : quantidade > 0

  const borderStyle = isPending ? s.itemPending : hasValue ? s.itemCounted : {}
  const inputStyle = { ...s.input, ...(hasValue && !requerPeso ? s.inputHasValue : {}) }
  const pesoInputStyle = {
    ...s.pesoInput,
    ...(hasValue ? s.inputHasValue : {}),
    ...(requerPeso && quantidade > 0 && !hasValue ? s.pesoInputMissing : {}),
  }

  function emitirMudanca() {
    if (requerPeso) {
      // Cenário 3 (KG sem peso médio): só o peso é editável. A quantidade
      // não carrega informação própria aqui — é inferida automaticamente
      // (1 quando um peso é informado, 0 quando o campo é limpo).
      const peso = Math.max(0, parseFloat(pesoRef.current?.value) || 0) || null
      onQtyChange(produto.id, peso ? 1 : 0, peso)
      return
    }
    const qtd = Math.max(0, parseInt(inputRef.current?.value) || 0)
    onQtyChange(produto.id, qtd, null)
  }

  function handleBlur() {
    emitirMudanca()
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') { e.target.blur(); onFocusNext() }
  }

  // Estoque calculado em KG — só mostra se já tem valor lançado
  let calcLabel = null
  if (produto.unidade_medida === 'KG' && hasValue) {
    const calc = parseFloat(produto.estoque_atual_calculado) || 0
    if (calc > 0) calcLabel = <span style={s.calc}>{calc.toFixed(2)} kg</span>
  }

  // Trilha de classificação (ex.: "Panificados > Pães"), configurada por
  // negócio e já vindo ordenada do backend (do nível mais genérico ao
  // mais específico). Ausente quando o negócio não configurou níveis ou
  // o produto não foi classificado.
  const trilhaClassificacao = (produto.classificacao || []).map(c => c.valor).join(' > ')

  return (
    <div style={{ ...s.item, ...borderStyle }}>
      <div style={s.info}>
        <div style={s.name}>{produto.nome}</div>
        <div style={s.meta}>
          <span style={s.unit}>{produto.unidade_medida}</span>
          {/* Código interno — exibido como badge discreto abaixo do nome */}
          {produto.codigo && (
            <span style={s.codigo}>{produto.codigo}</span>
          )}
          {requerPeso && <span style={s.calc}>peso na contagem</span>}
          {calcLabel}
        </div>
        {trilhaClassificacao && (
          <div style={s.classificacao} title={trilhaClassificacao}>{trilhaClassificacao}</div>
        )}
      </div>
      {!requerPeso && (
        <input
          ref={inputRef}
          type="number"
          inputMode="numeric"
          pattern="[0-9]*"
          style={inputStyle}
          defaultValue={quantidade || ''}
          placeholder="0"
          min="0"
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          onFocus={e => e.target.select()}
          aria-label={`Quantidade de ${produto.nome}`}
        />
      )}
      {requerPeso && (
        <div style={s.inputGroup}>
          <span style={s.inputLabel}>kg</span>
          <input
            ref={pesoRef}
            type="number"
            inputMode="decimal"
            step="0.001"
            style={pesoInputStyle}
            defaultValue={pesoAtual || ''}
            placeholder="0.000"
            min="0"
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
            onFocus={e => e.target.select()}
            aria-label={`Peso pesado de ${produto.nome} em kg`}
          />
        </div>
      )}
    </div>
  )
}

