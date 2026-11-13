---
name: frescor-design-system
description: Design system do Frescor (web no visual "Comando" azul-noite e âmbar; app mobile na direção B clara). Use ao criar ou alterar qualquer tela, componente ou estilo do frontend-saas ou do app mobile PWA.
---

# Frescor · design system

O Frescor é um SaaS de perecíveis para redes de supermercado: padaria, açougue, hortifruti e itens não produzidos. Ele tem duas superfícies, e **cada uma tem o seu visual**:
- **frontend-saas (web), visual "Comando" azul-noite e âmbar (D117, escolhido pelo Ualker em 13/11/2026):** o gestor da central vê a previsão, gera ordens de produção, faz o romaneio e acompanha o dashboard. Tema **escuro único**, com cara de sala de comando.
- **App mobile (PWA), direção B "Central de produção" (clara):** o operador da loja conta o estoque e lê código de barras no celular, em pé e com pressa. Não mudou com o D117; mudar o app é decisão à parte do Ualker.

Os usuários não são de tecnologia. A interface precisa ser usual, bonita e impossível de confundir.

Protótipos do visual Comando (referência visual do web): `visual-d117/v3/v2-noite-painel` e `v2-noite-login` (`.html` e `.png`) nos arquivos do projeto. Prévia antiga da direção B: https://claude.ai/artifact/S9Td8ehP4vgptb7Z1YT9hh

## Stack sugerida
- **Tailwind CSS + shadcn/ui** (Radix por baixo) nos dois frontends React/Vite.
- No web (Tailwind 4), os tokens ficam em `frontend-saas/src/index.css` como `--fr-<token>` no `:root` e são mapeados no `@theme`. O `src/tema.test.ts` confere cada `--fr-*` contra a tabela de cores do web abaixo: **mudou a tabela, muda o CSS no mesmo commit** (e vice-versa).
- **Componentes:** use os do shadcn (Button, Input, Card, Table, Alert, Dialog, Toast/Sonner) e ajuste-os aos tokens. Não crie componente próprio quando o shadcn já tem um.
- **Ícones:** lucide-react, 20px, traço 2. Ícone **sempre com nome em texto**. Única exceção de ícone sem rótulo fixo: a barra lateral de ícones do web, onde cada ícone tem o nome em texto que aparece como dica no hover e no foco e é o nome lido pelo leitor de tela (veja "Estrutura do web"). Botão fechar com `aria-label`.

## Cores do web (visual Comando, tema escuro único)
| Token | Hex | Uso |
|---|---|---|
| `--primary` | #F5B83D | âmbar: ação principal, link, foco, número em destaque na manchete |
| `--primary-hover` | #E0A52E | hover/pressionado do primário |
| `--on-color` | #1A1200 | texto sobre âmbar, verde e coral (botão primário, botão perigo) |
| `--secondary` | #EEF1F8 | títulos e números grandes |
| `--accent` | #F5B83D | traço, ícone ativo, texto de badge âmbar (sobre `--highlight-bg`) |
| `--highlight-bg` | #3A2C10 | fundo de badge âmbar ("Rascunho", "Evento") |
| `--blue` | #7CC4FF | segunda cor de dado na interface (barra de acerto, "a caminho") |
| `--bg` | #0A0F1E | fundo da página e dos campos |
| `--rail` | #0D1326 | barra lateral de ícones |
| `--surface` | #172038 | linhas alternadas, trilho de barra, hover, dica |
| `--card` | #121A2E | painel, card, modal, menu |
| `--text` | #EEF1F8 | texto principal |
| `--muted` | #98A2BD | texto secundário, legendas |
| `--line` | #222C47 | borda de 1px de painel, divisórias |
| `--input-border` | #6B779C | borda de input e checkbox (3:1 exigido) |
| `--success` / `--success-bg` | #5FD39A / #12302A | recebido, aprovado, dentro da meta |
| `--warning` / `--warning-bg` | #FFB65C / #3A2A10 | pendente, atenção |
| `--error` / `--error-bg` | #FF8A7A / #3A1A1C | erro, ruptura, perda acima do limite |
| `--ink-muted` | #98A2BD | texto secundário na barra lateral (igual a `--muted`) |
| `--ink-line` | #222C47 | divisória na barra lateral (igual a `--line`) |
| `--primary-soft` | #1A2442 | item ativo da barra, hover de linha de tabela, seleção de texto |

Contrastes conferidos (WCAG 2.1; o `tema.test.ts` refaz a conta): text/bg 16,9 · text/card 15,3 · muted/card 6,8 · muted/surface 6,3 · âmbar/card 9,7 · on-color/âmbar 10,4 · input-border/card 3,9 · success/success-bg 7,6 · warning/warning-bg 8,0 · error/error-bg 6,8 · âmbar/highlight-bg 7,6 · blue/card 9,2. Todos AA.

