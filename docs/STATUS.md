# STATUS — Projeto Bakery (SaaS web + app)

> **Fonte única da verdade sobre o andamento.** Atualizado em: 2026-10-13.
> Precedência em caso de conflito: **este arquivo** > `documento-referencia-saas-bakery.md` > qualquer conversa externa (claude.ai, etc.).
> Toda decisão nova, mudança de escopo ou fase concluída deve ser registrada aqui **na mesma sessão** em que acontece.

---

## 1. Andamento das fases

Roteiro completo, com tarefas e critérios de aceite: `documento-referencia-saas-bakery.md`, seção 8.

| Fase | Situação | Observações |
|---|---|---|
| 1 — Fundação de dados | **Concluída (2026-10-13)** | Migrations 0007–0014, models, seeds e testes verificados; app mobile testado no iPhone. |
| 2 — Ingestão de vendas e perdas | Planejamento | D1 e D4 decididas; `obter_gestor_central` pronta e testada. Plano em discussão (2026-10-13). |
| 3 — Motor de previsão | Não iniciada | |
| 4 — Necessidade e produção | Não iniciada | |
| 5 — Distribuição | Não iniciada | |
| 6 — Frontend do SaaS (`frontend-saas/`) | Não iniciada | Pasta ainda não existe |
| 7 — Validação com dado real | Não iniciada | Depende de cliente piloto (D3) |
| 8 — Refino V1.5 | Não iniciada | |

### Fase 1 — o que existe no código (lido em 2026-10-13)

- Migrations: `0007_central_producao`, `0008_loja_central_producao_id`, `0009_usuario_tipo_e_central`, `0010_produto_campos_producao`, `0011_produto_loja_ativo`, `0012_calendario_producao`, `0013_evento_e_associacoes`.
- Migration `0014_usuario_tem_acesso_web` (consequência de D1, 2026-10-13): coluna `usuarios.tem_acesso_web` (Boolean, NOT NULL, `server_default false`) e campo correspondente no model `Usuario`. Verificada: upgrade 0013→0014, downgrade 0014→0013 (coluna removida), upgrade de novo, todos com exit 0. Usuários existentes ficaram com `false`; `test_constraint_usuario.py` passou de novo (4/4); health check 200 e `POST /auth/login` igual a antes (200 para os operadores, 403 para o gestor).
- Dependency `obter_gestor_central` em `app/core/dependencies.py` (2026-10-13), devolve `GestorCentralAutenticado(usuario_id, negocio_id, central_producao_id)`, sempre lidos do registro atual no banco. Regras:
  - **401**: token ausente, malformado, inválido, expirado, refresh token no lugar de access, ou usuário inexistente. Usa um esquema próprio (`bearer_scheme_web = HTTPBearer(auto_error=False)`), porque o `HTTPBearer` padrão do FastAPI 0.115 responde **403** para token ausente.
  - **403**: usuário bloqueado; `tem_acesso_web = False`; `tipo_usuario` diferente de `gestor_central`; central inexistente ou de outro negócio (checagem extra: nada no banco impede uma central de outro negócio no usuário); ou central inativa (D4).
  - Não lê `tem_acesso_app`.
  - A validação do token foi extraída para `_carregar_usuario_do_token`, usada também pela `obter_usuario_autenticado`, com os mesmos passos na mesma ordem. Regressão conferida em `GET /produtos`: 200 com token válido, 403 sem token, 401 com token inválido, iguais ao comportamento anterior. `/auth/login` e `/auth/refresh` não foram alterados.
  - Verificado após a mudança: `test_constraint_usuario.py` 4/4 e health check 200.
  - **Testada em 2026-10-13** por `scripts/test_obter_gestor_central.py` (9 casos, 2 execuções seguidas, exit 0, banco limpo ao final): gestor do seed → 200 com `negocio_id=1`, `central_producao_id=1`; sem token, token inválido, expirado e refresh no lugar de access → 401; operador de loja (mesmo com `tem_acesso_web`), gestor sem `tem_acesso_web`, gestor bloqueado e gestor com central de outro negócio → 403, conferindo também a mensagem. Tokens gerados direto (`criar_access_token`); cada chamada passa pelo `bearer_scheme_web` com uma requisição montada. Sem `TestClient`, porque `httpx` não está instalado no venv.
  - Com D4, o script ganhou o caso 8 (central inativa → 403): 10/10, exit 0.
  - **Checagem de mutação:** o script foi rodado contra cópias da dependency sem a checagem de `tem_acesso_web`, sem a checagem de central do mesmo negócio e sem a checagem de central inativa. Em cada uma falhou exatamente o caso correspondente (5, 7 e 8), com exit 1. O arquivo real não foi alterado.
