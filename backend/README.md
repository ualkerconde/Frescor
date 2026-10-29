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
│   │   ├── 0017_extensao_unaccent.py
│   │   ├── 0018_evento_central_e_fks_negocio.py
│   │   ├── 0019_previsoes_diarias.py
│   │   ├── 0020_secao_prazo_tipo_abastecimento.py
│   │   ├── 0021_loja_horario_fechamento.py
│   │   ├── 0022_ordens_producao.py
│   │   ├── 0023_setores_producao.py
│   │   ├── 0024_romaneios.py
│   │   └── 0025_tira_recebimento_da_ordem.py
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
│   │   ├── eventos.py         # SaaS: POST/GET/DELETE /eventos (cadastro mínimo, D24)
│   │   ├── previsoes.py       # SaaS: POST /previsoes/gerar, GET /previsoes, GET /previsoes/qualidade
│   │   ├── producao.py        # SaaS: ordem de produção (gerar, listar, detalhar, ajustar, aprovar, apagar, PDF) e setores
│   │   ├── distribuicao.py    # SaaS: produção real, romaneio (gerar, ajustar, aprovar, apagar, saída, PDF), divergências
│   │   ├── recebimentos.py    # App: /recebimentos (entregas a confirmar e confirmação da loja)
│   │   ├── web.py             # SaaS: /web/me, /web/lojas, /web/produtos (apoio às telas)
│   │   ├── health.py          # /api/health
│   │   ├── produtos.py        # App: /produtos, /estoque
│   │   └── zeragem.py         # App: /zeragem/executar-agora
│   ├── core/
│   │   ├── config.py          # Leitura do .env
│   │   ├── security.py        # Hash de senha + JWT
│   │   ├── dependencies.py    # Autenticação e isolamento multiempresa (CRÍTICO):
│   │   │                      #   obter_usuario_autenticado (app) e obter_gestor_central (SaaS)
│   │   ├── erros_validacao.py # Erros de validação da entrada em português (detail em texto)
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
│   │   ├── perda_diaria.py            # Perda por loja + produto + dia + origem
│   │   ├── previsao_diaria.py         # Previsão gravada por loja + produto + dia, com os componentes
│   │   ├── ordem_producao.py          # Ordem do dia da central (rascunho / aprovada)
│   │   ├── ordem_producao_item.py     # Um item por produto na ordem
│   │   ├── ordem_producao_linha.py    # Uma linha por loja: sugerida, final, conta, avisos
│   │   ├── setor_producao.py          # Setor de produção da central (pão, bolo...): uma folha por setor na impressão
│   │   ├── romaneio.py                # Romaneio da ordem (rascunho / aprovado): quanto vai para cada loja
│   │   ├── romaneio_entrega.py        # Uma entrega por loja: saída e recebimento
│   │   └── romaneio_item.py           # Um item por produto na entrega: sugerida, final, recebida e motivo da diferença
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── estoque.py
│   │   ├── importacao.py
│   │   ├── consulta.py
│   │   ├── evento.py
│   │   ├── previsao.py
│   │   ├── producao.py
│   │   ├── distribuicao.py    # Romaneio, saída, recebimento e divergências
│   │   ├── web.py
│   │   └── zeragem.py
│   ├── services/
│   │   ├── estoque_service.py       # Lógica de contagem e cálculo UN/KG
│   │   ├── classificacao_service.py # Monta a classificação de cada produto para o app
│   │   ├── zeragem_service.py       # Lógica de zeragem diária por loja
│   │   ├── escopo_service.py        # Lojas no escopo do gestor (só a central dele)
│   │   ├── importacao_service.py    # Importação de CSV de vendas/perdas (regras D5-D13)
│   │   ├── consulta_service.py      # Consulta de vendas/perdas (filtros, período, paginação)
│   │   ├── registros_efetivos.py    # D16: com api e manual no mesmo dia, vale o api (único lugar)
│   │   ├── catalogo_service.py      # Lojas e produtos para as telas do SaaS
│   │   ├── sync_vendas_service.py   # STUB da integração com o PDV (não configurada)
│   │   ├── serie_vendas_service.py  # Série diária de vendas por loja + produto (D16, D17, D28)
│   │   ├── previsao_calculo.py      # Núcleo do cálculo, funções puras (base, tendência, sazonal, cold start, eventos)
│   │   ├── previsao_service.py      # Motor por central: junta série, cálculo, proxies e eventos
│   │   ├── previsao_gravacao.py     # Gera e grava 7 dias (substitui a geração anterior); VERSAO_METODO
│   │   ├── previsao_consulta_service.py # Consulta das previsões gravadas e qualidade (teste no passado)
│   │   ├── previsao_metricas.py     # WAPE, viés e o "ingênuo" (mesmo dia da semana passada)
│   │   ├── eventos_service.py       # Eventos da central (escopo D27) e carga para o motor
│   │   ├── necessidade_calculo.py   # Necessidade, funções puras (cobertura, contagem, projeção, margem); VERSAO_METODO_NECESSIDADE
│   │   ├── necessidade_service.py   # Necessidade de todas as lojas + produtos de uma central (lê o banco)
│   │   ├── producao_service.py      # Ordem: gerar, ajustar, aprovar, apagar; trânsito das ordens aprovadas
│   │   ├── producao_consulta_service.py # Leitura das ordens para a API e a tela
│   │   ├── ordem_pdf_service.py     # PDF da ordem aprovada, uma folha por setor (reportlab)
│   │   ├── distribuicao_calculo.py  # Rateio da produção entre as lojas, funções puras (D70)
│   │   ├── distribuicao_service.py  # Produção real, romaneio (gerar, ajustar, aprovar, apagar) e saída
│   │   ├── distribuicao_consulta_service.py # Leitura da distribuição do dia, do romaneio e das divergências
│   │   ├── recebimento_service.py   # Confirmação da loja e o trânsito pelo romaneio (D77–D79, D85, D89)
│   │   └── romaneio_pdf_service.py  # PDF do romaneio aprovado: folha de carga e uma folha por loja
│   └── main.py                 # Ponto de entrada da aplicação
├── scripts/
│   ├── seed_dev.py                     # Negócio, central, 2 lojas, operadores e gestor de teste
│   ├── seed_produtos.py                # Produtos de teste, habilitados em todas as lojas
│   ├── seed_vendas.py                  # ~8 semanas de vendas e perdas das 2 lojas
│   ├── seed_demo_previsao.py           # Negócio separado para ver "Sem previsão" e "Pouco histórico"
│   ├── seed_demo_producao.py           # Negócio separado para a ordem de produção (contagens, setores)
│   ├── backtest_previsao.py            # Teste no passado do motor (WAPE, viés, contra o ingênuo)
│   ├── test_*.py                       # Scripts de teste (ver seção 3.3)
│   └── _check_enums.py                 # Utilitário: lista os tipos enum do PostgreSQL
├── .env.example
├── .gitignore
├── requirements.txt
└── requirements-dev.txt               # Só desenvolvimento: httpx (TestClient) e pypdf (leitura do PDF nos testes)
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