**Cores de série em gráfico (web):** previsto `#3B8FD9` (azul) e vendido `#C2801A` (âmbar escuro), em `acompanhamento/GraficoDias.tsx`. O âmbar e o azul da interface são claros demais para série no escuro (OKLCH L ≈ 0,80; a faixa de série é 0,48–0,67). O par passou no `validate_palette` da skill de dataviz no modo escuro sobre `#121A2E` (CVD ΔE 24,8, contraste ≥ 3:1). Cor nova de série: rode o validador antes.

### Contenção (decisão do Ualker, 28/10/2026, mantida no D117)
A primeira versão do redesenho, com aurora, brilhos, texto em degradê, cartões de vidro, faixas coloridas e sombras verdes, foi recusada por ter "cara de IA". Ficou a regra, que vale também no escuro: **nada de degradê, brilho, desfoque decorativo, vidro, trama de fundo, sombra colorida ou animação de enfeite.** O que impressiona no Comando é o contraste do azul-noite com o âmbar, a manchete com o número grande, os números em fonte mono e a densidade certa, não o efeito.

Ao criar uma cor nova, confira o contraste antes de usar: no mínimo 4,5:1 para texto, 3:1 para texto ≥ 24px, ícones e bordas de controle.

## Cores do app mobile (direção B, clara)
O app (`frontend/`) continua na paleta clara. Valores (sem o `--` para o teste do web não confundir as tabelas):

| Token | Hex | Uso |
|---|---|---|
| primary | #0E6B5C | ação principal, links, foco |
| primary-hover | #0A5549 | hover/pressionado do primário |
| secondary | #1B2B3A | títulos, números grandes |
| accent | #E3A62F | destaque, selo. **Só como fundo** (com texto `text`) |
| bg / surface / card | #FAFBFA / #EEF3F1 / #FFFFFF | fundo, áreas agrupadas, card e input |
| text / muted | #15212B / #56636D | texto principal e secundário |
| line / input-border | #D3DEDA / #7D8A93 | divisória e borda de controle (3:1) |
| success / success-bg | #1F7A3E / #E8F4EC | enviado, dentro da meta |
| warning / warning-bg | #9A5B00 / #FDF3E1 | pendente, atenção |
| error / error-bg | #B42318 / #FDECEA | erro, perda acima do limite |

Contrastes: text/bg 15,8 · muted/bg 6,0 · branco/primary 6,4 · text/accent 7,6 · success/success-bg 4,75 · warning/warning-bg 4,9 · error/error-bg 5,75. Todos AA.

## Tipografia
- **Web (Comando):** **Inter Tight** 400/500/600/700 para tudo (títulos com −0,03em) e **JetBrains Mono** 500/600 para números de destaque (KPI, manchete, totais). Servidas pelo próprio projeto com `@fontsource` (sem Google Fonts em produção).
- **App:** Sora 600/700 para títulos e números; Source Sans 3 400/600 para o resto.
- Fallback: `system-ui, -apple-system, "Segoe UI", sans-serif` (mono: `ui-monospace, monospace`).
- **Escala (px):** 12 legenda · 13 apoio de card · 14 apoio · **16 corpo (mínimo no mobile)** · 18 título de card · 22 título de seção · 28–34 título de página/manchete · 34–48 número de dashboard.
- Rótulo em maiúsculas (sobretítulo, seção): 12px, espaçamento 0,14em, `--muted`.
- Números sempre com `font-variant-numeric: tabular-nums`.
- Formato pt-BR: `1.240 un`, `18,5 kg`, `3,8%`, `14/10/2026`. Use `Intl.NumberFormat('pt-BR')`.

## Espaço, raio e sombra
- **Espaçamento:** escala de 4px: 4, 8, 12, 16, 24, 32, 48. Margem lateral mínima de 16px no mobile.
- **Raio (web):** 12px em botão, input e ícone da barra; 12px nos painéis das telas; **16px nos cartões da visão geral**; 6px em badge; pill (999px) só em status. App: 10px em botão/input, 12px em painel.
- **Sombra:** no escuro, nenhuma em painel e botão: quem separa é a borda de 1px `--line`. Só elementos que flutuam (modal, dica, menu) usam `shadow-elevado` (preta, sem cor), e o modal fica sobre véu preto a 60%, sem desfoque.
- **Utilitários do web** (`frontend-saas/src/index.css`): `painel` (card, borda 1px, raio 12), `painel-kpi`, `painel-vazio` (tracejado), `numero-destaque` (JetBrains Mono 600, −0,02em, tabular, `--secondary`). Use-os em vez de repetir classes soltas.

