# Implantação do piloto — roteiro

Roteiro para colocar a versão do PR #4 em produção e cadastrar o primeiro cliente. **Onde** o backend roda hoje (servidor, banco, domínio) não está registrado em `docs/`: preencher a seção 0 antes de seguir.

## 0. Ambiente de produção (preencher)

| Item | Valor |
|---|---|
| Servidor da API (FastAPI) | _a preencher_ |
| PostgreSQL (versão, onde) | _a preencher_ |
| Domínio do app mobile (PWA) | _a preencher_ |
| Domínio do SaaS web | _a preencher_ |
| Servidor da frente (nginx ou outro) | _a preencher_ |
| Backup do banco (como e onde) | _a preencher_ |

## 1. Antes de mexer no banco

1. **Backup** do banco de produção (`pg_dump -Fc`), guardado fora do servidor. Sem backup, não seguir: as migrations têm downgrade, mas dado apagado por engano não volta.
2. Na pasta `backend/`, com o `.env` de produção:
   `python scripts/verificar_pre_deploy.py`
   - **[BLOQUEIA]** resolve antes. Ex.: códigos de produto repetidos (a 0016 para) ou falta a extensão `unaccent` (instalar o pacote `postgresql-contrib`).
   - **[ATENÇÃO]** leia e decida. Ex.: vínculos produto × loja desativados somem da contagem do app (D100); SECRET_KEY curta; CORS vazio.

## 2. Backend

1. `git pull` na versão aprovada e `pip install -r requirements.txt`.
2. `.env` de produção, criado do zero, **nunca copiado** (no Windows o `Copy-Item` quebra a codificação). Campos novos:
   - `ENVIRONMENT=production`;
   - `CORS_ORIGINS=https://<domínio do app>,https://<domínio do SaaS>` (vírgula entre as origens). Sem isso, só as origens de desenvolvimento são aceitas.
3. `alembic upgrade head`, depois `alembic current` (tem de mostrar o último número de `alembic/versions/`).
4. Reiniciar a API. Abrir `/docs` e testar o login do app com um usuário real.
5. **Servidor da frente:**
   - limite de corpo de requisição (ex.: `client_max_body_size 6m;` no nginx), porque o limite de 5 MB do upload só vale depois do recebimento;
   - HTTPS obrigatório, porque o app usa a câmera.

## 3. SaaS web

1. Na pasta `frontend-saas/`: `npm ci` e `VITE_API_URL=https://<domínio da API> npm run build`.
2. Publicar a pasta `dist/` no domínio do SaaS. Toda rota desconhecida tem de cair no `index.html` (SPA).
3. Entrar com um gestor e abrir cada tela do menu.

## 4. Cliente novo

1. Copiar `backend/scripts/exemplo_implantacao.json` e preencher:
   - negócio;
   - central (seção, prazo de entrega);
   - lojas (código igual ao do sistema de vendas do cliente; horário de fechamento);
   - gestores e operadores (nome, e-mail).
2. `python scripts/implantar_cliente.py cliente.json`: só simula. Confira a lista.
3. `python scripts/implantar_cliente.py cliente.json --aplicar`: grava e mostra **uma vez** a senha provisória de cada usuário criado.
   - Entregue cada senha por canal privado.
   - **Ainda não há tela de troca de senha:** pendência antes do cliente usar de verdade.
4. O gestor, na tela **Cadastros**, faz:
   - setores;
   - produtos (com o código do PDV);
   - dias de produção;
   - produtos de cada loja.
5. **Histórico de vendas** (D109: pelo menos 1 ano, ideal 2): pela API do cliente, quando definida (D108), ou por CSV em *Integração de vendas → Carga de histórico*. Sem 1 ano de histórico, os fatores de ano anterior e de semana e dia do mês ficam neutros.
6. **Integração de vendas** (tela *Integração de vendas*): configurar a busca diária ou entregar a chave de envio ao fornecedor do sistema do cliente.

## 5. Depois do primeiro dia

- Gerar a previsão e a ordem de produção do dia seguinte e conferir "Ver a conta" de alguns produtos.
- Depois de uma semana com venda real: rodar o `scripts/backtest_fatores.py` adaptado à venda do cliente, para decidir se cada fator de calendário fica ligado (D114).
