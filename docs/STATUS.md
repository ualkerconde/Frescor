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
| 2 — Ingestão de vendas e perdas | **Em andamento** (plano aprovado em 2026-10-13) | P1–P6 feitos; **critério de aceite atendido** no P6 (importar CSV e consultar). Faltam P7 (stub do sync) e P8 (seed de vendas + README). |
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

### Fase 2 — plano (aprovado em 2026-10-13)

Objetivo (doc §8): ter dado de venda e perda fluindo antes da API do PDV. Critério de aceite: importar um CSV de vendas e consultá-lo em `GET /vendas?loja_id=&produto_id=&data_inicio=&data_fim=`. Decisões aplicadas: D5–D11 (seção 3).

| Passo | O que | Verificação | Situação |
|---|---|---|---|
| P1 | Rotas `/auth/web/login` e `/auth/web/refresh` (router próprio, regras da `obter_gestor_central` compartilhadas); claim `porta: web` nos tokens do SaaS; dependency do app recusa tokens `porta: web` e quem não é `operador_loja` (D10) | Script com `TestClient`: login/refresh do gestor, 401/403 por motivo, token de uma porta recusado na outra; regressão completa do app (login, `/produtos`, `/zeragem`); `test_obter_gestor_central` | **Concluído (2026-10-13)** — ver abaixo |
| P2 | Migration 0015: `vendas_diarias` e `perdas_diarias` (`negocio_id`, `loja_id`, `produto_id`, `data`, `quantidade` na unidade do produto, `origem`, `criado_em`; perda já com `inferida`); chave única para D5; `lojas.codigo` opcional (D7) | upgrade → downgrade → upgrade; script de chave única e FKs; regressão do app | **Concluído (2026-10-13)** — ver abaixo |
| P3 | Escopo do gestor: lojas da própria central (D8); `loja_id` como filtro validado contra o escopo (fora → 404) | Script: loja da central, de outra central do mesmo negócio, de outro negócio | **Concluído (2026-10-13)** — ver abaixo |
| P4 | Serviço de importação CSV (`;`, vírgula decimal, `dd/mm/aaaa`, produto por `codigo`, loja por `codigo`), tudo ou nada (D9), substitui na reimportação (D5) | Script com CSVs sintéticos: válido, data inválida, produto desconhecido, loja fora do escopo, quantidade negativa, linha duplicada, reimportação | **Concluído (2026-10-13)** — ver abaixo |
| P5 | `POST /vendas/importar` e `POST /perdas/importar` | `TestClient`: 401/403, importação válida, relatório de erros | **Concluído (2026-10-13)** — ver abaixo |
| P6 | `GET /vendas` e `GET /perdas` (filtros, período máximo, paginação) | `TestClient`: filtros, escopo, isolamento entre negócios — fecha o critério de aceite | **Concluído (2026-10-13)** — ver abaixo; **critério de aceite da Fase 2 atendido** |
| P7 | Stub `sync_vendas_service` ("integração não configurada"), fora do agendador | Chamada direta; agendador não o registra | — |
| P8 | `seed_vendas.py` (~8 semanas, 2 lojas) para a Fase 3; README e STATUS | Seed 2× sem duplicar; `GET /vendas` devolve o período | — |

Frontend do SaaS (`frontend-saas/`): começa depois do P6.

