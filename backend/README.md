# Backend — App de Coleta de Dados (Contagem de Estoque)

API em **Python + FastAPI**, com banco de dados **PostgreSQL**, que serve de
backend para o app móvel (PWA) e para a integração com o software web.

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
│   │   └── 0006_niveis_classificacao_produtos.py
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
│   │   ├── dependencies.py    # Extração de negocio_id/loja_id do token (CRÍTICO)
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
│   │   └── produto_classificacao.py   # Valor de cada produto em cada nível
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
│   ├── seed_dev.py             # Cria negócio, loja e usuário de teste
│   └── seed_produtos.py        # Cria produtos de teste e habilita para a loja
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

Aplica as 3 migrações em sequência, criando todas as tabelas:
`negocios`, `lojas`, `usuarios`, `permissoes_web`, `produtos`,
`produtos_lojas`, `estoque_atual`, `historico_contagens`.

### 3.2 Popular dados de teste

```bash
python scripts/seed_dev.py
python scripts/seed_produtos.py
```

Cria:

- **Negócio:** "Rede Padaria Teste"
- **Loja:** "Loja Centro" (horário de zeragem: 06:00)
- **Usuário:** `admin@teste.com` / `senha123`
- **10 produtos:** 6 em UN e 4 em KG (com peso médio cadastrado)
- **Habilitação:** todos os produtos habilitados para a Loja Centro

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
   └─ lojas         (N lojas, cada uma com horario_zeragem próprio)
         └─ usuarios (cada usuário pertence a UMA loja fixa)
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

**Regra fundamental:** `negocio_id` e `loja_id` **nunca** vêm de um parâmetro
enviado pelo app. São sempre extraídos do token JWT validado no backend
(ver `app/core/dependencies.py`). Isso impede que um usuário de um negócio
acesse dados de outro negócio, mesmo alterando parâmetros na requisição.

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

### Seeds

```bash
# Recriar todos os dados de teste do zero
python scripts/seed_dev.py
python scripts/seed_produtos.py
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