- Models: `CentralProducao`, `CalendarioProducao` (+ `DiaSemana`), `Evento`, `EventoLoja`, `EventoProduto` (+ `EscopoLoja`, `EscopoProduto`, `TipoAjuste`). Campos novos em `Produto`, `ProdutoLoja.ativo`, `Usuario.tipo_usuario`/`central_producao_id`, `Loja.central_producao_id` (obrigatório).
- Check constraint no banco: `ck_usuario_tipo_vs_loja_central` (operador_loja ⇒ loja_id preenchido e central nula; gestor_central ⇒ central preenchida e loja nula).
- Não há mais `estoque_minimo`/`estoque_maximo` em `produtos_lojas`, e nenhum código da API ou dos serviços os referencia.
- `UsuarioAutenticado.loja_id` já é `Optional[int]`.
- `scripts/test_constraint_usuario.py` existe (4 casos: 2 inválidos, 2 válidos).

### Fase 1 — verificação (concluída em 2026-10-13)

Na pasta `backend/`, com o venv ativo:

```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
python scripts/test_constraint_usuario.py
python scripts/seed_dev.py
uvicorn app.main:app --reload
```

Depois: abrir `/api/health`, e fazer login e uma contagem de estoque no app mobile (compatibilidade com o que já está em produção).

- [x] upgrade / downgrade / upgrade sem erro (2026-10-13: 0013 → 0012 → 0013, exit 0)
- [x] `test_constraint_usuario.py` — 4 casos passam (2026-10-13: a 1ª execução quebrou com `UnicodeEncodeError` ao imprimir o emoji `✅` no console cp1252, antes da limpeza. O script foi corrigido (saída `[OK]`/`[FALHA]`, limpeza de resíduos no início e limpeza final em `try/finally` próprio) e passou 2 vezes seguidas, exit 0, sem deixar dados no banco)
- [x] app mobile continua funcionando (login + contagem) — 2026-10-13, teste manual do Ualker no iPhone: login, contagem e leitor de código de barras ok (o leitor precisou de correção, ver pendência 6).
- [x] seed + health check ok (2026-10-13: `seed_dev.py` rodou 2 vezes sem duplicar; `GET /api/health` → 200 `{"status":"ok","database":"conectado"}`. Teste extra pela API: `POST /auth/login` → 200 para `admin@teste.com` e `operador.bairro@teste.com`, 403 para `gestor@teste.com`, como esperado)

### Fase 1 — pendências identificadas (fora da verificação)

