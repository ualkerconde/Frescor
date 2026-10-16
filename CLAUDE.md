# CLAUDE.md — Projeto Bakery

Gestão de padaria para redes de supermercado. Um produto, duas portas de entrada sobre o mesmo backend multi-tenant:

- **App mobile (PWA)** — `frontend/` — lojas fazem a contagem de estoque. Já em produção.
- **SaaS web** — `frontend-saas/` (ainda não criado) — a central de produção compila a demanda das lojas, gera ordens de produção e romaneios. Em construção.
- **Backend único** — `backend/` — FastAPI + PostgreSQL + Alembic.

## Leia antes de qualquer trabalho

1. `docs/STATUS.md` — estado atual, decisões em aberto, próximo passo. **Fonte única da verdade.**
2. `docs/documento-referencia-saas-bakery.md` — modelo de dados, regras de negócio do motor de cálculo e roteiro das 8 fases.

Precedência em conflito: `docs/STATUS.md` > documento de referência > qualquer conversa externa. Se faltar uma regra de negócio, **pergunte e registre** em `docs/STATUS.md`; não invente.

## Regra de sincronização (evita versões divergentes)

- Decisão, mudança de escopo ou fase concluída → atualizar `docs/STATUS.md` na mesma sessão, antes de encerrar.
- Mudança de modelo de dados ou de regra de negócio → atualizar também o documento de referência, ou registrar a divergência na seção 2 do `STATUS.md`.
- O projeto também é discutido no claude.ai. Esse chat não é fonte de verdade: o que for decidido lá só vale depois de gravado em `docs/`.

## Stack

Python 3.14 (compatível com 3.11+), FastAPI 0.115, SQLAlchemy 2.0.36, Alembic 1.14, PostgreSQL, Pydantic 2, JWT (python-jose), APScheduler. Frontend: React + Vite (PWA). Ambiente do desenvolvedor: Windows + PowerShell + VS Code.

## Comandos (rodar na pasta `backend/` com o venv ativo)

```powershell
venv\Scripts\Activate.ps1
alembic upgrade head
alembic downgrade -1
python scripts/seed_dev.py
python scripts/seed_produtos.py
python scripts/test_constraint_usuario.py
uvicorn app.main:app --reload      # docs em http://127.0.0.1:8000/docs
```

## Estrutura do backend

- `app/models/` — um arquivo por tabela; `app/models/__init__.py` importa todos (o Alembic precisa disso). Novo model ⇒ registrar lá.
- `app/services/` — lógica de negócio. `app/api/` — routers finos, sem regra de negócio.
- `app/core/dependencies.py` — autenticação e isolamento multi-tenant (**arquivo mais sensível do projeto**).
- `alembic/versions/` — migrations numeradas `NNNN_descricao.py`.
- `scripts/` — seeds e scripts de verificação.

## Regras de ouro

1. **Multi-tenant:** `negocio_id` (e `loja_id`/`central_producao_id`) vêm **sempre** do usuário autenticado, derivado do token e do registro no banco. Nunca de parâmetro, query string ou corpo da requisição. Toda query nova filtra por `negocio_id`.
2. **Gestor de central** (`tipo_usuario = gestor_central`) tem `loja_id = NULL` e `central_producao_id` preenchido. O banco garante isso (`ck_usuario_tipo_vs_loja_central`).
3. Cada loja pertence a exatamente uma central de produção.
4. Rateio em escassez de produção é decisão manual do gestor; o sistema só sugere.
5. Nunca ler, exibir ou commitar o `.env`. No Windows, criar o `.env` do zero (não usar `Copy-Item`: a codificação quebra a conexão com o banco).

## Convenções de código

- Comentários, docstrings e mensagens ao usuário em **português**. Cada model começa com docstring explicando o porquê, não só o quê.
- Enums: `class X(str, enum.Enum)` e coluna com `Enum(X, values_callable=lambda enum_cls: [e.value for e in enum_cls])`. Sem o `values_callable`, o INSERT falha contra o enum do PostgreSQL.
- Python 3.14 + SQLAlchemy 2.0.36: **não** usar `Mapped[Optional[X]]`. Para colunas nullable, usar `mapped_column(...)` sem anotação.
- Migrations: `revision` como string `"NNNN"`, docstring com "ID da revisão / Revisa / Criada em", `downgrade` funcional (será testado: upgrade → downgrade → upgrade). Enums do PostgreSQL criados explicitamente com `checkfirst=True`.
- Colunas novas em tabelas existentes: `server_default` ou `nullable=True`, para não quebrar o app em produção.
- Nomes de tabela no plural em português (`centrais_producao`, `produtos_lojas`).
- Motor de previsão: qualquer mudança no cálculo (`previsao_calculo.py`, `previsao_service.py`, série de vendas, eventos, cold start, sazonal, estatística da base) exige atualizar `VERSAO_METODO` em `app/services/previsao_gravacao.py` **no mesmo commit**. A versão vai gravada em cada previsão e é o que permite saber qual regra gerou cada número.
- Necessidade (Fase 4): qualquer mudança no cálculo (`necessidade_calculo.py` ou nos filtros do `necessidade_service.py`) exige atualizar `VERSAO_METODO_NECESSIDADE` em `app/services/necessidade_calculo.py` **no mesmo commit**. Ela vai gravada em cada ordem de produção.
- Mudança que toque no app mobile (tabelas `estoque_atual`, `historico_contagens`, endpoints de `/produtos`, `/estoque`, `/zeragem`, `/auth`) exige conferir a compatibilidade com ele.

## Como trabalhar

- Rodar migrations e testes de verdade e reportar o resultado real; não afirmar que algo passou sem ter executado.
- Antes de implementar uma fase, conferir as tarefas e o critério de aceite no documento de referência (seção 8).
- Ao terminar: atualizar `docs/STATUS.md` (fase, pendências, log de decisões) e então commitar.
- **Criar e editar arquivos só com as ferramentas de edição de arquivo** (Write/Edit). **Nunca usar heredoc** (`<<EOF`) nem `python -c`/`node -e` com o conteúdo embutido para escrever ou alterar arquivos: o escape de `\`, `\n` e aspas pelo shell já corrompeu arquivos 3 vezes (byte nulo gravado no código, quebra de linha real no meio de uma string, `\s` virando `s` numa regex). O shell fica para rodar comandos.
- Front-end (`frontend-saas/` e mudanças no app mobile): seguir a skill `.claude/skills/frescor-design-system/SKILL.md`.
- Preferência do dono do projeto (Ualker): respostas diretas, críticas e sinceras; separar hipótese de certeza; mostrar riscos, custos e alternativas; priorizar viabilidade e resultado concreto; não inventar capacidades nem resultados; ao ensinar, explicar de forma progressiva com exemplos práticos.
