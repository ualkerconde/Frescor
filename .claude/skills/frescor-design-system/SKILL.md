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
| `--ink` | #0F1B25 | fim do degradê das superfícies escuras (barra lateral, painel do login) |
| `--ink-muted` | #A9B7C1 | texto secundário **sobre superfície escura** |
| `--ink-line` | #2C3E4D | divisória decorativa sobre superfície escura |
| `--mint` | #6FD6BD | realce (texto, ícone, brilho) **só sobre superfície escura**; nunca sobre claro |
| `--primary-soft` | #E2F0EC | hover de linha de tabela, seleção de texto |

Contrastes conferidos (WCAG 2.1): text/bg 15,8 · muted/bg 6,0 · muted/surface 5,5 · branco/primary 6,4 · primary/bg 6,2 · text/accent 7,6 · success/bg 5,2 · warning/bg 5,2 · error/bg 6,3 · branco/error 6,6 · branco/success 5,4 · success/success-bg 4,75 · warning/warning-bg 4,9 · error/error-bg 5,75. Superfície escura: branco/ink 17,4 · ink-muted/secondary 7,0 · accent/secondary 6,7 · mint/secondary 8,3. Claro: text/primary-soft 13,9 · muted/primary-soft 5,3. Todos AA.

### Superfícies escuras (desde 28/10/2026)
A barra lateral do web e o painel de marca do login usam um degradê `--secondary` → `--ink`, com trama de pontos branca a 7% e um brilho `--primary` desfocado. Ali:
- texto principal branco, secundário `--ink-muted`;
- o `--accent` (dourado) **pode** ser texto, ícone e marcador (6,7:1), por exemplo o item de menu atual;
- `--mint` é o realce verde (status "ok", foco visível no lugar do `--primary`).
Isso não é modo escuro: o conteúdo das telas continua só na paleta clara.

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
- **Raio:** 10px em botões, inputs e cards pequenos; **16px nos painéis** (blocos de filtro, formulário, tabela, KPI, modal); 6px em badges; pill (999px) só em status.
- **Sombra:** em camadas, nunca uma sombra preta pesada.
  - painel (`painel`, `painel-kpi` no `index.css`): contorno de 1px a 6% + `0 8px 24px -12px` a 12%;
  - botão primário: brilho interno de 1px + sombra verde `0 6px 16px -6px` do `--primary`;
  - modal: `0 24px 64px -16px` do `--ink` a 45%, sobre véu `--ink` 40% com desfoque.
- **Utilitários do web** (`frontend-saas/src/index.css`): `painel`, `painel-kpi` (faixa da marca de 3px no topo, verde → menta → dourado), `painel-vazio` (estado vazio tracejado), `numero-destaque`, `fundo-trabalho` (brilhos suaves nos cantos), `trama-pontos`. Use-os em vez de repetir classes soltas.

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
- **Estrutura do web (shell):**
  - barra lateral escura fixa de 272px (≥ 1024px): logo, navegação em grupos ("Dados", "Planejamento"), e no rodapé avatar com iniciais (fundo `--accent`), nome, central · negócio e "Sair";
  - item atual: fundo branco a 9%, marcador dourado de 3px à esquerda e ícone dourado;
  - abaixo de 1024px vira faixa no topo, com a navegação rolando de lado;
  - faixa clara fixa no topo do conteúdo: trilha ("Planejamento › Produção") e a data de hoje;
  - cada tela entra com um "surgir" de 200ms.
- **Login:** tela dividida. À esquerda, superfície escura com aurora (brilhos verde, menta e dourado se movendo devagar), a promessa do produto em Sora 700 com o fim em degradê menta → dourado, e uma ilustração de cartões de vidro (decorativa, `aria-hidden`). À direita, o formulário sobre `--bg`. No celular, só o logo sobre o fundo escuro e o formulário num cartão.
- **Tabela (web):**
  - dentro de um painel (raio 16); tabela dentro de outra usa `contorno={false}`;
  - cabeçalho 12px maiúsculo `--muted` sobre `--surface`, linhas de 48px, hover `--primary-soft`;
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
- Respeite `prefers-reduced-motion`. Transições de interface de no máximo 200ms. A única exceção é o movimento ambiente lento e decorativo do login (aurora, cartões flutuando), que para com `prefers-reduced-motion`.

## Marca
- **Nome:** Frescor. O nome do módulo de padaria ("Fornada") e o slogan ("Quebra Zero") ainda não foram confirmados.
- **Logo (conceito):** folha com degradê `--mint` → `--primary` → `--primary-hover`, cuja nervura é um "certo" `--accent`, ao lado de "Frescor" em Sora 700 `--secondary` (branco sobre superfície escura), com espaçamento entre letras de −0,03em.
- **Tipografia de impacto:** títulos de página em Sora 700 com −0,025em; números de dashboard em Sora 700 com −0,03em.
- INPI e registro.br ainda não foram consultados.