1. **`seed_dev.py` (corrigido em 2026-10-13).** Agora é idempotente e garante: negócio `Rede Padaria Teste`; 1 central (reaproveita a existente do negócio: no banco de dev é a `Central Principal (Padrão)`, criada pela migration 0008); lojas `Loja Centro` e `Loja Bairro`; operadores `admin@teste.com` e `operador.bairro@teste.com` (`tem_acesso_app=True`); gestor `gestor@teste.com` (`gestor_central`, `tem_acesso_app=False`). Senha `senha123`. Depois da migration 0014, o gestor passou a ter `tem_acesso_web=True`: o seed **atualizou** o usuário 27 (mesmo id e `criado_em`), sem recriá-lo.
2. **`backend/README.md` (atualizado em 2026-10-13):** migrations 0001–0014 com o que cada uma faz, models novos, as duas dependencies de autenticação, seeds (o que criam, ordem, idempotência) e scripts de teste (como rodar, saída esperada).
3. **Resíduos de teste no banco de desenvolvimento (resolvido em 2026-10-13):** havia dois negócios de teste sobrando (`_Teste Constraint`, id 3, de uma versão antiga do script; e `_Teste Constraint 16588216`, id 6, da execução que quebrou), com suas centrais, lojas e usuários. Nenhuma outra tabela apontava para eles. Foram apagados pela limpeza inicial do script corrigido. Os negócios 1 (`Rede Padaria Teste`) e 2 (`Pais e Filhos`) foram mantidos.
4. **`seed_produtos.py` (corrigido em 2026-10-13):** agora habilita cada produto em todas as lojas do negócio. Rodou 2 vezes: na 1ª criou 11 habilitações para a `Loja Bairro` (0 para a `Loja Centro`, que já tinha); na 2ª, 0 em ambas. Banco: 11 produtos × 2 lojas, nenhum par duplicado (o banco também impede: `uq_produto_loja`).
5. **Observação (não bloqueia):** `seed_produtos.py` usa o primeiro negócio do banco (`order by id`), não o negócio pelo nome como o `seed_dev.py`. No banco de dev é o mesmo (id 1); só faria diferença num banco onde outro negócio tenha sido criado antes.
6. **App mobile — leitor de código de barras com tela preta no iPhone (resolvido em 2026-10-13).**
   - **Sintoma:** iPhone + Safari, em HTTPS (no navegador e instalado na tela inicial): ao tocar no leitor abria uma tela preta, sem imagem e sem mensagem.
   - **Descartado:** contexto não seguro (o app já rodava em HTTPS com proxy `/backend`).
   - **Causa:** montagem dupla do efeito pelo `React.StrictMode` em dev, com as duas aberturas compartilhando o mesmo `<video>`; a primeira, ao parar, zerava a imagem da segunda. Confirmada **indiretamente**: a correção que isola as aberturas resolveu. Como a correção também trouxe `getUserMedia` próprio e limites de tempo, não houve teste isolado de cada mudança.
   - **Correção (`frontend/src/components/BarcodeScanner.jsx`):** `<video>` próprio por abertura; `getUserMedia` feito pelo componente e entregue ao ZXing (`decodeFromStream`); limites de 20 s (liberação) e 8 s (imagem) com "Tentar novamente"; nome técnico do erro na mensagem; câmera sempre desligada ao fechar, detectar, falhar, estourar o tempo ou o app ir para segundo plano. `StrictMode` mantido.
   - **Teste do Ualker no iPhone (2026-10-13):** leitura ok, fechar no ✕ ok, trocar de app ok, abrir/fechar várias vezes ok.

### Pendências registradas para a Fase 2

- **Rotas de login do SaaS: `/auth/web/login` e `/auth/web/refresh`.** Os endpoints atuais `/auth/login` e `/auth/refresh` recusam usuários com `tem_acesso_app = False`, então um gestor só com `tem_acesso_web` ainda **não consegue obter um token**. As rotas novas devem exigir `tem_acesso_web` e ficar separadas das do app mobile, sem alterar estas. Até lá, o teste da `obter_gestor_central` gera o token direto (`criar_access_token`). Decidido em 2026-10-13.

---

## 2. Divergências entre o documento de referência e o código

O documento é planejamento. Onde o código diverge, **vale o código** (e este arquivo registra a divergência).

| Tema | Documento | Código real |
|---|---|---|
| Nomes de tabela | singular (`central_producao`, `evento`, `produto_loja`) | `centrais_producao`, `eventos`, `eventos_lojas`, `eventos_produtos`, `produtos_lojas`, `calendario_producao` |
| Eventos | uma entidade `evento` | `eventos` + tabelas de associação `eventos_lojas` e `eventos_produtos` (usadas quando o escopo é "específicas"/"específicos"); `valor_ajuste` é `Numeric(10,4)` |
| Isolamento multi-tenant (§6) | recomenda schema/banco por cliente | Tabelas compartilhadas, com `negocio_id` em tudo e isolamento via JWT (ver D2) |
| Login do gestor (§3.1) | gestor com escopo de central; não fala em flag de acesso ao SaaS | Campo novo `usuarios.tem_acesso_web` (migration 0014, D1 = A), separado de `tem_acesso_app`. A dependency `obter_gestor_central` exige `tem_acesso_web` e `gestor_central` (passo 5, 2026-10-13); `obter_usuario_autenticado` e `/auth/login` continuam exigindo `tem_acesso_app` (rotas `/auth/web/*` ficam para a Fase 2) |