Aplica as 23 migrações em sequência (0001 a 0023). Tabelas criadas:
`negocios`, `centrais_producao`, `lojas`, `usuarios`, `permissoes_web`,
`produtos`, `produtos_lojas`, `estoque_atual`, `historico_contagens`,
`niveis_classificacao`, `produto_classificacoes`, `calendario_producao`,
`eventos`, `eventos_lojas`, `eventos_produtos`, `vendas_diarias`,
`perdas_diarias`, `previsoes_diarias`, `ordens_producao`,
`ordens_producao_itens`, `ordens_producao_linhas`, `setores_producao`.

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
| 0018 | `eventos.central_producao_id` ("todas as lojas" = lojas da central do evento, D27) e `negocio_id` nas associações de eventos, com FKs compostas por negócio |
| 0019 | Cria `previsoes_diarias`: uma linha por loja + produto + dia, com o número, a previsão sem evento e a própria, os componentes (base, tendência, peso, proxy), os eventos aplicados, a versão do método e quem/quando gerou; FKs compostas por negócio |
| 0020 | `centrais_producao.secao` (padaria/açougue/hortifruti, D14) e `prazo_entrega_dias` (padrão 0, D32); `produtos.tipo_abastecimento` (`produzido`/`distribuido`, no lugar de `tem_producao_propria`, D40); `calendario_producao.negocio_id` com FK composta |
| 0021 | `lojas.horario_fechamento` (padrão 21:00, hora local): a contagem vale desde o fechamento da véspera menos 2 h (D44) |
| 0022 | Cria `ordens_producao` (rascunho/aprovada; uma programada por central e dia), `ordens_producao_itens` (por produto) e `ordens_producao_linhas` (por loja: sugerida, final, conta e avisos em JSON, edição, recebimento); FKs compostas; apagar a ordem apaga itens e linhas |
| 0023 | Cria `setores_producao` (por central: nome, ordem, ativo) e `produtos.setor_producao_id` opcional (D67) |
| 0024 | Cria `romaneios` (rascunho/aprovado; um por ordem), `romaneios_entregas` (uma por loja: saída e recebimento) e `romaneios_itens` (por produto: sugerida, final, recebida, motivo da diferença); quem/quando registrou a produção em `ordens_producao_itens`; FKs compostas; a ordem com romaneio não pode ser apagada; apagar o romaneio apaga entregas e itens |
| 0025 | Tira `quantidade_recebida`/`recebido_em` da linha da ordem: o recebimento passa a ser do romaneio (D79) |

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