**P1 — resultado (2026-10-13):**
- Código: `app/api/auth_web.py` (novo; `POST /auth/web/login` e `POST /auth/web/refresh`, registrado em `main.py` com prefixo `/auth/web`); `app/core/security.py` (parâmetro opcional `porta` em `criar_access_token`/`criar_refresh_token`; tokens do app continuam sem a claim); `app/core/dependencies.py` (`carregar_usuario_do_token` pública, com tipo e porta esperados; `validar_gestor_central` extraída e usada pela dependency e pelas rotas web; dependency do app recusa tokens `porta: web` com 401 e não-operadores com 403); `requirements-dev.txt` (novo, `httpx==0.27.2`). `/auth/login` do app não foi alterado; `/auth/refresh` do app só ganhou a recusa de tokens `porta: web` (ver abaixo).
- `scripts/test_auth_web.py` (novo, `TestClient`): 38 verificações, 3 execuções seguidas, exit 0, banco limpo. Cobre login web (200, claim `porta: web`, token aceito pela dependency), 401 para senha errada/e-mail inexistente, os 5 motivos de 403, refresh válido, access usado como refresh (401), refresh do app na rota web (401), token web no app e token do app no SaaS (401), revogação de `tem_acesso_web` depois do login (refresh e access antigos → 403). **Regressão completa do app:** login, `/produtos` (11 itens), `/produtos/buscar`, `/auth/refresh`, sem token (403, como antes), token inválido (401), gestor no login do app (403) e o fluxo contagem → `/zeragem` → contagem zerada → snapshot gravado → segunda zeragem 409, numa **loja de teste** (as contagens do seed não são tocadas).
- `test_obter_gestor_central.py` atualizado para tokens `porta: web` + caso 9 (token do app → 401): 11/11. `test_constraint_usuario.py` 4/4. Health check e `POST /auth/web/login` do `gestor@teste.com` pelo uvicorn: 200.
- Checagem de mutação: sem a regra "app só para operador" falham A9b e A9c; sem a checagem de porta nas dependencies falham W11, W13 e W14; sem a checagem de porta no `/auth/refresh` do app falha W15.
- **Correção de uma afirmação do plano:** sem a D10, um gestor com `tem_acesso_app` **não** quebrava o app com erro 500: recebia `200` com lista vazia em `/produtos` e `404` em `/zeragem`. O risco era comportamento errado e silencioso.
- **Brecha corrigida (2026-10-13):** a rota `/auth/refresh` do app aceitava um refresh token web (de um gestor com `tem_acesso_app` ligado) e emitia um access token do app, que depois era recusado (403). Agora ela recusa com 401 qualquer refresh token com a claim `porta` — **única mudança feita nas rotas do app**, aprovada pelo Ualker. Caso W15 do `test_auth_web.py` exige o 401; com a checagem removida (mutação), o W15 falha. Regressão completa do app de novo: 38/38.

**P2 — resultado (2026-10-13):**
- Migration `0015_vendas_e_perdas_diarias`: tabelas `vendas_diarias` e `perdas_diarias` (`negocio_id`, `loja_id`, `produto_id`, `data`, `quantidade` Numeric(12,3), `origem`, `criado_em`, `atualizado_em`); chave única `(loja_id, produto_id, data, origem)`; check `quantidade >= 0`; índices em `negocio_id` e `produto_id` (a chave única cobre loja + produto + data); enums `origemvenda` (api, manual) e `origemperda` (api, manual, inferida); coluna `lojas.codigo` (String(32), opcional) com única `(negocio_id, codigo)`. **FKs compostas** `(negocio_id, loja_id) → lojas(negocio_id, id)` e `(negocio_id, produto_id) → produtos(negocio_id, id)` nas duas tabelas (pedido do Ualker: garantia de negócio no banco), com as únicas-alvo `uq_loja_negocio_id` e `uq_produto_negocio_id` criadas na própria 0015. Antes, conferido que os dados existentes não violavam nada (vendas/perdas vazias; `id` já é único).
- Models `VendaDiaria`/`OrigemVenda` e `PerdaDiaria`/`OrigemPerda`, registrados em `app/models/__init__.py`; `Loja.codigo`.
- upgrade 0014→0015 → downgrade 0015→0014 (tabelas, enums e coluna removidos) → upgrade, todos exit 0.
- `scripts/test_vendas_perdas_modelo.py` (novo): 20 casos, 2 execuções, exit 0, banco limpo. Cada erro confere o nome da constraint. Inclui o mecanismo do D5 (`INSERT ... ON CONFLICT DO UPDATE` substitui 10 → 15, 1 linha), origens diferentes coexistindo e venda/perda com loja ou produto de **outro negócio** barradas pelas FKs compostas (X1–X4).
- `seed_dev.py`: preenche `lojas.codigo` (`001` Loja Centro, `002` Loja Bairro) só se estiver vazio; 2 execuções sem duplicar.
- Regressão: `test_auth_web.py` 38/38 (inclui a regressão completa do app), `test_obter_gestor_central.py` 11/11, `test_constraint_usuario.py` 4/4.
- **Para o P4:** o banco arredonda quantidades com mais de 3 casas (1,2345 → 1,235) sem erro; o serviço de importação deve recusar esses valores em vez de deixar o banco arredondar. A coerência entre o `negocio_id` da venda e o da loja/produto é garantida no banco (FKs compostas), mas o serviço também valida, para dar mensagem de erro clara.

