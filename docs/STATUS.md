# STATUS — Projeto Bakery (SaaS web + app)

> **Fonte única da verdade sobre o andamento.** Atualizado em: 2026-10-13.
> Precedência em caso de conflito: **este arquivo** > `documento-referencia-saas-bakery.md` > qualquer conversa externa (claude.ai, etc.).
> Toda decisão nova, mudança de escopo ou fase concluída deve ser registrada aqui **na mesma sessão** em que acontece.

---

## 1. Andamento das fases

Roteiro completo, com tarefas e critérios de aceite: `documento-referencia-saas-bakery.md`, seção 8.

| Fase | Situação | Observações |
|---|---|---|
| 1 — Fundação de dados | **Implementada; verificação pendente** | Migrations 0007–0013, models e seeds existem. Ver pendências abaixo. |
| 2 — Ingestão de vendas e perdas | Não iniciada | D1 decidida (opção A). Começa depois de concluída a Fase 1 e a migration 0014. |
| 3 — Motor de previsão | Não iniciada | |
| 4 — Necessidade e produção | Não iniciada | |
| 5 — Distribuição | Não iniciada | |
| 6 — Frontend do SaaS (`frontend-saas/`) | Não iniciada | Pasta ainda não existe |
| 7 — Validação com dado real | Não iniciada | Depende de cliente piloto (D3) |
| 8 — Refino V1.5 | Não iniciada | |

### Fase 1 — o que existe no código (lido em 2026-10-13)

- Migrations: `0007_central_producao`, `0008_loja_central_producao_id`, `0009_usuario_tipo_e_central`, `0010_produto_campos_producao`, `0011_produto_loja_ativo`, `0012_calendario_producao`, `0013_evento_e_associacoes`.
- Models: `CentralProducao`, `CalendarioProducao` (+ `DiaSemana`), `Evento`, `EventoLoja`, `EventoProduto` (+ `EscopoLoja`, `EscopoProduto`, `TipoAjuste`). Campos novos em `Produto`, `ProdutoLoja.ativo`, `Usuario.tipo_usuario`/`central_producao_id`, `Loja.central_producao_id` (obrigatório).
- Check constraint no banco: `ck_usuario_tipo_vs_loja_central` (operador_loja ⇒ loja_id preenchido e central nula; gestor_central ⇒ central preenchida e loja nula).
- Não há mais `estoque_minimo`/`estoque_maximo` em `produtos_lojas`, e nenhum código da API ou dos serviços os referencia.
- `UsuarioAutenticado.loja_id` já é `Optional[int]`.
- `scripts/test_constraint_usuario.py` existe (4 casos: 2 inválidos, 2 válidos).

### Fase 1 — verificação pendente (rodar e registrar o resultado aqui)

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
- [ ] app mobile continua funcionando (login + contagem)
- [ ] seed + health check ok

### Fase 1 — pendências identificadas (fora da verificação)

1. **`seed_dev.py` não atende o critério de aceite original.** Cria 1 central e **1** loja (o critério pedia 2 ou mais lojas) e só um usuário `operador_loja`. Falta também um usuário `gestor_central`, necessário para testar qualquer endpoint do SaaS.
2. **`backend/README.md` está desatualizado:** lista migrations só até a 0006 e não cita os models novos.
3. **Resíduos de teste no banco de desenvolvimento (resolvido em 2026-10-13):** havia dois negócios de teste sobrando (`_Teste Constraint`, id 3, de uma versão antiga do script; e `_Teste Constraint 16588216`, id 6, da execução que quebrou), com suas centrais, lojas e usuários. Nenhuma outra tabela apontava para eles. Foram apagados pela limpeza inicial do script corrigido. Os negócios 1 (`Rede Padaria Teste`) e 2 (`Pais e Filhos`) foram mantidos.

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
| Login do gestor (§3.1) | gestor com escopo de central | `obter_usuario_autenticado` exige `tem_acesso_app`, não devolve `tipo_usuario` nem `central_producao_id` (ver D1) |

---

## 3. Decisões em aberto

| ID | Decisão | Opções | Recomendação | Status |
|---|---|---|---|---|
| D1 | Como o gestor de central autentica no SaaS web | **A)** nova flag `tem_acesso_web` no usuário (migration 0014) + dependency `obter_gestor_central` que valida `tipo_usuario` e `central_producao_id` no banco. **B)** reaproveitar `tem_acesso_app`. | A: separa as duas portas de entrada; em B o gestor ganharia acesso ao app mobile só para conseguir logar. | **Decidida em 2026-10-13: opção A.** |
| D2 | Isolamento: schema/banco por cliente (doc §6) vs. `negocio_id` em tabelas compartilhadas (código atual) | A) manter tabelas compartilhadas; B) migrar para schema por cliente | Não recomendado de forma conclusiva ainda: o doc diz "recomendado", não "decidido". Trocar depois de ter clientes reais é caro, então decidir **antes do primeiro cliente real**. Enquanto isso, toda query nova **deve** filtrar por `negocio_id` vindo do token. | Aberta. Não bloqueia as Fases 2–4. |
| D3 | Cliente piloto e acesso aos dados de venda (PDV) | — | Definir cedo: a Fase 7 depende disso. Alternativa de baixo custo: usar os dados do MVP de loja única (planilha) para testar a Fase 3. | Não definido. |

---

## 4. Log de decisões

- **2026-10-06** — Roteiro de 8 fases e documento de referência criados (conversa de planejamento no claude.ai).
- **2026-10-13** — O desenvolvimento passa a ser feito **somente com o Claude** (sem GitHub Copilot). O executor principal é o Claude Code no VS Code, no repositório.
- **2026-10-13** — `docs/` e `CLAUDE.md` no repositório passam a ser a fonte única da verdade. Conversas no claude.ai servem para planejamento solto; o que virar decisão é gravado aqui.
- **2026-10-13** — **D1 decidida: opção A.** O gestor de central entra no SaaS web por uma flag nova `tem_acesso_web` no usuário, separada de `tem_acesso_app` (migration 0014). A autorização no SaaS fica na dependency `obter_gestor_central`, que exige `status = ativo`, `tem_acesso_web = True` e `tipo_usuario = gestor_central`.

(Decisões anteriores já fechadas: ver `documento-referencia-saas-bakery.md`, seção 10.)

---

## 5. Próximo passo

1. Concluir a verificação da Fase 1 (seção 1) e corrigir `seed_dev.py` (2+ lojas, 1 `operador_loja` por loja e 1 `gestor_central` com `tem_acesso_web=True`).
2. Implementar a consequência de D1 = A: migration 0014 (`tem_acesso_web`), dependency `obter_gestor_central` e script de teste.
3. Atualizar `backend/README.md`.
4. Iniciar a Fase 2: rotas `/auth/web/login` e `/auth/web/refresh`, models `venda_diaria`/`perda_diaria`, importação por CSV, consulta `GET /vendas`, stub de `sync_vendas_service`.
