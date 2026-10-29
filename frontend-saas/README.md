# Frescor · painel da central (frontend do SaaS)

Painel web do **gestor da central de produção**: entrar, importar vendas e
perdas por CSV, consultar o que foi importado, ver a previsão de vendas e gerar,
ajustar, aprovar e imprimir a ordem de produção. Fala com o mesmo backend do
app mobile (`../backend`), pelas rotas do SaaS (token com `porta: web`).

Estado do projeto, decisões e próximos passos: [`../docs/STATUS.md`](../docs/STATUS.md).
Visual e regras de interface: skill
[`../.claude/skills/frescor-design-system/SKILL.md`](../.claude/skills/frescor-design-system/SKILL.md).

---

## 1. Como rodar

Pré-requisitos: Node 22 e o backend rodando em <http://127.0.0.1:8000>
(ver `../backend/README.md`), com os seeds (`seed_dev.py`, `seed_produtos.py`
e, para ter dados na consulta e na previsão, `seed_vendas.py`). Para ver
"Sem previsão" e "Pouco histórico" na tela de previsão, rode também
`seed_demo_previsao.py` e entre com `gestor.demo@teste.com` / `senha123`.
Para a tela de produção (contagens, setores, todos os avisos), rode
`seed_demo_producao.py` e entre com `gestor.producao@teste.com` / `senha123`.
O PDF da ordem precisa do `reportlab` no backend (`pip install -r requirements.txt`).

```powershell
cd frontend-saas
npm install
npm run dev
```

Abra **<http://localhost:3001>** e entre com `gestor@teste.com` / `senha123`
(gestor do seed). As chamadas à API passam pelo próprio Vite
(`/backend/...` → `http://127.0.0.1:8000/...`), então não há CORS em
desenvolvimento. Porta 3001 em http: é desktop, sem câmera, não precisa de
HTTPS (o app mobile usa a 3000 em HTTPS).

Para apontar para outra API, defina `VITE_API_URL` (ex.: num arquivo
`.env.local`, que não vai para o git).

## 2. Comandos

| Comando | O que faz |
|---|---|
| `npm run dev` | Servidor de desenvolvimento na porta 3001 |
| `npm run test` | Todos os testes (Vitest + Testing Library + axe-core) |
| `npm run typecheck` | Checagem de tipos (TypeScript) |
| `npm run lint` | Linter (oxlint) |
| `npm run build` | Checagem de tipos + build de produção em `dist/` |
| `npm audit --omit=dev` | Vulnerabilidades nas dependências que vão para produção |

## 3. Telas