**P3 — resultado (2026-10-13):**
- `app/services/escopo_service.py` (novo): `consulta_lojas_do_gestor`, `ids_lojas_do_gestor` e `buscar_loja_no_escopo`. Filtra por `negocio_id` **e** `central_producao_id`, ambos de `GestorCentralAutenticado` (nunca da requisição). Não conhece HTTP: devolve a loja ou `None`.
- `app/api/escopo.py` (novo): `loja_no_escopo_ou_404`, para as rotas do P5/P6. Loja inexistente, de outra central ou de outro negócio recebem a **mesma** resposta (`404 "Loja não encontrada."`), sem revelar se a loja existe.
- `scripts/test_escopo_gestor.py` (novo): 13 casos, 2 execuções, exit 0, banco limpo. Serviço (S1–S7, incluindo o gestor do seed → lojas `001` e `002`) e HTTP por rotas que só existem no processo de teste (H1–H6, incluindo as três respostas 404 idênticas).
- Mutação: sem o filtro de central, 5 casos falham. Sem o filtro de negócio, nenhum falha — esperado: a central pertence a um só negócio e `validar_gestor_central` já garante que é o do gestor; o filtro é defesa em profundidade (regra de ouro), sem efeito observável com dados válidos.
- Regressão: `test_auth_web.py` 38/38, `test_vendas_perdas_modelo.py` 20/20, `test_obter_gestor_central.py` 11/11, `test_constraint_usuario.py` 4/4.
- **Lojas inativas estão no escopo** (permite consultar histórico). A importação para loja inativa é recusada pelo serviço de importação (D12).