## Componentes
- **Botão:**
  - altura 44px no web (48px no login) e **48px no mobile**, texto 16px 600;
  - *Primário:* fundo `--primary`; texto `--on-color` no web (tinta escura sobre o âmbar), branco no app;
  - *Secundário:* borda 2px `--primary`, texto `--primary`, fundo transparente;
  - *Perigo:* fundo `--error`; texto `--on-color` no web, branco no app;
  - o rótulo é um verbo do que acontece ("Gerar ordem", "Enviar contagem"), nunca "OK" ou "Confirmar";
  - durante o carregamento, mostre spinner e texto ("Enviando…") e bloqueie o clique duplo.
- **Input:**
  - label visível acima, nunca só placeholder;
  - altura 44/48px, borda 1px `--input-border`; fundo `--bg` no web (o campo fica "fundo" dentro do card), branco no app;
  - campo de quantidade com `inputmode="decimal"` e a unidade (kg, un) fixa ao lado;
  - erro: borda e mensagem em `--error` abaixo do campo, com ícone.
- **Estrutura do web (shell), visual Comando (13/11/2026).** O menu mora em `frontend-saas/src/components/layout/menu.ts`: a barra lateral, a barra do topo e a busca leem de lá.
  - **Barra lateral de ícones** de 76px, `--rail` lisa com borda direita `--line`, fixa (≥ 1024px). É o `<header>` (banner):
    - no topo, o **selo** do Frescor: quadrado âmbar de 40px (raio 30%) com a folha em `--on-color`; o nome "Frescor" fica para o leitor de tela;
    - um ícone de 44px por tela (raio 12), na ordem das seções **Visão** (Visão geral, Acompanhamento), **Dados** (Consultar), **Planejamento** (Previsão, Produção), **Operação** (Distribuição, Perdas), **Configuração** (Cadastros, Integração de vendas). Entre seções, uma divisória `--ink-line`; o nome da seção é só para o leitor de tela. Tela que não é rotina (carga de CSV, D107; trocar senha) fica fora com `foraDoMenu`;
    - **cada ícone tem o nome em texto**, que aparece como dica à direita (fundo `--surface`, borda `--line`, 14px 600) no hover e no foco do teclado e é o nome acessível do link;
    - item atual: fundo `--primary-soft`, ícone `--primary` e traço âmbar de 2px na borda esquerda (`inset`); os outros em `--ink-muted`, hover `--surface`;
    - no pé: "Trocar senha", "Sair" (discreto, nunca primário) e o avatar redondo (iniciais, fundo `--primary-soft`, borda `--line`), que mostra nome e central · negócio na dica (hover e foco);
    - abaixo de 1024px vira faixa no topo, com ícone + nome visíveis e a navegação rolando de lado.
  - **Barra do topo** `--bg`, fixa ao rolar, 64px, borda inferior `--line`: à esquerda "SEÇÃO / Tela" (seção em maiúsculas 12px `--muted`, tela em 16px 600 `--secondary`; não é heading: o h1 fica no conteúdo); à direita a **busca de telas** ("Buscar tela…", `Ctrl K`/`⌘ K`, 44px), que só navega. Sem sino e sem ação global.
  - **Cabeçalho da tela** (`CabecalhoPagina`): sobretítulo opcional em maiúsculas com traço âmbar de 20×2px; h1 30px 700; linha de apoio `--muted`; ações à direita (secundário + no máximo um primário).
- **Visão geral (`/inicio`, primeira tela depois do login), no desenho do protótipo v2 e só com dado real:**
  - **manchete**: sobretítulo com a data por extenso · central; h1 com a saudação ("Bom dia, Ualker"); embaixo, em 28px `--muted`, a frase do dia com os números em âmbar e mono ("Amanhã a central produz **4.812 un** e **612 kg**."); à direita a pill de status da ordem e o botão primário da ordem;
  - grade de 12 colunas: 4 cartões de 3 colunas (Acerto da previsão, Perda, Ruptura, Entregas de hoje), com número em mono 34px, legenda 13px e uma marca pequena embaixo (barra, faísca ou segmentos); depois "Produção de amanhã por setor" (7) e "Previsto × vendido" (5); depois "Acerto por loja" (7) e "Precisa de você" (5);
  - o que o protótipo tinha e o sistema ainda não mede **não vira número inventado**: sem horário de produção não há Gantt (fica a quantidade por setor); o acerto loja × dia somado mistura erros, então fica o acerto da loja na semana (1 − WAPE);
  - "Precisa de você": só pendências reais (ordem não gerada/em rascunho, entrega sem confirmação, divergência, ruptura, nenhuma venda), cada uma com etiqueta (ícone + texto), frase e link;
  - cada bloco carrega e falha sozinho ("Não foi possível carregar…"), sem derrubar a tela.
