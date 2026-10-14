# Backend — Projeto Bakery

API em **Python + FastAPI**, com banco de dados **PostgreSQL**. Backend único,
multiempresa, para as duas portas de entrada do produto:

- **App móvel (PWA)** — as lojas fazem a contagem de estoque (em produção).
- **SaaS web** — a central de produção compila a demanda das lojas (em construção).

Estado do projeto, decisões e próximos passos: `../docs/STATUS.md`.

---

## Estrutura de pastas

```text
backend/
├── alembic/                        # Migrações do banco de dados
│   ├── versions/
│   │   ├── 0001_criacao_tabelas_iniciais.py
│   │   ├── 0002_lojas_e_habilitacao.py
│   │   ├── 0003_unidade_medida_e_estoque_calculado.py
│   │   ├── 0004_adiciona_codigo_produto.py
│   │   ├── 0005_peso_informado_kg.py
│   │   ├── 0006_niveis_classificacao_produtos.py
│   │   ├── 0007_central_producao.py
│   │   ├── 0008_loja_central_producao_id.py
│   │   ├── 0009_usuario_tipo_e_central.py
│   │   ├── 0010_produto_campos_producao.py
│   │   ├── 0011_produto_loja_ativo.py
│   │   ├── 0012_calendario_producao.py
│   │   ├── 0013_evento_e_associacoes.py
│   │   ├── 0014_usuario_tem_acesso_web.py
│   │   ├── 0015_vendas_e_perdas_diarias.py
│   │   ├── 0016_produto_codigo_unico.py
│   │   └── 0017_extensao_unaccent.py
│   ├── env.py
│   └── script.py.mako
├── alembic.ini
├── app/
│   ├── api/
│   │   ├── auth.py            # App: /auth/login, /auth/refresh, /auth/logout
│   │   ├── auth_web.py        # SaaS: /auth/web/login, /auth/web/refresh
│   │   ├── importacao.py      # SaaS: POST /vendas/importar, /perdas/importar (CSV)
│   │   ├── consultas.py       # SaaS: GET /vendas, /perdas
│   │   ├── escopo.py          # SaaS: loja fora do escopo do gestor -> 404
│   │   ├── health.py          # /api/health
│   │   ├── produtos.py        # App: /produtos, /estoque
│   │   └── zeragem.py         # App: /zeragem/executar-agora
│   ├── core/
│   │   ├── config.py          # Leitura do .env
│   │   ├── security.py        # Hash de senha + JWT
│   │   ├── dependencies.py    # Autenticação e isolamento multiempresa (CRÍTICO):
│   │   │                      #   obter_usuario_autenticado (app) e obter_gestor_central (SaaS)
│   │   └── scheduler.py       # Agendador APScheduler (zeragem automática)
│   ├── db/
│   │   └── session.py         # Conexão com o banco
│   ├── models/
│   │   ├── negocio.py
│   │   ├── loja.py
│   │   ├── usuario.py
│   │   ├── permissao_web.py
│   │   ├── produto.py
│   │   ├── produto_loja.py
│   │   ├── estoque_atual.py
│   │   ├── historico_contagem.py
│   │   ├── nivel_classificacao.py     # Níveis de classificação (até 4, por negócio)
│   │   ├── produto_classificacao.py   # Valor de cada produto em cada nível
│   │   ├── central_producao.py        # Central de produção (cada loja pertence a uma)
│   │   ├── calendario_producao.py     # Dias da semana em que cada produto é produzido
│   │   ├── evento.py                  # Eventos de demanda atípica + associações com lojas/produtos
│   │   ├── venda_diaria.py            # Venda por loja + produto + dia + origem
│   │   └── perda_diaria.py            # Perda por loja + produto + dia + origem
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── estoque.py
│   │   ├── importacao.py
│   │   ├── consulta.py
│   │   └── zeragem.py
│   ├── services/
│   │   ├── estoque_service.py       # Lógica de contagem e cálculo UN/KG
│   │   ├── classificacao_service.py # Monta a classificação de cada produto para o app
│   │   ├── zeragem_service.py       # Lógica de zeragem diária por loja
│   │   ├── escopo_service.py        # Lojas no escopo do gestor (só a central dele)
│   │   ├── importacao_service.py    # Importação de CSV de vendas/perdas (regras D5-D13)
│   │   ├── consulta_service.py      # Consulta de vendas/perdas (filtros, período, paginação)
│   │   └── sync_vendas_service.py   # STUB da integração com o PDV (não configurada)
│   └── main.py                 # Ponto de entrada da aplicação
├── scripts/
│   ├── seed_dev.py                     # Negócio, central, 2 lojas, operadores e gestor de teste
│   ├── seed_produtos.py                # Produtos de teste, habilitados em todas as lojas
│   ├── seed_vendas.py                  # ~8 semanas de vendas e perdas das 2 lojas
│   ├── test_*.py                       # Scripts de teste (ver seção 3.3)
│   └── _check_enums.py                 # Utilitário: lista os tipos enum do PostgreSQL
├── .env.example
├── .gitignore
├── requirements.txt
└── requirements-dev.txt               # Só desenvolvimento: httpx (TestClient dos testes de rota)
```