**P4 — resultado (2026-10-13):**
- `app/services/importacao_service.py` (novo): `importar_csv(db, gestor, conteudo, tipo)` → `ResultadoImportacao` (sucesso, linhas lidas, inseridas, substituídas, erros por linha, codificação). Sem endpoint (P5). Aplica D5 (substitui, via `ON CONFLICT DO UPDATE`), D6 (unidade do produto, até 3 casas, não negativa), D7 (cabeçalho `data;codigo_loja;codigo_produto;quantidade`, `;`, vírgula decimal, `dd/mm/aaaa`), D8 (só lojas da central), D9 (tudo ou nada, todos os erros relatados de uma vez, vários problemas da mesma linha juntos), D12 (loja inativa recusada), D13 (fração em UN e data futura recusadas; produto inativo aceito; produto não habilitado/desabilitado na loja aceito com **aviso**, numa lista `avisos` separada dos erros, devolvida também quando o arquivo tem erros). Coerência de negócio com mensagem clara (loja e produto procurados só no negócio do gestor). Origem sempre `manual`. Codificação: UTF-8 (com ou sem BOM) e, se não for UTF-8 válido, Windows-1252.
- Escolhas conservadoras **não cobertas por decisão** (revisáveis): quantidade com ponto (`1.234`) é recusada (ambíguo entre milhar e decimal); loja + produto + data repetidos no mesmo arquivo é erro (sem isso o PostgreSQL derruba o `ON CONFLICT` com erro 500 — visto na mutação); linhas totalmente vazias são ignoradas; limite de 100.000 linhas por arquivo; no máximo 200 erros listados (o resto é contado).
- **Defeito achado pelo próprio teste e corrigido:** um arquivo com bytes que não existem no Windows-1252 (ex.: `0x81`) derrubava o serviço com `UnicodeDecodeError`. Agora vira erro "não é um CSV de texto"; arquivo com byte nulo também.
- `scripts/test_importacao_csv.py` (novo): 37 verificações, 2 execuções, exit 0, banco limpo. Sucessos: CSV válido, valor KG (`1,25` → `1.250`), reimportação substitui (12 → 20, sem linha nova), perdas na tabela certa, Windows-1252 com acento (`PÃO-01`), UTF-8 com BOM, linhas em branco no fim, cabeçalho em maiúsculas/com espaços, quantidade zero e 3 casas. Erros (cada um confere linha, mensagem e que nada foi gravado): data em formato errado e inexistente, produto desconhecido, loja de outra central, loja de outro negócio, produto de outro negócio, loja inativa, negativa, mais de 3 casas, com ponto, vazia, linha duplicada, código ambíguo, número de colunas, arquivo vazio, só espaços, cabeçalho errado, separador vírgula, só cabeçalho, tudo ou nada (2 válidas + 1 inválida → nenhuma gravada), vários erros de uma vez, vários problemas na mesma linha, arquivo binário, bytes inválidos.
- Mutação: sem o tudo ou nada falham 18 verificações; aceitando loja inativa, mais de 3 casas ou linha duplicada falha o caso correspondente.
- Regressão: `test_escopo_gestor` 13/13, `test_vendas_perdas_modelo` 20/20, `test_auth_web` 38/38, `test_obter_gestor_central` 11/11, `test_constraint_usuario` 4/4.
- **D13 + migration 0016:** `0016_produto_codigo_unico` cria a única `uq_produto_negocio_codigo (negocio_id, codigo)` em `produtos` (NULL continua permitido). Antes de criar, procura códigos repetidos e, se houver, para com uma mensagem que lista cada um. Verificado: dev sem repetidos; ciclo upgrade → downgrade → upgrade ok; **teste da trava:** com dois produtos `DUP-X` num negócio de teste, o upgrade parou com `RuntimeError ... negocio_id=107 codigo='DUP-X' (2 produtos)` e o banco ficou na 0015; dados de teste apagados e upgrade refeito. **Antes do deploy, conferir o banco de produção** (`SELECT negocio_id, codigo, count(*) FROM produtos WHERE codigo IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1`). Com a única, a lógica de "código ambíguo" saiu do serviço.
- Testes após a D13: `test_importacao_csv.py` 44 verificações (novos: fração em UN recusada, `2,0` aceito, produto inativo aceito, não habilitado e desabilitado com aviso, data futura recusada, hoje aceito, arquivo com erro traz erros e avisos sem gravar; "hoje" fixado em 13/10/2026 pelo parâmetro `hoje`); `test_vendas_perdas_modelo.py` 23 casos (novos L4–L6: código de produto repetido barrado por `uq_produto_negocio_codigo`, mesmo código em outro negócio e produtos sem código aceitos). 2 execuções cada, exit 0. Mutação dos casos novos: sem a recusa de fração, sem a recusa de data futura e sem os avisos, falham os casos correspondentes. Regressão completa ok.