- **Login (web):** coluna do formulário de 520px à esquerda, com o selo + "Frescor" no topo, a saudação grande pela hora (44px: "Bom dia. A fornada de hoje já está calculada."), o rótulo "ENTRAR" (é o h1), uma frase de apoio, os campos, o botão "Entrar" de 48px e, no pé, a linha para o operador de loja. À direita, só no desktop, a **vitrine**: sobretítulo "EXEMPLO DE UMA CENTRAL · ÚLTIMA SEMANA", o número grande em mono 112px ("91,8%" com o "%" em âmbar), a linha previsto × vendido e três cartões. A vitrine é decorativa (`aria-hidden`) e **diz que é exemplo**: antes do login não há dado real. No celular, só o formulário.
- **Link com cara de botão:** `<Link className={cn(buttonVariants(...))}>`. Sem o `cn`, a borda do secundário pode sumir.
- **Tabela (web):**
  - dentro de um painel; tabela dentro de outra usa `contorno={false}`;
  - cabeçalho 12px maiúsculo `--muted` sobre `--surface`, linhas de 48px, hover `--primary-soft`;
  - números alinhados à direita; zebra com `--surface`;
  - no mobile, a tabela vira uma lista de cards.
- **Número de dashboard:** rótulo curto em cima; número grande em mono (web) ou Sora (app), `--secondary`, sem quebrar linha; variação embaixo com seta e cor semântica. No máximo 4 números por linha. **Perda subindo é vermelho**, mesmo sendo "para cima".
- **Alerta:** fundo `*-bg`, texto e ícone na cor semântica; uma frase do que houve e uma do que fazer; o toast some sozinho só para sucesso; erro fica até a pessoa fechar.
- **Badge de status:** pill 12–14px 600, fundo `*-bg` e texto na cor semântica. No web, "Rascunho"/"Em andamento"/"Evento" usam `--highlight-bg` com texto `--accent`.

## Regras de clareza
1. **Uma ação principal por tela.** Só um botão primário visível.
2. **Texto curto em pt-BR, na língua da loja:** "contagem", "perda", "quebra", "romaneio", "ordem de produção". Nada de "sincronizar registro" ou "payload". Nada de código de decisão (D89) na tela.
3. **Números grandes e com unidade.** Nunca mostre uma quantidade sem `un` ou `kg`. UN e KG nunca se somam.
4. **Erro claro:** diga o que deu errado e como resolver. Nada de "Erro 422" na tela. Não peça desculpa.
5. **Estado vazio útil:** diga o que vai aparecer ali e mostre o caminho que começa.
6. **Confirmação só para o que não se desfaz**, em diálogo com o verbo no botão.
7. **Mobile:** ação principal fixa no rodapé; leitura de código com feedback imediato.
8. **Cor nunca sozinha:** status sempre com texto ou ícone junto; barras e segmentos com legenda em texto.
9. **Dado de exemplo só onde não há dado real (login) e sempre dito como exemplo.**

## Acessibilidade
- Contraste AA em tudo (veja as tabelas acima).
- **Área de toque:** mínimo 44×44px, e **48×48px no app mobile**, com 8px entre os alvos.
- **Foco visível:** anel de 2px `--primary` com 2px de offset (`focus-visible`). No web o âmbar aparece bem sobre o escuro, inclusive na barra lateral. Nunca `outline: none` sem substituto.
- `lang="pt-BR"`, labels ligadas aos inputs, `aria-live="polite"` para resultado de leitura e envio.
- Respeite `prefers-reduced-motion`. Animações de no máximo 200ms, só para dar retorno (hover, dica, abrir diálogo), nunca de enfeite.

## Marca
- **Nome:** Frescor. O nome do módulo de padaria ("Fornada") e o slogan ("Quebra Zero") ainda não foram confirmados.
- **Logo (web, Comando):** selo quadrado âmbar com a folha em `--on-color` e a nervura em "certo" no próprio âmbar, ao lado de "Frescor" em Inter Tight 700 `--secondary` (−0,03em). Componente `Logo`/`Selo` em `components/marca/Logo.tsx`.
- **Logo (app):** folha `#0E6B5C` com a nervura em "certo" `#E3A62F`, ao lado de "Frescor" em Sora 700.
- INPI e registro.br ainda não foram consultados.
