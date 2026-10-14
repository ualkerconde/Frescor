# Frescor · painel da central (frontend do SaaS)

Painel web do **gestor da central de produção**: entrar, importar vendas e
perdas por CSV e consultar o que foi importado. Fala com o mesmo backend do
app mobile (`../backend`), pelas rotas do SaaS (token com `porta: web`).

Estado do projeto, decisões e próximos passos: [`../docs/STATUS.md`](../docs/STATUS.md).
Visual e regras de interface: skill
[`../.claude/skills/frescor-design-system/SKILL.md`](../.claude/skills/frescor-design-system/SKILL.md).

---

## 1. Como rodar

Pré-requisitos: Node 22 e o backend rodando em <http://127.0.0.1:8000>
(ver `../backend/README.md`), com os seeds (`seed_dev.py`, `seed_produtos.py`
e, para ter dados na consulta, `seed_vendas.py`).

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
│   └── query.ts                # Configuração do TanStack Query
├── paginas/                    # Entrar, Importar, Consultar (+ componentes de cada uma)
└── test/                       # Ajudantes de teste (App completo, API simulada)
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