---

## 1. Pré-requisitos

- Python 3.11 ou superior
- PostgreSQL instalado e rodando
- VS Code com a extensão "Python" instalada

---

## 2. Configuração inicial

### 2.1 Criar e ativar o ambiente virtual

Abra o terminal **dentro da pasta `backend`**:

```bash
python -m venv venv
```

Ativar (Windows - PowerShell):

```bash
venv\Scripts\Activate.ps1
```

Ativar (macOS/Linux):

```bash
source venv/bin/activate
```

O terminal deve mostrar `(venv)` no início da linha. Se não mostrar, o ambiente não está ativo — não pule este passo.

No VS Code, selecione o interpretador correto:
`Ctrl+Shift+P` → "Python: Select Interpreter" → escolha `.\venv\Scripts\python.exe`.

### 2.2 Instalar as dependências

```bash
pip install -r requirements.txt
```

Para rodar os scripts de teste de rota (usam o `TestClient` do FastAPI):

```bash
pip install -r requirements-dev.txt
```

> **Nota (Python 3.14 + bcrypt):** Se der erro relacionado ao bcrypt durante
> o `pip install`, execute:
>
> ```bash
> pip uninstall bcrypt -y
> pip install bcrypt==4.0.1
> ```

### 2.3 Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Abra o `.env` e ajuste `DATABASE_URL` com seus dados reais:

```text
DATABASE_URL=postgresql://postgres:SUASENHA@localhost:5432/bakery
```

Gere uma chave secreta segura:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Cole o valor gerado no campo `SECRET_KEY` do `.env`.

> **Atenção com o .env no Windows:** Crie o arquivo do zero com
> `New-Item .env -ItemType File` e edite manualmente no VS Code.
> Não use `Copy-Item` do PowerShell — pode salvar com codificação
> incorreta e causar erros de conexão com o banco.

---

## 3. Banco de dados

### 3.1 Criar as tabelas

```bash
alembic upgrade head
```

Aplica as 17 migrações em sequência (0001 a 0017). Tabelas criadas:
`negocios`, `centrais_producao`, `lojas`, `usuarios`, `permissoes_web`,
`produtos`, `produtos_lojas`, `estoque_atual`, `historico_contagens`,
`niveis_classificacao`, `produto_classificacoes`, `calendario_producao`,
`eventos`, `eventos_lojas`, `eventos_produtos`, `vendas_diarias`,
`perdas_diarias`.