**P5 — resultado (2026-10-13):**
- `app/api/importacao.py` (novo): `POST /vendas/importar` e `POST /perdas/importar`, routers finos com `obter_gestor_central`, upload multipart (campo `arquivo`), limite de **5 MB** por arquivo (`LIMITE_ARQUIVO_BYTES`) e delegação ao `importacao_service`. Registrado em `main.py`.
- `app/schemas/importacao.py` (novo): `RelatorioImportacaoResponse` (sucesso, linhas lidas, inseridas, substituídas, codificação, erros, erros omitidos, avisos, avisos omitidos) e `MensagemLinha` (linha, mensagem).
- Respostas: **200** importado; **422** arquivo com erros, nada gravado, com o **mesmo relatório** no corpo; **413** arquivo maior que 5 MB; 401/403 da `obter_gestor_central`. Um 422 **sem** o campo `sucesso` é a validação do próprio FastAPI (ex.: campo `arquivo` ausente). As três respostas aparecem no OpenAPI (`/docs`).
- **Limite de tamanho — limitação conhecida:** o Starlette recebe e guarda o upload inteiro antes da rota rodar, então o limite impede o processamento, não o recebimento (nem a autenticação vem antes do recebimento). Proteção real contra uploads enormes: limite de corpo no servidor da frente (ex.: `client_max_body_size` no nginx) quando houver deploy.
- **Defeito achado e corrigido no serviço:** um campo com mais de 128 KB (limite do módulo `csv` do Python) gerava a mensagem em inglês `field larger than field limit (131072)` para o usuário. Agora a mensagem é em português, com o detalhe técnico entre parênteses (caso E25 no `test_importacao_csv.py`, 45 verificações).
- `scripts/test_importacao_rotas.py` (novo): 14 verificações por HTTP, 2 execuções, exit 0, banco limpo: sem token (401), token do app (401), gestor sem `tem_acesso_web` (403), nada gravado nesses casos; importação válida (200, relatório), reimportação (substituídas), perdas na tabela certa, produto não habilitado (200 com aviso), arquivo com erros (422 com erros nas linhas 3 e 4, nada gravado), gestor de outra central (422), arquivo acima do limite (413, nada gravado), exatamente no limite (processado, não 413), sem o campo `arquivo` (422 do FastAPI), `/perdas/importar` sem token (401).
- Mutação: sem o limite de tamanho falha R10; respondendo sempre 200 falham R8, R9 e R11.
- Servidor real (uvicorn): health 200; `POST /auth/web/login` do `gestor@teste.com` e `POST /vendas/importar` com arquivo com erro → 422 com o relatório; nenhuma venda/perda gravada nos dados do seed.
- Regressão completa: `test_importacao_csv` 45, `test_vendas_perdas_modelo` 23, `test_escopo_gestor` 13, `test_auth_web` 38, `test_obter_gestor_central` 11, `test_constraint_usuario` 4 — todos passaram.

**P6 — resultado (2026-10-13):**
- `app/services/consulta_service.py` (novo): `consultar(...)` → (total, itens da página). Filtra por `negocio_id` **e** pelas lojas da central do gestor (D8), período, loja e produto opcionais. `validar_periodo`: `data_inicio > data_fim` ou período acima de **366 dias** (contando o primeiro e o último dia) → `PeriodoInvalido`. Ordenação estável por data, loja, produto, origem e id (a origem e o id desempatam venda `manual` e `api` do mesmo dia).
- `app/api/consultas.py` (novo): `GET /vendas` e `GET /perdas` com `obter_gestor_central`. `loja_id` validado pelo `loja_no_escopo_ou_404` do P3 (404 idêntico para loja inexistente, de outra central ou de outro negócio). Período inválido → 422 com mensagem. Parâmetros: `data_inicio` e `data_fim` obrigatórios em **AAAA-MM-DD** (padrão de API; o `dd/mm/aaaa` é só do CSV), `loja_id`, `produto_id`, `limit` (1 a 1000, padrão 100), `offset` (padrão 0). Registrado em `main.py`.
- `app/schemas/consulta.py` (novo): resposta `{total, limit, offset, itens}`; cada item com `data`, `loja {id, codigo}`, `produto {id, codigo, nome}`, `quantidade` (texto decimal, ex.: `"1.250"`, como o `estoque_atual_calculado` do app), `unidade` e `origem`.
- Escolha registrada: `produto_id` de outro negócio devolve lista vazia (200), não 404 — o filtro de negócio já impede o vazamento.
- `scripts/test_consulta_rotas.py` (novo): 33 verificações, 2 execuções, exit 0, banco limpo. Autenticação (sem token 401, token do app 401, sem `tem_acesso_web` 403, `/perdas` sem token 401); filtros (sem filtros só lojas da central, loja, produto, loja + produto, período inclusive, produto de outro negócio vazio); formato do item; origem `api` junto com a `manual` do mesmo dia; ordenação; paginação de 3 em 3 reconstrói a lista sem repetir nem pular, total constante, última página parcial; `limit` 1000 aceito, 1001 e 0 → 422; período invertido e de 367 dias → 422 com mensagem, 366 dias → 200, sem `data_inicio` e data em `dd/mm/aaaa` → 422; loja de outra central, de outro negócio e inexistente → 404 com respostas idênticas; isolamento (gestor de outra central e de outro negócio só veem as próprias lojas; loja de outro negócio → 404); `/perdas` só perdas.
- **Critério de aceite da Fase 2, de ponta a ponta:** importar um CSV pela rota `POST /vendas/importar` (200, 2 inseridas) e consultá-lo em `GET /vendas?loja_id=&produto_id=&data_inicio=&data_fim=` (os 2 dias com as quantidades importadas, origem `manual`).
- Sabotagem: sem o filtro de escopo no serviço, falham F1, O2, O3 e S1 (a loja de outra central aparece); sem o 404 no router, falham E1, E2, E3 e S3 (200 com lista vazia). Sem o filtro de negócio nada falha — esperado, o escopo de central já implica o negócio (defesa em profundidade, como no P3).
- Regressão completa: `test_importacao_rotas` 14, `test_importacao_csv` 45, `test_vendas_perdas_modelo` 23, `test_escopo_gestor` 13, `test_auth_web` 38, `test_obter_gestor_central` 11, `test_constraint_usuario` 4.

