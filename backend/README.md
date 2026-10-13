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
│   │   └── 0014_usuario_tem_acesso_web.py
│   ├── env.py
│   └── script.py.mako
├── alembic.ini
├── app/
│   ├── api/
│   │   ├── auth.py            # /auth/login, /auth/refresh, /auth/logout
│   │   ├── health.py          # /api/health
│   │   ├── produtos.py        # /produtos, /estoque
│   │   └── zeragem.py         # /zeragem/executar-agora
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
│   │   └── evento.py                  # Eventos de demanda atípica + associações com lojas/produtos
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── estoque.py
│   │   └── zeragem.py
│   ├── services/
│   │   ├── estoque_service.py       # Lógica de contagem e cálculo UN/KG
│   │   ├── classificacao_service.py # Monta a classificação de cada produto para o app
│   │   └── zeragem_service.py       # Lógica de zeragem diária por loja
│   └── main.py                 # Ponto de entrada da aplicação
├── scripts/
│   ├── seed_dev.py                     # Negócio, central, 2 lojas, operadores e gestor de teste
│   ├── seed_produtos.py                # Produtos de teste, habilitados em todas as lojas
│   ├── test_constraint_usuario.py      # Testa ck_usuario_tipo_vs_loja_central
│   ├── test_obter_gestor_central.py    # Testa a dependency de acesso ao SaaS
│   └── _check_enums.py                 # Utilitário: lista os tipos enum do PostgreSQL
├── .env.example
├── .gitignore
└── requirements.txt
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

Aplica as 14 migrações em sequência (0001 a 0014). Tabelas criadas:
`negocios`, `centrais_producao`, `lojas`, `usuarios`, `permissoes_web`,
`produtos`, `produtos_lojas`, `estoque_atual`, `historico_contagens`,
`niveis_classificacao`, `produto_classificacoes`, `calendario_producao`,
`eventos`, `eventos_lojas`, `eventos_produtos`.

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

Toda migração tem `downgrade` funcional. Para conferir uma migração nova:
`alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`.

### 3.2 Popular dados de teste

```bash
python scripts/seed_dev.py
python scripts/seed_produtos.py
```

Os dois scripts são idempotentes: podem rodar quantas vezes quiser, sem
duplicar dados (procuram cada registro antes de criar).

Rode **nesta ordem** (o segundo usa as lojas criadas pelo primeiro). Cria:

- **Negócio:** "Rede Padaria Teste"
- **Central de produção:** reaproveita a do negócio, se já existir
- **Lojas:** "Loja Centro" e "Loja Bairro" (horário de zeragem: 06:00)
- **Usuários** (senha `senha123`):

| E-mail | Perfil | App mobile | SaaS web |
| --- | --- | --- | --- |
| `admin@teste.com` | operador da Loja Centro | sim | não |
| `operador.bairro@teste.com` | operador da Loja Bairro | sim | não |
| `gestor@teste.com` | gestor da central | não | sim |

- **11 produtos:** 6 em UN, 4 em KG com peso médio e 1 em KG sem peso médio (pesado na hora)
- **Habilitação:** todos os produtos habilitados em todas as lojas do negócio
- **Classificação** (Categoria/Subcategoria) e **calendário de produção** de exemplo

> O gestor ainda não consegue fazer login: `/auth/login` é a rota do app e
> exige `tem_acesso_app`. As rotas de login do SaaS (`/auth/web/login`,
> `/auth/web/refresh`) estão previstas para a Fase 2.

### 3.3 Scripts de teste

Rodam contra o banco configurado no `.env`, criam os próprios dados de
teste e apagam tudo ao final (também apagam resíduos de execuções
anteriores que tenham quebrado no meio). Terminam com exit 0 se tudo
passou e exit 1 se algum caso falhou.

```bash
# Check constraint entre tipo_usuario, loja_id e central_producao_id (4 casos)
python scripts/test_constraint_usuario.py

# Dependency obter_gestor_central (10 casos). Requer o seed_dev.py.
python scripts/test_obter_gestor_central.py
```

Saída esperada: uma linha `[OK]` por caso e, no fim, `TODOS OS CASOS PASSARAM`.

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
| `obter_usuario_autenticado` | app mobile | usuário ativo + `tem_acesso_app` | `usuario_id`, `negocio_id`, `loja_id` |
| `obter_gestor_central` | SaaS web | usuário ativo + `tem_acesso_web` + `gestor_central` + central do mesmo negócio e ativa | `usuario_id`, `negocio_id`, `central_producao_id` |

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

# Testes
python scripts/test_constraint_usuario.py
python scripts/test_obter_gestor_central.py
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