| Rota | Tela |
|---|---|
| `/entrar` | Login do gestor. Erros claros: "E-mail ou senha incorretos.", mensagem da API para quem não tem acesso, aviso quando a sessão expira. |
| `/importar` | Importação de CSV de vendas ou perdas. Resumo grande no topo ("1.232 linhas importadas" ou "Nada foi gravado: 3 erros") e depois as tabelas de erros e avisos. Modelo de CSV para baixar. |
| `/consultar` | Consulta por período (até 366 dias), loja e produto (busca sem acento). Resumo do período no topo (total vendido e de perda, por unidade), tabela paginada de 50 em 50. Filtros ficam na URL. |
| `/previsao` | Previsão de vendas por dia (padrão: amanhã), loja e produto; filtros na URL. No topo, o resumo do dia (previsto por unidade contra o mesmo dia da semana passada; produtos sem previsão ou com pouco histórico citados pelo nome). Depois, a tabela: cada linha tem uma frase de como o número foi calculado ("Mediana das últimas 6 quartas × tendência +10%") e "Ver a conta" abre o passo a passo. Por fim, a qualidade (erro médio, sobra/falta, comparação com repetir a semana passada). Ação principal: "Gerar previsão" / "Atualizar previsão". **Carregada só quando aberta** (`React.lazy`). |
| `/producao` | Ordem de produção por dia de produção (padrão: amanhã; de hoje até 6 dias à frente). Sem ordem: "Gerar ordem". **Rascunho:** ação principal "Aprovar ordem"; "Gerar de novo" (com ajustes, pede confirmação dizendo quantas linhas ajustadas serão perdidas) e "Apagar rascunho". Resumo com o que produzir e distribuir por unidade, linhas sem quantidade e "Confira estes"; tabelas "Produção" e "A distribuir"; cada produto abre as lojas (sugerido, final, perda das 4 semanas em 4 faixas, avisos, "Ajustar" e "Ver a conta"). **Aprovada:** só leitura, com "Imprimir" (escolha de setores, "todos" por padrão; o PDF abre numa aba nova, uma folha por setor). A conta mostra também o que veio do romaneio (recebido depois da contagem, entrega sem confirmação). **Carregada só quando aberta** (`React.lazy`). |
| `/distribuicao` | Distribuição e romaneio por dia de entrega (padrão: hoje; `?data=` na URL). Um bloco por ordem aprovada, com **uma ação principal por estado**: "Registrar produção" → "Gerar romaneio" → **rascunho:** "Aprovar romaneio" (o diálogo lista e bloqueia produto cuja soma das lojas passa do produzido), "Ajustar" por loja e produto, "Gerar de novo" (avisa quantos ajustes se perdem) e "Apagar romaneio" → **aprovado:** "Imprimir" (todas as lojas ou algumas) e "Registrar saída" ("todas as que faltam" ou escolher lojas). Acompanhamento por loja: aguardando saída, a caminho, recebido (com ou sem diferença), **sem confirmação** (nunca mostrada como recebida) e confirmado com atraso; cada loja abre os itens. Embaixo, "Diferenças no recebimento" (últimos 7 dias). **Carregada só quando aberta** (`React.lazy`). |
| `/cadastros` | Cadastros, com um submenu e um endereço para cada parte. **Produtos** (`/cadastros/produtos`): lista com busca e "Novo produto"; o formulário (`/novo` e `/:id`) tem identificação, unidade e produção (setor e dias da semana; produto novo nasce com todos os dias, nenhum dia = sem calendário, sem sugestão na ordem), validade e margem, vigência (permanente, temporário ou sazonal); no produto já cadastrado, "Lojas da central" com ativar/desativar por loja. **Setores de produção:** novo, renomear, subir/descer, desativar. **Eventos:** lista a partir de hoje, "Novo evento" (multiplicar ou fixar; lojas e produtos) e apagar com confirmação. **Central:** nome e prazo de entrega. **Carregada só quando aberta** (`React.lazy`). |

Formato do CSV: `data;codigo_loja;codigo_produto;quantidade`, separador `;`,
vírgula decimal, data `dd/mm/aaaa`, até 5 MB. Arquivos de exemplo em
[`exemplos/`](exemplos/README.md).

## 4. Estrutura

```text
src/
├── App.tsx                     # Rotas
├── main.tsx                    # TanStack Query + roteador + sessão
├── index.css                   # Tema: tokens da skill Frescor (--fr-*) + mapeamento do shadcn
├── components/
│   ├── ui/                     # Componentes do shadcn ajustados à skill
│   ├── marca/Logo.tsx          # Logo Frescor (conceito provisório da skill)
│   └── layout/                 # Cabeçalho, navegação e "Sair"
├── lib/
│   ├── api/                    # Cliente da API, sessão (tokens) e tipos das respostas
│   ├── sessao/                 # Provider da sessão e rota protegida
│   ├── formato.ts              # Números, quantidades e datas em pt-BR
│   ├── modeloCsv.ts            # Modelo de CSV para baixar
│   ├── perda.ts                # Faixas do indicador de perda (3% / 5% / 8%, constante única, D66)
│   └── query.ts                # Configuração do TanStack Query
├── paginas/                    # Entrar, Importar, Consultar, Previsao, Producao, Distribuicao, Cadastros (+ componentes de cada uma)
│   ├── cadastros/              # Produtos (lista, formulário, lojas), setores, eventos, central;
│                               # formularioProduto.ts (campos, validação e corpo enviado)
│   ├── distribuicao/           # Bloco de cada ordem, tabelas do romaneio, diálogos (produção, saída, imprimir),
│                               # divergências, situacao.ts (textos da situação de cada entrega)
│   ├── previsao/               # Resumo, tabela, qualidade e explicacao.ts (frase de cada número)
│   └── producao/               # Resumo, tabela com as lojas, diálogos (ajustar, confirmar, imprimir),
│                               # conta.ts ("Ver a conta"), avisos.ts, quantidade.ts (validação)
└── test/                       # Ajudantes de teste (App completo, API simulada, itens de previsão e de ordem)
```