---

## 3. Decisões em aberto

| ID | Decisão | Opções | Recomendação | Status |
|---|---|---|---|---|
| D1 | Como o gestor de central autentica no SaaS web | **A)** nova flag `tem_acesso_web` no usuário (migration 0014) + dependency `obter_gestor_central` que valida `tipo_usuario` e `central_producao_id` no banco. **B)** reaproveitar `tem_acesso_app`. | A: separa as duas portas de entrada; em B o gestor ganharia acesso ao app mobile só para conseguir logar. | **Decidida em 2026-10-13: opção A.** |
| D2 | Isolamento: schema/banco por cliente (doc §6) vs. `negocio_id` em tabelas compartilhadas (código atual) | A) manter tabelas compartilhadas; B) migrar para schema por cliente | Não recomendado de forma conclusiva ainda: o doc diz "recomendado", não "decidido". Trocar depois de ter clientes reais é caro, então decidir **antes do primeiro cliente real**. Enquanto isso, toda query nova **deve** filtrar por `negocio_id` vindo do token. | Aberta. Não bloqueia as Fases 2–4. |
| D3 | Cliente piloto e acesso aos dados de venda (PDV) | — | Definir cedo: a Fase 7 depende disso. Alternativa de baixo custo: usar os dados do MVP de loja única (planilha) para testar a Fase 3. | Não definido. |
| D4 | Central de produção inativa (`centrais_producao.ativa = false`) bloqueia o acesso do gestor ao SaaS? | **A)** sim: `obter_gestor_central` responde 403. **B)** não: o gestor entra e só vê a central como inativa (ex.: para consultar histórico). | Sem recomendação: depende de como o cliente usa a desativação de central. | **Decidida em 2026-10-13: opção A** (central inativa bloqueia o gestor, 403). Implementada em `obter_gestor_central`. |

---

## 4. Log de decisões

- **2026-10-06** — Roteiro de 8 fases e documento de referência criados (conversa de planejamento no claude.ai).
- **2026-10-13** — O desenvolvimento passa a ser feito **somente com o Claude** (sem GitHub Copilot). O executor principal é o Claude Code no VS Code, no repositório.
- **2026-10-13** — `docs/` e `CLAUDE.md` no repositório passam a ser a fonte única da verdade. Conversas no claude.ai servem para planejamento solto; o que virar decisão é gravado aqui.
- **2026-10-13** — **D1 decidida: opção A.** O gestor de central entra no SaaS web por uma flag nova `tem_acesso_web` no usuário, separada de `tem_acesso_app` (migration 0014). A autorização no SaaS fica na dependency `obter_gestor_central`, que exige `status = ativo`, `tem_acesso_web = True` e `tipo_usuario = gestor_central`.
- **2026-10-13** — **D4 decidida: opção A.** Gestor cuja central está inativa (`centrais_producao.ativa = false`) é recusado pela `obter_gestor_central` com 403 e mensagem própria ("A central de produção vinculada ao seu usuário está inativa"). Coberto pelo caso 8 de `test_obter_gestor_central.py`.
- **2026-10-13** — Removido `backend/scripts/_fix_migrations_encoding.py` (script temporário, sem uso, que reescrevia as migrations 0012 e 0013 se executado).
- **2026-10-13** — **Fase 1 concluída.** Último item: teste do app mobile no iPhone (login, contagem e leitor de código de barras, este após correção do `BarcodeScanner`).

(Decisões anteriores já fechadas: ver `documento-referencia-saas-bakery.md`, seção 10.)

---

## 5. Próximo passo

1. ~~Teste do app mobile (login + contagem + leitor)~~ — feito pelo Ualker em 2026-10-13. **Fase 1 concluída.**
2. ~~Consequência de D1 = A: migration 0014, dependency `obter_gestor_central` e script de teste~~ (concluídas em 2026-10-13).
3. ~~Atualizar `backend/README.md`~~ e ~~corrigir `seed_produtos.py`~~ (feitos em 2026-10-13).
4. Iniciar a Fase 2: rotas `/auth/web/login` e `/auth/web/refresh`, models `venda_diaria`/`perda_diaria`, importação por CSV, consulta `GET /vendas`, stub de `sync_vendas_service`.