---

## 2. Divergências entre o documento de referência e o código

O documento é planejamento. Onde o código diverge, **vale o código** (e este arquivo registra a divergência).

| Tema | Documento | Código real |
|---|---|---|
| Nomes de tabela | singular (`central_producao`, `evento`, `produto_loja`) | `centrais_producao`, `eventos`, `eventos_lojas`, `eventos_produtos`, `produtos_lojas`, `calendario_producao` |
| Eventos | uma entidade `evento` | `eventos` + tabelas de associação `eventos_lojas` e `eventos_produtos` (usadas quando o escopo é "específicas"/"específicos"); `valor_ajuste` é `Numeric(10,4)` |
| Isolamento multi-tenant (§6 e §10) | recomenda schema/banco por cliente | **Decidido (D2, 2026-10-13):** tabelas compartilhadas, com `negocio_id` em todas as tabelas e isolamento via JWT |
| Login do gestor (§3.1) | gestor com escopo de central; não fala em flag de acesso ao SaaS | Campo novo `usuarios.tem_acesso_web` (migration 0014, D1 = A), separado de `tem_acesso_app`. A dependency `obter_gestor_central` exige `tem_acesso_web` e `gestor_central` (passo 5, 2026-10-13); `obter_usuario_autenticado` e `/auth/login` continuam exigindo `tem_acesso_app` (rotas `/auth/web/*` ficam para a Fase 2) |
| Vendas e perdas (§3.6, §3.7) | `venda_diaria`/`perda_diaria`, sem `negocio_id`; campos `quantidade_vendida`/`quantidade_perdida` | `vendas_diarias`/`perdas_diarias` (migration 0015), **com** `negocio_id` (D2); campo `quantidade` Numeric(12,3) na unidade do produto (D6), não negativa; `criado_em`/`atualizado_em`; chave única (loja, produto, data, origem) (D5) |
| Escopo do gestor (§3.1) | "negócio/central inteiro" | **Só as lojas da própria central** (D8) |

---

## 3. Decisões em aberto

