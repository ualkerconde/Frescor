---
name: frescor-design-system
description: Design system do Frescor (direção B). Use ao criar ou alterar qualquer tela, componente ou estilo do frontend-saas ou do app mobile PWA.
---

# Frescor · design system (direção B "Central de produção")

O Frescor é um SaaS de perecíveis para redes de supermercado: padaria, açougue, hortifruti e itens não produzidos. Ele tem duas superfícies:
- **App mobile (PWA):** o operador da loja conta o estoque e lê código de barras no celular, em pé e com pressa.
- **frontend-saas (web):** o gestor da central importa vendas e perdas, vê a previsão, gera ordens de produção, faz o romaneio e acompanha o dashboard.

Os usuários não são de tecnologia. A interface precisa ser usual, bonita e impossível de confundir.

Prévia visual: https://claude.ai/artifact/S9Td8ehP4vgptb7Z1YT9hh

## Stack sugerida
- **Tailwind CSS + shadcn/ui** (Radix por baixo) nos dois frontends React/Vite.
- Os tokens abaixo vão em CSS variables no `:root` e são mapeados no `tailwind.config` (`colors.primary` = `var(--primary)` etc.).
- **Componentes:** use os do shadcn (Button, Input, Card, Table, Alert, Dialog, Toast/Sonner) e ajuste-os aos tokens. Não crie componente próprio quando o shadcn já tem um.
- **Ícones:** lucide-react (vem com o shadcn), com tamanho 20px e traço 2. Use ícone sempre com texto, nunca sozinho, exceto no botão fechar com `aria-label`.

## Cores (hex)
| Token | Hex | Uso |
|---|---|---|
| `--primary` | #0E6B5C | ação principal, links, foco |
| `--primary-hover` | #0A5549 | hover/pressionado do primário |
| `--secondary` | #1B2B3A | títulos, números grandes, barra lateral |
| `--accent` | #E3A62F | destaque, selo, marcador. **Só como fundo** (com texto `--text`), nunca como texto sobre branco |
| `--bg` | #FAFBFA | fundo da página |
| `--surface` | #EEF3F1 | cards, linhas alternadas, áreas agrupadas |
| `--card` | #FFFFFF | card elevado, input, modal |
| `--text` | #15212B | texto principal |
| `--muted` | #56636D | texto secundário, legendas |
| `--line` | #D3DEDA | divisórias decorativas |
| `--input-border` | #7D8A93 | borda de input e checkbox (3:1 exigido) |
| `--success` / `--success-bg` | #1F7A3E / #E8F4EC | enviado, dentro da meta |
| `--warning` / `--warning-bg` | #9A5B00 / #FDF3E1 | pendente, atenção |
| `--error` / `--error-bg` | #B42318 / #FDECEA | erro, perda acima do limite |

Contrastes conferidos (WCAG 2.1): text/bg 15,8 · muted/bg 6,0 · muted/surface 5,5 · branco/primary 6,4 · primary/bg 6,2 · text/accent 7,6 · success/bg 5,2 · warning/bg 5,2 · error/bg 6,3 · branco/error 6,6 · branco/success 5,4 · success/success-bg 4,75 · warning/warning-bg 4,9 · error/error-bg 5,75. Todos AA.

Ao criar uma cor nova, confira o contraste antes de usar: no mínimo 4,5:1 para texto, 3:1 para texto ≥ 24px, ícones e bordas de controle.

Modo escuro ainda não foi definido. Não invente um: só a paleta clara existe por enquanto.

## Tipografia (Google Fonts)
- **Sora** 600/700 para títulos, números de dashboard e o nome Frescor.
- **Source Sans 3** 400/600 para todo o resto.
- Fallback: `system-ui, -apple-system, "Segoe UI", sans-serif`.
- **Escala (px):** 12 legenda · 14 apoio · **16 corpo (mínimo no mobile)** · 18 título de card · 22 título de seção · 28 título de página · 36–48 número de dashboard.
- Números sempre com `font-variant-numeric: tabular-nums`.
- Formato pt-BR: `1.240 un`, `18,5 kg`, `3,8%`, `14/10/2026`. Use `Intl.NumberFormat('pt-BR')`.