| Migração | O que faz |
| --- | --- |
| 0001–0006 | Base do app de contagem: negócios, lojas, usuários, produtos, habilitação, estoque, histórico, unidade de medida, código interno, peso informado, níveis de classificação |
| 0007 | Cria `centrais_producao` |
| 0008 | `lojas.central_producao_id` (obrigatório); cria uma "Central Principal (Padrão)" para as lojas que já existiam |
| 0009 | `usuarios.tipo_usuario` (`operador_loja` / `gestor_central`), `central_producao_id`, `loja_id` opcional e o check constraint `ck_usuario_tipo_vs_loja_central` |
| 0010 | Campos de produção em `produtos` (`tem_producao_propria`, `dias_validade`, `ciclo_previsao`, ...) |
| 0011 | `produtos_lojas.ativo` |
| 0012 | Cria `calendario_producao` |
| 0013 | Cria `eventos`, `eventos_lojas` e `eventos_produtos` |
| 0014 | `usuarios.tem_acesso_web` (acesso ao SaaS, separado de `tem_acesso_app`) |
| 0015 | Cria `vendas_diarias` e `perdas_diarias` (única por loja + produto + data + origem; FKs compostas com `negocio_id`); `lojas.codigo` |
| 0016 | Código de produto único no negócio (para antes de criar se houver códigos repetidos, listando cada um) |
| 0017 | Extensão `unaccent` do PostgreSQL: a busca de produtos ignora acentos ("pao" acha "Pão"). Precisa estar disponível no PostgreSQL de produção |

Toda migração tem `downgrade` funcional. Para conferir uma migração nova:
`alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`.

### 3.2 Popular dados de teste

```bash
python scripts/seed_dev.py
python scripts/seed_produtos.py
python scripts/seed_vendas.py
```

Os três scripts são idempotentes: podem rodar quantas vezes quiser, sem
duplicar dados.

Rode **nesta ordem** (cada um usa o que o anterior criou). Cria:

- **Negócio:** "Rede Padaria Teste"
- **Central de produção:** reaproveita a do negócio, se já existir
- **Lojas:** "Loja Centro" (código `001`) e "Loja Bairro" (código `002`), horário de zeragem 06:00
- **Usuários** (senha `senha123`):

| E-mail | Perfil | App mobile | SaaS web |
| --- | --- | --- | --- |
| `admin@teste.com` | operador da Loja Centro | sim | não |
| `operador.bairro@teste.com` | operador da Loja Bairro | sim | não |
| `gestor@teste.com` | gestor da central | não | sim |

- **11 produtos:** 6 em UN, 4 em KG com peso médio e 1 em KG sem peso médio (pesado na hora)
- **Habilitação:** todos os produtos habilitados em todas as lojas do negócio
- **Classificação** (Categoria/Subcategoria) e **calendário de produção** de exemplo
- **Vendas e perdas** (`seed_vendas.py`): as 8 semanas que terminam ontem, para as 2 lojas e
  todos os produtos habilitados, origem `manual`. Padrões: mais venda no fim de semana, Loja
  Bairro ~65% da Loja Centro, perda maior em produto de validade curta (~9% para 1 dia, ~1,5%
  para 5 dias), variação aleatória com semente fixa por loja + produto + dia (o valor de um dia
  é sempre o mesmo). Rodar de novo substitui os mesmos valores, sem criar linhas.

O gestor entra no SaaS por `POST /auth/web/login`; no app (`/auth/login`) ele é recusado.

### 3.3 Scripts de teste

Rodam contra o banco configurado no `.env`, criam os próprios dados de
teste e apagam tudo ao final (também apagam resíduos de execuções
anteriores que tenham quebrado no meio). Terminam com exit 0 se tudo
passou e exit 1 se algum caso falhou.

Os testes de rota usam o `TestClient` (requer `requirements-dev.txt`) e
não iniciam o agendador de zeragem. Vários usam os usuários do seed
(rode os seeds antes); o app é testado numa loja de teste própria, então
as contagens das lojas do seed não são tocadas.