**Demonstração da tela de previsão** (opcional): `python scripts/seed_demo_previsao.py`
cria um negócio **separado**, "Rede Demo Previsão", com o gestor
`gestor.demo@teste.com` / `senha123` e a loja `D01`. Lá aparecem os dois estados
que o seed principal não tem: **DEMO-03** com "Pouco histórico" (só 2 semanas de
venda) e **DEMO-04** com "Sem previsão" (sem venda e sem produto da mesma
unidade na loja para comparar). É separado porque os testes contam o seed
principal (11 produtos, lojas 001/002). Idempotente; a cada execução a janela
acompanha a data de hoje. Depois, entre na tela de previsão com o gestor demo e
clique em "Gerar previsão".

**Demonstração da ordem de produção** (opcional): `python scripts/seed_demo_producao.py`
cria outro negócio **separado**, "Rede Demo Produção" (gestor
`gestor.producao@teste.com` / `senha123`; central padaria com prazo 0; lojas
`P01` e `P02`), com 8 semanas de vendas e perdas, **contagens no fechamento de
hoje (21h)** e 7 produtos, cada um com um caso da necessidade: validade de 1 dia,
margem própria, cobertura maior que a validade, contagem antiga, nunca contado,
**distribuído**, pouco histórico e sem calendário. Tem os setores "Pães", "Bolos e
doces" e "Salgados", e a Empada **sem setor**. É separado porque a Loja 001 do
seed principal tem contagens reais feitas no app. Idempotente; a janela acompanha
a data de hoje (rode de novo em outro dia para as contagens valerem para amanhã).
Depois, entre na tela "Produção" e clique em "Gerar ordem".

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

# Fase 3 — motor de previsão
python scripts/test_serie_vendas.py           # série diária de vendas (D16, D17) (21)
python scripts/test_previsao_calculo.py       # núcleo do cálculo, sem banco: base, tendência (21)
python scripts/test_previsao_eventos.py       # eventos fora da base e ajuste do dia (24)
python scripts/test_eventos_rotas.py          # POST/GET/DELETE /eventos, escopo e erros em português (44)
python scripts/test_previsao_cold_start.py    # produto novo e loja nova, proxies (15)
python scripts/test_previsao_sazonal.py       # ramo sazonal e vigência (14)
python scripts/test_previsao_metricas.py      # WAPE, viés e ingênuo (6)
python scripts/test_previsoes_gravadas.py     # gravação de 7 dias, substituição, trava (15)
python scripts/test_previsoes_rotas.py        # API de previsão: gerar, consultar, qualidade (26)
python scripts/test_aceite_fase3.py           # critério de aceite da Fase 3: os 5 cenários (6)

# Fase 4 — necessidade e ordem de produção
python scripts/test_abastecimento_modelo.py   # migrations 0020/0021: seção, prazo, tipo, calendário, fechamento (15)
python scripts/test_seeds_fase4.py            # seeds da Fase 4 (rode seed_produtos e seed_demo_producao antes) (12)
python scripts/test_necessidade_calculo.py    # necessidade, sem banco: cobertura, contagem, prazo 0 e 1, trânsito (22)
python scripts/test_necessidade_service.py    # necessidade com banco: quem entra, de onde vem cada entrada (13)
python scripts/test_ordens_modelo.py          # migration 0022: regras de banco das ordens (22)
python scripts/test_producao_service.py       # gerar, ajustar, aprovar, apagar; trânsito da ordem aprovada (18)
python scripts/test_producao_rotas.py         # API da ordem: 401/403, 404/409/422, escopo (19)
python scripts/test_ordem_pdf.py              # PDF da ordem aprovada: uma folha por setor, filtro, 409, 404 (12)
python scripts/test_aceite_fase4.py           # critério de aceite da Fase 4, de ponta a ponta pela rota (7)