| ID | Decisão | Opções | Recomendação | Status |
|---|---|---|---|---|
| D1 | Como o gestor de central autentica no SaaS web | **A)** nova flag `tem_acesso_web` no usuário (migration 0014) + dependency `obter_gestor_central` que valida `tipo_usuario` e `central_producao_id` no banco. **B)** reaproveitar `tem_acesso_app`. | A: separa as duas portas de entrada; em B o gestor ganharia acesso ao app mobile só para conseguir logar. | **Decidida em 2026-10-13: opção A.** |
| D2 | Isolamento: schema/banco por cliente (doc §6) vs. `negocio_id` em tabelas compartilhadas (código atual) | A) manter tabelas compartilhadas; B) migrar para schema por cliente | Trocar depois de ter clientes reais é caro. Toda query nova **deve** filtrar por `negocio_id` vindo do usuário autenticado. | **Decidida em 2026-10-13: opção A** (tabelas compartilhadas, `negocio_id` em todas as tabelas). |
| D3 | Cliente piloto e acesso aos dados de venda (PDV) | — | Definir cedo: a Fase 7 depende disso. Alternativa de baixo custo: usar os dados do MVP de loja única (planilha) para testar a Fase 3. Quando definido, pode alterar o formato do CSV (D7). | **Aberta.** Trava a implementação real do `sync_vendas_service` (P7 fica em stub). |
| D4 | Central de produção inativa (`centrais_producao.ativa = false`) bloqueia o acesso do gestor ao SaaS? | **A)** sim: `obter_gestor_central` responde 403. **B)** não: o gestor entra e só vê a central como inativa (ex.: para consultar histórico). | Sem recomendação: depende de como o cliente usa a desativação de central. | **Decidida em 2026-10-13: opção A** (central inativa bloqueia o gestor, 403). Implementada em `obter_gestor_central`. |
| D5 | Reimportação de loja + produto + data + origem já existentes | A) substituir; B) somar; C) recusar | A: permite corrigir reenviando o arquivo | **Decidida em 2026-10-13: A (substituir).** |
| D6 | Unidade da quantidade vendida/perdida | — | Unidade do produto (UN → peças, KG → kg), coerente com `estoque_atual_calculado` | **Decidida em 2026-10-13: unidade do produto.** |
| D7 | Formato do CSV de importação | — | `;` como separador, vírgula decimal, data `dd/mm/aaaa`, produto pelo `codigo` interno, loja por `lojas.codigo` (campo novo, opcional) | **Aprovada em 2026-10-13 como provisória**; pode mudar quando D3 for definida. |
| D8 | Escopo do gestor de central | A) lojas da própria central; B) todas as lojas do negócio | A: menor privilégio; bate com "cada central roda seu ciclo" | **Decidida em 2026-10-13: A.** |
| D9 | Arquivo com linhas inválidas | A) tudo ou nada, com relatório de erros; B) importa as válidas | A | **Decidida em 2026-10-13: A (tudo ou nada).** |
| D10 | Separar tokens do app e do SaaS | — | Claim `porta: web` nos tokens do SaaS, exigida pela `obter_gestor_central`; a dependency do app recusa tokens `porta: web` e usuários que não são `operador_loja` (fecha o risco de gestor com `tem_acesso_app` cair em endpoints que assumem `loja_id`) | **Decidida em 2026-10-13: sim.** |
| D11 | Como testar rotas por HTTP | A) `httpx` em `requirements-dev.txt` + `TestClient`; B) subir uvicorn nos scripts | A | **Decidida em 2026-10-13: A.** |
| D12 | Importar vendas/perdas para uma loja **inativa** da central | A) recusar (erro na linha do CSV); B) aceitar | — | **Decidida em 2026-10-13: A (recusar).** Erro na linha; pela D9 (tudo ou nada) o arquivo inteiro não grava. Para carregar histórico de uma loja desativada, reativar a loja temporariamente, importar e desativar de novo. |
| D13 | Regras de conteúdo do CSV: (a) fração em produto UN; (b) produto inativo; (c) produto não habilitado na loja; (d) data futura | — | — | **Decidida em 2026-10-13:** (a) **recusar** (erro na linha; `2,0` vale); (b) **aceitar**; (c) **aceitar com AVISO** (lista separada de avisos no relatório, sem erro e sem bloquear o arquivo; vale também para produto habilitado mas desabilitado na loja, `ativo = false`); (d) **recusar** (hoje é aceito). Junto: única `(negocio_id, codigo)` em `produtos` (migration 0016). |