```bash
python scripts/test_constraint_usuario.py     # check constraint de tipo de usuário (4 casos)
python scripts/test_obter_gestor_central.py   # dependency de acesso ao SaaS (11 casos)
python scripts/test_auth_web.py               # login/refresh do SaaS + regressão completa do app (38)
python scripts/test_vendas_perdas_modelo.py   # regras de banco de vendas/perdas e códigos (23)
python scripts/test_escopo_gestor.py          # escopo do gestor: só a própria central (13)
python scripts/test_importacao_csv.py         # serviço de importação de CSV (45)
python scripts/test_importacao_rotas.py       # POST /vendas/importar e /perdas/importar (14)
python scripts/test_consulta_rotas.py         # GET /vendas e /perdas, totais + importar e consultar (40)
python scripts/test_sync_vendas_stub.py       # stub da integração com o PDV (5)
python scripts/test_web_apoio.py              # /web/me, /web/lojas, /web/produtos (25)
```

Saída esperada: uma linha `[OK]` por caso e, no fim, `TODOS OS CASOS PASSARAM`
(ou `N verificações; TODAS PASSARAM`).

---

## 4. Rodando a API

```bash
uvicorn app.main:app --reload
```

- `http://127.0.0.1:8000/docs` → documentação interativa (Swagger)
- `http://127.0.0.1:8000/api/health` → deve retornar `{"status": "ok", "database": "conectado"}`

---

## 5. Modelo de dados

### Hierarquia

```text
negocio (rede)
   └─ centrais_producao  (cada loja pertence a exatamente uma central)
         └─ usuarios     (gestor_central: escopo da central, sem loja)
   └─ lojas         (N lojas, cada uma com horario_zeragem próprio)
         └─ usuarios (operador_loja: pertence a UMA loja fixa)
   └─ produtos      (catálogo da rede — gerenciado pelo software web)
         └─ produtos_lojas   (habilitação: quais produtos cada loja pode contar)
               └─ estoque_atual        (por produto + loja)
               └─ historico_contagens  (snapshot diário, por produto + loja)
```

### Campos de estoque (dois campos separados, propósitos distintos)

| Campo | Onde aparece | Comportamento |
| --- | --- | --- |
| `quantidade_inventariada` | App mobile (rascunho) | Contagem de peças (inteiro). **Zerado pela rotina diária.** |
| `estoque_atual_calculado` | Software web (valor real) | Calculado a cada lançamento. **Nunca zerado pela rotina.** |

**Cálculo por unidade de medida:**

- `UN` → `estoque_atual_calculado = quantidade_inventariada`
- `KG` (com `peso_medio_kg` cadastrado) → `estoque_atual_calculado = peso_medio_kg × quantidade_inventariada`
- `KG` sem `peso_medio_kg` cadastrado → o responsável informa o peso pesado na hora (`peso_informado_kg`); nesse caso `estoque_atual_calculado = peso_informado_kg`. O campo `requer_peso_informado`, retornado pela API, indica quando esse cenário se aplica.

Os produtos também têm um `codigo` (código interno, distinto do `codigo_barras`), usado na busca unificada do app.

### Classificação de produtos (multi-nível)

Cada negócio pode configurar até 4 níveis de classificação (ex.: Departamento,
Seção, Categoria, Subcategoria), na tabela `niveis_classificacao`. Cada
produto recebe um valor por nível na tabela `produto_classificacoes`
(ex.: produto "Pão Francês" → nível "Departamento" = "Padaria"). Este
backend apenas **lê** essa classificação (via `classificacao_service.py`) e
a expõe em `GET /produtos` e `/produtos/buscar` — a gestão de níveis e
valores é feita pelo software web (fora deste repositório).

---

## 6. Endpoints da API