# Fase 5 — distribuição, romaneio e recebimento
python scripts/test_romaneios_modelo.py       # migration 0024: regras de banco do romaneio (31)
python scripts/test_distribuicao_calculo.py   # rateio, sem banco: pela final, sobra, falta, arredondamento (15)
python scripts/test_distribuicao_service.py   # produção real, romaneio, aprovar, saída (24)
python scripts/test_recebimento_transito.py   # confirmação da loja e trânsito pelo romaneio; migration 0025 (18)
python scripts/test_distribuicao_rotas.py     # API da distribuição: 401/403, 404/409/422, escopo (26)
python scripts/test_recebimentos_rotas.py     # API do app /recebimentos: loja do token, erros (17)
python scripts/test_romaneio_pdf.py           # PDF do romaneio: carga + folha por loja, filtro, 409, 422 (10)
python scripts/test_aceite_fase5.py           # aceite da Fase 5 pelas rotas, prazo 1 (12) — ver nota abaixo
```

> **Nota do `test_aceite_fase5.py`:** ele usa o relógio real e para com aviso
> se a data de São Paulo for diferente da do servidor (só acontece num
> servidor em UTC entre 21h e 0h de São Paulo). No Windows, com o relógio em
> São Paulo, isso não acontece. O `test_seeds_fase4.py` espera os dados do
> seed demo até ontem: se a data virou desde o último seed, rode o
> `seed_demo_producao.py` de novo antes.

Saída esperada: uma linha `[OK]` por caso e, no fim, `TODOS OS CASOS PASSARAM`
(ou `N verificações; TODAS PASSARAM`).

Teste no passado do motor, com o seed (não é teste de unidade; leva alguns segundos):

```bash
python scripts/backtest_previsao.py   # WAPE e viés por produto e dia da semana, contra o ingênuo
```

Termina com dois critérios `[OK]` (vence o ingênuo; reencontra o perfil
semanal do seed) e um `[aviso]` com os produtos que não vencem o ingênuo
(hoje INT-001, INT-002 e INT-006 — provável ruído do seed, ver D31 no STATUS).

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

### SaaS web — eventos (exigem token do SaaS)

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/eventos` | Cria (201) um evento da central do gestor: `nome`, `data_inicio`, `data_fim` (até 366 dias), `tipo_ajuste` (`multiplicador` ou `valor_fixo`), `valor_ajuste`, `escopo_loja` (`todas` = lojas da central, ou `especificas` com `loja_ids`), `produto_ids` (vazio = todos). Erro de validação → 422 com mensagem em português. |
| `GET` | `/eventos?data_inicio=&data_fim=` | Eventos que valem para a central (datas opcionais: só os que tocam o período). |
| `DELETE` | `/eventos/{id}` | Apaga (204). Fora do escopo ou inexistente → 404; evento que vale também para outra central → 403. |

Editar = apagar e criar de novo (API mínima, D24). Regras do ajuste: D26 no STATUS.

