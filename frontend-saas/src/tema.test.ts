// @vitest-environment node
/*
 * Confere o tema contra a skill Frescor: cada token --fr-* do index.css
 * tem de ter exatamente o valor da tabela de cores da skill (a skill é a
 * fonte da verdade), e os contrastes têm de atingir o mínimo da WCAG.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const raiz = fileURLToPath(new URL('..', import.meta.url))
const css = readFileSync(resolve(raiz, 'src/index.css'), 'utf8')
const skill = readFileSync(resolve(raiz, '../.claude/skills/frescor-design-system/SKILL.md'), 'utf8')

/**
 * Tokens da tabela "Cores do web" da skill: { primary: '#F5B83D', 'success-bg': ... }.
 * Só as linhas que começam com "| `--"; a tabela do app mobile escreve os nomes sem "--".
 */
function tokensDaSkill(): Record<string, string> {
  const tokens: Record<string, string> = {}
  for (const linha of skill.split('\n')) {
    if (!linha.startsWith('| `--')) continue
    const [nomes, valores] = linha.split('|').slice(1, 3).map((c) => c.trim())
    const listaNomes = [...nomes.matchAll(/`--([a-z-]+)`/g)].map((m) => m[1])
    const listaValores = [...valores.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toLowerCase())
    listaNomes.forEach((n, i) => (tokens[n] = listaValores[i]))
  }
  return tokens
}

function tokenDoCss(nome: string): string | undefined {
  return css.match(new RegExp(`--fr-${nome}:\\s*(#[0-9a-fA-F]{6})`))?.[1].toLowerCase()
}

function luminancia(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contraste(a: string, b: string): number {
  const [l1, l2] = [luminancia(a), luminancia(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

describe('tema x skill Frescor', () => {
  const skillTokens = tokensDaSkill()

  it('a tabela de cores do web foi lida (24 cores do visual Comando, D117)', () => {
    expect(Object.keys(skillTokens)).toHaveLength(24)
  })

  it.each(Object.entries(tokensDaSkill()))('--fr-%s tem o valor da skill (%s)', (nome, valor) => {
    expect(tokenDoCss(nome)).toBe(valor)
  })

  // Tema escuro único (visual Comando): os pares são os que aparecem nas telas.
  const pares: [string, string, string, number][] = [
    ['texto sobre o fundo', 'text', 'bg', 4.5],
    ['texto sobre o card', 'text', 'card', 4.5],
    ['texto sobre surface', 'text', 'surface', 4.5],
    ['texto secundário sobre o fundo', 'muted', 'bg', 4.5],
    ['texto secundário sobre o card', 'muted', 'card', 4.5],
    ['texto secundário sobre surface', 'muted', 'surface', 4.5],
    ['texto secundário sobre a barra lateral', 'ink-muted', 'rail', 4.5],
    ['tinta sobre o primário (botão)', 'on-color', 'primary', 4.5],
    ['tinta sobre o primário (hover)', 'on-color', 'primary-hover', 4.5],
    ['tinta sobre o erro (botão perigo)', 'on-color', 'error', 4.5],
    ['primário (link, número) sobre o fundo', 'primary', 'bg', 4.5],
    ['primário sobre o card', 'primary', 'card', 4.5],
    ['âmbar sobre highlight-bg (badge)', 'accent', 'highlight-bg', 4.5],
    ['sucesso sobre sucesso-bg', 'success', 'success-bg', 4.5],
    ['atenção sobre atenção-bg', 'warning', 'warning-bg', 4.5],
    ['erro sobre erro-bg', 'error', 'error-bg', 4.5],
    ['erro como texto sobre o card', 'error', 'card', 4.5],
    ['título (heading) sobre o fundo', 'secondary', 'bg', 4.5],
    ['azul (dado) sobre o card', 'blue', 'card', 3],
    ['borda de controle sobre o card', 'input-border', 'card', 3],
    ['borda de controle sobre o fundo (campo)', 'input-border', 'bg', 3],
    ['texto sobre primary-soft (item ativo, hover de linha)', 'text', 'primary-soft', 4.5],
    ['texto secundário sobre primary-soft', 'muted', 'primary-soft', 4.5],
    ['primário sobre primary-soft (ícone ativo)', 'primary', 'primary-soft', 4.5],
  ]
  it.each(pares)('contraste: %s', (_rotulo, a, b, minimo) => {
    expect(contraste(skillTokens[a], skillTokens[b])).toBeGreaterThanOrEqual(minimo)
  })

  it('tema escuro único: não há bloco .dark (não há alternância claro/escuro)', () => {
    expect(css).not.toMatch(/\.dark\s*\{/)
  })
})