## Espaço, raio e sombra
- **Espaçamento:** escala de 4px: 4, 8, 12, 16, 24, 32, 48. Margem lateral mínima de 16px no mobile.
- **Raio:** 10px em botões, inputs e cards; 6px em badges; pill (999px) só em status.
- **Sombra:** só no card elevado e no modal (`0 1px 2px rgb(21 33 43 / .06), 0 4px 12px rgb(21 33 43 / .06)`). O resto é plano, separado por `--surface` ou `--line`.

## Componentes
- **Botão:**
  - altura 44px no web e **48px no mobile**, texto 16px 600;
  - *Primário:* fundo `--primary`, texto branco;
  - *Secundário:* borda 2px `--primary`, texto `--primary`, fundo transparente;
  - *Perigo:* fundo `--error`, texto branco;
  - o rótulo é um verbo do que acontece ("Gerar ordem", "Enviar contagem"), nunca "OK" ou "Confirmar";
  - durante o carregamento, mostre spinner e texto ("Enviando…") e bloqueie o clique duplo.
- **Input:**
  - label visível acima, nunca só placeholder;
  - altura 44/48px, borda 1px `--input-border`, fundo branco;
  - campo de quantidade com `inputmode="decimal"` e a unidade (kg, un) fixa ao lado;
  - erro: borda e mensagem em `--error` abaixo do campo, com ícone.
- **Card:**
  - fundo `--card` ou `--surface`, raio 10, padding 16;
  - título em Sora 18 `--secondary`, com o status (badge) no canto direito.
- **Tabela (web):**
  - cabeçalho 12px maiúsculo `--muted`, linhas de 48px;
  - números alinhados à direita;
  - zebra com `--surface`;
  - no mobile, a tabela vira uma lista de cards.
- **Número de dashboard:**
  - rótulo curto em cima (14px `--muted`);
  - número grande em Sora 36–48 `--secondary`;
  - variação embaixo com seta e cor semântica ("▲ 6% vs. ontem").
  - No máximo 4 números por linha. **Perda subindo é vermelho**, mesmo sendo "para cima".
- **Alerta:**
  - fundo `*-bg`, texto e ícone na cor semântica, raio 10;
  - uma frase do que houve e uma do que fazer;
  - o toast some sozinho só para sucesso; erro fica até a pessoa fechar.
- **Badge de status:** pill 12–14px 600, com fundo `*-bg` e texto na cor semântica. Use `--accent` com texto `--text` para "Em produção".

## Regras de clareza
1. **Uma ação principal por tela.** Só um botão primário visível. As outras ações ficam como secundário ou no menu.
2. **Texto curto em pt-BR, na língua da loja:** "contagem", "perda", "quebra", "romaneio", "ordem de produção". Nada de "sincronizar registro" ou "payload".
3. **Números grandes e com unidade.** Nunca mostre uma quantidade sem `un` ou `kg`.
4. **Erro claro:** diga o que deu errado e como resolver ("Código 789… não encontrado. Confira o produto ou digite o código."). Nada de "Erro 422" na tela. Não peça desculpa.
5. **Estado vazio útil:** diga o que vai aparecer ali e mostre o botão que começa ("Nenhuma venda importada ainda. Importar CSV").
6. **Confirmação só para o que não se desfaz** (apagar, enviar romaneio), em diálogo com o verbo no botão ("Enviar romaneio").
7. **Mobile:**
   - a ação principal fica fixa no rodapé, ao alcance do polegar;
   - leitura de código com feedback imediato: vibração e mensagem verde ou vermelha.
8. **Cor nunca sozinha:** status sempre com texto ou ícone junto.

## Acessibilidade
- Contraste AA em tudo (veja a tabela acima). O `--accent` nunca é texto.
- **Área de toque:** mínimo 44×44px, e **48×48px no app mobile**, com 8px entre os alvos.
- **Foco visível:** anel de 2px `--primary` com 2px de offset (`focus-visible`). Nunca `outline: none` sem substituto.
- `lang="pt-BR"`, labels ligadas aos inputs, `aria-live="polite"` para resultado de leitura e envio.
- Respeite `prefers-reduced-motion`. Animações de no máximo 200ms.

## Marca
- **Nome:** Frescor. O nome do módulo de padaria ("Fornada") e o slogan ("Quebra Zero") ainda não foram confirmados.
- **Logo (conceito):** folha `--primary` cuja nervura é um "certo" `--accent`, ao lado de "Frescor" em Sora 700 `--secondary`.
- INPI e registro.br ainda não foram consultados.