### SaaS web — previsão (exigem token do SaaS)

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/previsoes/gerar` | Corpo opcional `{"data_referencia": "AAAA-MM-DD"}` (padrão: ontem; hoje ou futuro → 422). Calcula e grava os 7 dias seguintes da central, substituindo a geração anterior (tudo ou nada). Resposta: período, `gravadas`, `sem_previsao`, `substituidas`, `versao_metodo`. |
| `GET` | `/previsoes?data=&loja_id=&produto_id=` | Previsões gravadas de um dia (padrão: amanhã), com os componentes (base, tendência, peso do histórico, proxy, eventos), `pouco_historico`, a venda do mesmo dia da semana passada e `totais` por unidade. Lista vazia = ainda não gerou para esse dia. `previsao` nula = sem previsão (sem histórico e sem referência). Loja fora do escopo → 404. |
| `GET` | `/previsoes/qualidade?data_inicio=&data_fim=&loja_id=&produto_id=` | Teste no passado sob demanda (até 28 dias; padrão: as 4 semanas até ontem): WAPE e viés do motor e do ingênuo, **por unidade** (frações com 4 casas: `0.1165` = 11,65%). Calculado na hora (~1 s no seed): antes de cliente real, precisa de cache ou job noturno. |

Valores decimais chegam como texto (ex.: `"44.1234"`).

### Motor de previsão (Fase 3)

Para cada loja + produto + dia (detalhes e números nas decisões D16–D31 do `docs/STATUS.md`):

1. **Série de vendas** efetiva (D16: vale o `api` sobre o `manual`); dia sem linha é zero se a loja vendeu algo naquele dia, senão faltante (D17). Só produto ativo, habilitado e vigente; loja ativa.
2. **Base** = mediana do mesmo dia da semana nas últimas 6 semanas (D18, D25). Dias de evento ficam fora.
3. **Tendência** = mediana das razões real ÷ base dos últimos 7 dias, limitada a 0,7–1,3; com menos de 5 dias, fator 1 (D19, D31).
4. **Sazonal** (`ciclo_previsao = sazonal`) com temporada anterior: base do mesmo período do ano anterior e tendência contra ele; na 1ª temporada, segue o semanal com cold start (F5, versão mínima).
5. **Cold start**: com menos de 6 semanas de histórico, mistura a própria com um proxy (outras lojas, mesma categoria ou mesma unidade) com peso crescente (D20, D28, D29). Sem nenhuma referência: sem previsão.
6. **Evento** do dia: multiplicador ou valor fixo (D26).
7. Sem arredondar (D21); gravada com 4 casas.

Qualquer mudança no cálculo exige atualizar `VERSAO_METODO` em `app/services/previsao_gravacao.py` no mesmo commit (hoje `2026.10-v2`); a versão vai gravada em cada previsão.

### SaaS web — ordem de produção (exigem token do SaaS)

A central vem do token: nenhuma rota recebe `central_id`. Erros: **404** ordem ou linha fora do escopo (mesma resposta para outra central, outro negócio e inexistente); **409** ordem aprovada (não é ajustada, gerada de novo nem apagada) e imprimir ordem que não foi aprovada; **422** regra ferida, em português.

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/producao/ordens/gerar` | Corpo opcional `{"data_producao"}` (padrão amanhã; de hoje até 6 dias à frente). Atualiza a previsão se estiver desatualizada, calcula a necessidade (com o trânsito das ordens aprovadas) e grava a ordem em **rascunho**, substituindo o rascunho do dia. Final = sugerida. |
| `GET` | `/producao/ordens?data=` | Ordens do dia em resumo: situação, totais por unidade, `linhas_editadas` (perdidas se o rascunho for gerado de novo), `linhas_sem_quantidade`. |
| `GET` | `/producao/ordens/{id}` | Itens por produto (total sugerido e final = soma das lojas) e linhas por loja (quantidades, avisos, a conta da necessidade). |
| `PATCH` | `/producao/ordens/{id}/linhas/{linha_id}` | `{quantidade_final, motivo?}` (UN inteiro; KG até 3 casas). Só rascunho. |
| `POST` | `/producao/ordens/{id}/aprovar` | Exige quantidade em todas as linhas e lojas ativas na central. Aprovada fica travada e vira trânsito das próximas ordens. |
| `DELETE` | `/producao/ordens/{id}` | Apaga um rascunho (204). |
| `GET` | `/producao/ordens/{id}/pdf?setores=1,2,sem` | PDF da ordem **aprovada**, uma folha por setor (vazio = todos; `sem` = produtos sem setor). Só produtos produzidos. |
| `GET` | `/producao/setores` | Setores de produção da central, na ordem. |

### Necessidade (Fase 4)

Para cada loja + produto na data de produção D (decisões D32–D62 do `docs/STATUS.md`):