## 5. Decisões importantes

- **Tokens** no `localStorage`, com chaves próprias do SaaS (decisão DF2).
  Antes da produção: refresh token em cookie `httpOnly` (exige backend).
- **Sessão:** 401 → uma renovação (compartilhada entre chamadas) e uma
  repetição; renovação recusada ou 403 → volta ao login mostrando o motivo.
  Ao sair, o cache de dados é apagado.
- **Tema:** skill e shadcn usam `--secondary`, `--accent` e `--muted` com
  sentidos diferentes; os tokens da skill ficam como `--fr-*` e o mapeamento
  está documentado no topo do `index.css`. Só existe paleta clara.
- **Fontes** Sora e Source Sans 3 servidas pelo próprio projeto (`@fontsource`).
- **Uma ação principal por tela**; erros sem código técnico; quantidade
  sempre com a unidade.
- **Código dividido por tela** a partir da Fase 3: telas novas entram com
  `React.lazy` + `import()`. Conferir o tamanho no `npm run build`: o JS
  principal está em ~488 kB (o Vite avisa acima de 500 kB). Bibliotecas usadas
  só por uma tela (ex.: os avisos do `sonner`, na previsão) ficam montadas
  nessa tela, para irem no pacote dela.
- **Previsão na tela:** o número exibido é sempre o do backend (1 casa em UN,
  2 em KG; o banco guarda 4). A explicação de cada linha só descreve os
  componentes gravados, não refaz conta. A qualidade fica guardada 10 minutos
  por loja + produto e não é recalculada ao trocar o dia.
- **Ordem de produção na tela:** a conta de cada linha ("Ver a conta") também
  só descreve os componentes gravados pelo backend. A quantidade digitada é
  conferida no navegador com as mesmas regras do backend (UN inteiro, KG até 3
  casas, vírgula decimal). Ordem aprovada não tem nenhuma ação de alterar.
- **PDF:** a rota exige o token, então a tela baixa o arquivo e abre o
  endereço local dele numa aba aberta no próprio clique (para o navegador não
  bloquear como pop-up; se bloquear, o PDF é baixado).
- **Distribuição na tela:** a situação de cada entrega vem calculada do
  backend; a tela só traduz. "Registrar saída" só existe com o romaneio
  aprovado e alguma loja aguardando saída. O visual segue o `main` atual; se o
  redesign do PR #1 entrar, a tela precisa trocar as classes.
- **Faixas de perda:** limites numa constante única (`lib/perda.ts`);
  configuração por negócio fica para depois (STATUS, seção 5).

## 6. Testes e acessibilidade

- Testes de tela renderizam o App completo com a API simulada por rota
  (`src/test/renderizar.tsx`).
- `src/tema.test.ts` lê a tabela de cores **direto da skill** e exige os
  mesmos valores no CSS, além de recalcular os contrastes WCAG.
- `src/acessibilidade.test.tsx` roda o **axe-core** nas telas e estados
  principais. Limitação: no jsdom o axe não mede contraste (coberto pelo
  teste do tema).
- Manual: navegar só pelo teclado (Tab, Enter, Esc) — o link "Pular para o
  conteúdo" aparece no primeiro Tab, o foco é sempre visível (anel verde).