---

## 4. Log de decisões

- **2026-10-06** — Roteiro de 8 fases e documento de referência criados (conversa de planejamento no claude.ai).
- **2026-10-13** — O desenvolvimento passa a ser feito **somente com o Claude** (sem GitHub Copilot). O executor principal é o Claude Code no VS Code, no repositório.
- **2026-10-13** — `docs/` e `CLAUDE.md` no repositório passam a ser a fonte única da verdade. Conversas no claude.ai servem para planejamento solto; o que virar decisão é gravado aqui.
- **2026-10-13** — **D1 decidida: opção A.** O gestor de central entra no SaaS web por uma flag nova `tem_acesso_web` no usuário, separada de `tem_acesso_app` (migration 0014). A autorização no SaaS fica na dependency `obter_gestor_central`, que exige `status = ativo`, `tem_acesso_web = True` e `tipo_usuario = gestor_central`.
- **2026-10-13** — **D4 decidida: opção A.** Gestor cuja central está inativa (`centrais_producao.ativa = false`) é recusado pela `obter_gestor_central` com 403 e mensagem própria ("A central de produção vinculada ao seu usuário está inativa"). Coberto pelo caso 8 de `test_obter_gestor_central.py`.
- **2026-10-13** — Removido `backend/scripts/_fix_migrations_encoding.py` (script temporário, sem uso, que reescrevia as migrations 0012 e 0013 se executado).
- **2026-10-13** — **Fase 1 concluída.** Último item: teste do app mobile no iPhone (login, contagem e leitor de código de barras, este após correção do `BarcodeScanner`).
- **2026-10-13** — **Plano da Fase 2 aprovado** (passos P1–P8, seção 1). Frontend do SaaS começa depois do P6.
- **2026-10-13** — **D2 decidida:** tabelas compartilhadas com `negocio_id` em todas as tabelas (diverge da recomendação do doc §6/§10, que fica superada).
- **2026-10-13** — **D5:** reimportação substitui o valor. **D6:** quantidade na unidade do produto. **D8:** gestor vê só as lojas da própria central. **D9:** importação tudo ou nada.
- **2026-10-13** — **D7 (provisória):** CSV com `;`, vírgula decimal, `dd/mm/aaaa`, produto por `codigo`, loja por `lojas.codigo` (opcional). Revisar quando D3 for definida.
- **2026-10-13** — **D10:** tokens do SaaS levam a claim `porta: web`; a dependency do app recusa esses tokens e quem não é `operador_loja`. **D11:** `httpx` só em `requirements-dev.txt`, testes de rota com `TestClient`.
- **2026-10-13** — **D12 decidida: A.** Importação para loja inativa é recusada com erro na linha (e, pela D9, o arquivo inteiro não grava). Histórico de loja desativada: reativar temporariamente, importar e desativar.
- **2026-10-13** — **D13 decidida:** fração em produto UN e data futura são recusadas; produto inativo é aceito; produto não habilitado (ou desabilitado) na loja é aceito com aviso. Código de produto passa a ser único no negócio (migration 0016).

(Decisões anteriores já fechadas: ver `documento-referencia-saas-bakery.md`, seção 10.)

---

## 5. Próximo passo

1. ~~Teste do app mobile (login + contagem + leitor)~~ — feito pelo Ualker em 2026-10-13. **Fase 1 concluída.**
2. ~~Consequência de D1 = A: migration 0014, dependency `obter_gestor_central` e script de teste~~ (concluídas em 2026-10-13).
3. ~~Atualizar `backend/README.md`~~ e ~~corrigir `seed_produtos.py`~~ (feitos em 2026-10-13).
4. **Fase 2, P1:** rotas `/auth/web/login` e `/auth/web/refresh` + D10 (ver plano na seção 1). Depois P2–P8 na ordem.