1. **Chegada** = D + prazo de entrega da central; **cobertura** = da chegada até a véspera da próxima chegada pelo calendário do produto, limitada à validade (contada da fabricação).
2. **Mínimo** = soma da previsão **gravada** de cada dia da cobertura; dia fora da vigência conta 0.
3. **Alvo** = mínimo × (1 + margem): a do produto, 10% sem margem, pelo menos 20% com pouco histórico.
4. **Estoque na chegada** = contagem válida (desde o fechamento da véspera − 2 h, hora de São Paulo) + trânsito das ordens aprovadas − venda prevista até a chegada, sem o que vence antes.
5. **Necessidade** = alvo − estoque na chegada, para cima (UN inteiro; KG em 0,1 kg).

Qualquer mudança nesse cálculo (ou nos filtros do `necessidade_service.py`) exige atualizar `VERSAO_METODO_NECESSIDADE` em `app/services/necessidade_calculo.py` no mesmo commit (hoje `2026.10-n2`); a versão vai gravada em cada ordem.

Desde a Fase 5 (n2), o trânsito vem do **romaneio** quando a ordem tem um: a entrega com saída entra pela final do romaneio; a confirmada pela loja depois da contagem entra pela recebida; a sem confirmação (ou confirmada com atraso) conta como chegada no dia de entrega, antes da contagem (D89), e aparece com a marca "sem confirmação" / "confirmada com atraso". Sem romaneio, vale a final da ordem, como antes (D52).

### SaaS web — distribuição e romaneio (exigem token do SaaS)

A central vem do token. Erros: **404** fora do escopo; **409** ordem não programada/aprovada (D88), romaneio aprovado (não muda mais) ou rascunho na impressão; **422** regra ferida, em português (soma das lojas acima do produzido, D71; quantidade inválida; loja fora do romaneio no filtro).

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/distribuicao/ordens/{ordem_id}/producao` | `{itens: [{item_id, quantidade}]}`: o produzido de cada produto (ou o disponível, no distribuído). Pode corrigir até o romaneio ser aprovado (D87). |
| `GET` | `/distribuicao/romaneios?data_entrega=` | Ordens do dia com a produção e o resumo do romaneio (D92). |
| `POST` | `/distribuicao/romaneios/gerar` | `{ordem_id}`: rateia a produção pela final da ordem (D70) e grava o romaneio em rascunho, substituindo o rascunho anterior. |
| `GET` | `/distribuicao/romaneios/{id}` | Entregas por loja com os itens, a situação de cada entrega (calculada na leitura) e a produção por produto. |
| `PATCH` | `/distribuicao/romaneios/{id}/itens/{item_id}` | `{quantidade_final, motivo?}`. Só rascunho. |
| `POST` | `/distribuicao/romaneios/{id}/aprovar` | Recusa se a soma das lojas passar do produzido. Aprovado fica travado. |
| `DELETE` | `/distribuicao/romaneios/{id}` | Apaga um rascunho (204). |
| `POST` | `/distribuicao/romaneios/{id}/saida` | `{entrega_ids?}` (ausente = todas as que aguardam saída): registra a saída da central. |
| `GET` | `/distribuicao/romaneios/{id}/pdf?lojas=1,2` | PDF do romaneio aprovado: folha de carga e uma folha por loja (vazio = todas). |
| `GET` | `/distribuicao/divergencias?data_inicio=&data_fim=` | O que as lojas confirmaram diferente do enviado (falta, avaria, a mais, outro), com totais. |

### App — recebimento (exige o token do app)

A loja vem do usuário autenticado; não há loja na URL nem no corpo. Sem token → 403 (D93), como o resto do app.

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/recebimentos` | Entregas da loja com saída registrada, ainda não confirmadas e dentro do prazo (até o fim do dia seguinte ao da entrega, D85). |
| `GET` | `/recebimentos/{entrega_id}` | Uma entrega da loja, com os itens. |
| `POST` | `/recebimentos/{entrega_id}/confirmar` | `{diferencas: []}` = "Recebi tudo certo"; com diferença, só os itens que vieram diferentes: `{item_id, quantidade_recebida, motivo, observacao?}` (`outro` exige a observação). Uma vez só. |

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
python scripts/seed_demo_previsao.py   # opcional: demonstração da tela de previsão
python scripts/seed_demo_producao.py   # opcional: demonstração da ordem de produção

# Testes (lista completa na seção 3.3)
python scripts/test_auth_web.py
python scripts/test_consulta_rotas.py
python scripts/test_aceite_fase3.py
python scripts/test_aceite_fase4.py
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