### Autenticação

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/auth/login` | Login com e-mail + senha. Retorna access_token (1h) + refresh_token (30 dias). |
| `POST` | `/auth/refresh` | Renova o access_token usando o refresh_token. |
| `POST` | `/auth/logout` | Logout — apaga tokens do lado do cliente. |

### Produtos e Estoque (exigem autenticação)

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/produtos` | Lista produtos habilitados para a loja do usuário logado, com estoque atual e a `classificacao` (níveis/valores) de cada produto. |
| `GET` | `/produtos/buscar?q=...` | Busca unificada: localiza um produto pelo `codigo` (interno) OU `codigo_barras` (leitura via câmera), usando o mesmo parâmetro `q`. |
| `PATCH` | `/estoque/{produto_id}` | Atualiza a contagem de um produto (`quantidade_inventariada` e, quando aplicável, `peso_informado_kg`). Recalcula `estoque_atual_calculado` automaticamente. |
| `POST` | `/estoque/sincronizar` | Sincroniza em lote contagens feitas offline. Aplica regra "último a sincronizar prevalece". |

### Zeragem (exige autenticação)

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/zeragem/executar-agora` | Dispara a zeragem manualmente para a loja do usuário autenticado. Use `?forcar=true` para ignorar a regra de "uma vez por dia". |

### SaaS web — autenticação do gestor de central

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/auth/web/login` | Login do gestor (e-mail + senha). Exige `tem_acesso_web`, perfil `gestor_central` e central ativa do mesmo negócio. Tokens com a claim `porta: web`. 401 credenciais erradas; 403 sem permissão (com o motivo). |
| `POST` | `/auth/web/refresh` | Renova o access token do SaaS; confere as permissões de novo no banco. |

Os tokens do SaaS e do app não são intercambiáveis: cada porta recusa o token da outra (401).

### SaaS web — vendas e perdas (exigem token do SaaS)

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/vendas/importar` | Upload multipart (campo `arquivo`) de CSV `data;codigo_loja;codigo_produto;quantidade`, `;`, vírgula decimal, `dd/mm/aaaa`, UTF-8 ou Windows-1252, até 5 MB. Tudo ou nada; reimportação substitui. 200 com relatório (inseridas, substituídas, avisos); 422 com o mesmo relatório e os erros por linha (nada gravado); 413 acima de 5 MB. |
| `POST` | `/perdas/importar` | Igual, para perdas. |
| `GET` | `/vendas` | `data_inicio` e `data_fim` obrigatórios (AAAA-MM-DD, até 366 dias); `loja_id`, `produto_id`; `limit` (1–1000, padrão 100), `offset`. Só lojas da central do gestor; loja fora do escopo → 404. Resposta `{total, limit, offset, itens}`, ordenada por data, loja, produto e origem. |
| `GET` | `/perdas` | Igual, para perdas. |

A resposta de `GET /vendas` e `GET /perdas` traz também `totais`: a soma do período por unidade (`UN` e `KG` não se somam), com os mesmos filtros e **sem** paginação — usada no resumo do topo da tela de consulta.

Quando o mesmo loja + produto + data tem registro `api` (PDV) e `manual` (CSV), **vale o `api`**: o `manual` continua gravado como reserva, mas não aparece na listagem nem entra nos totais (decisão D16). O critério fica num lugar só, `app/services/registros_efetivos.py`, e deve ser usado por toda leitura de vendas/perdas para números de negócio (inclusive o motor de previsão).

### SaaS web — apoio às telas (exigem token do SaaS)

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/web/me` | Gestor logado, sua central e seu negócio (cabeçalho). |
| `GET` | `/web/lojas` | Lojas da central do gestor, ativas e inativas (campo `ativo`). |
| `GET` | `/web/produtos?busca=&limit=&offset=` | Produtos do negócio (ativos e inativos), busca por código ou nome sem diferenciar maiúsculas nem acentos; `%` e `_` são texto; `limit` até 200. |

---

## 7. Segurança — Isolamento Multiempresa

**Regra fundamental:** `negocio_id`, `loja_id` e `central_producao_id`
**nunca** vêm de um parâmetro enviado pelo cliente. São sempre lidos do
registro atual do usuário identificado pelo token JWT validado no backend
(ver `app/core/dependencies.py`). Isso impede que um usuário de um negócio
acesse dados de outro negócio, mesmo alterando parâmetros na requisição.

Duas dependencies, uma por porta de entrada:

| Dependency | Usada por | Exige | Devolve |
| --- | --- | --- | --- |
| `obter_usuario_autenticado` | app mobile | token do app (sem a claim `porta`) + usuário ativo + `tem_acesso_app` + `operador_loja` | `usuario_id`, `negocio_id`, `loja_id` |
| `obter_gestor_central` | SaaS web | token do SaaS (`porta: web`) + usuário ativo + `tem_acesso_web` + `gestor_central` + central do mesmo negócio e ativa | `usuario_id`, `negocio_id`, `central_producao_id` |

No SaaS, o gestor só enxerga as lojas da **própria central** (`app/services/escopo_service.py`).
Vendas e perdas também têm FKs compostas com `negocio_id`: o banco recusa uma linha que
aponte para loja ou produto de outro negócio.

Na `obter_gestor_central`: token ausente ou inválido → **401**; autenticado
sem permissão → **403**. (Na dependency do app, token ausente responde 403,
que é o padrão do FastAPI 0.115; foi mantido para não mudar o comportamento
do app em produção.)

---

## 8. Autenticação — Sessão de 30 dias

- **Access Token:** vida curta (1 hora). Enviado em toda chamada à API.
- **Refresh Token:** vida longa (30 dias). Usado para renovar o access token
  automaticamente, sem pedir senha novamente.
- O usuário só precisa logar de novo se passar 30 dias sem usar o app,
  ou se fizer logout manualmente, ou se o admin revogar o acesso.

---

## 9. Zeragem diária automática

O agendador (APScheduler) roda em segundo plano dentro do processo da API,
verificando a cada 1 minuto se alguma loja atingiu seu `horario_zeragem`.

**Fluxo de zeragem (por loja, em transação atômica):**

1. Copia `quantidade_inventariada` e `estoque_atual_calculado` de cada
   produto para `historico_contagens` (snapshot preservado para relatórios).
2. Zera **apenas** `quantidade_inventariada` em `estoque_atual`.
3. `estoque_atual_calculado` permanece intocado — continua refletindo o
   último valor real conhecido.

**Proteção contra dupla execução:** verifica se já existe snapshot para
aquela loja no dia corrente antes de executar.

---

## 10. CORS

O backend está configurado para aceitar requisições do frontend em
`http://localhost:3000` e `http://127.0.0.1:3000`. Para produção, atualize
a lista de origens em `app/main.py`.

---

## 11. Comandos úteis

### Alembic

```bash
# Aplicar todas as migrações pendentes
alembic upgrade head

# Ver qual migração está aplicada atualmente
alembic current

# Desfazer a última migração
alembic downgrade -1

# Gerar nova migração automaticamente (após alterar um modelo)
alembic revision --autogenerate -m "descricao da mudanca"
```

### Seeds e testes

```bash
# Criar ou completar os dados de teste (idempotente, não apaga nada)
python scripts/seed_dev.py
python scripts/seed_produtos.py
python scripts/seed_vendas.py

# Testes (lista completa na seção 3.3)
python scripts/test_auth_web.py
python scripts/test_consulta_rotas.py
```

### Banco (via psql)

```bash
# Listar tabelas
psql -U postgres -d bakery -c "\dt"

# Ver estrutura de uma tabela
psql -U postgres -d bakery -c "\d nome_da_tabela"

# Ver histórico de contagens
psql -U postgres -d bakery -c "SELECT * FROM historico_contagens ORDER BY id DESC LIMIT 10;"
```
