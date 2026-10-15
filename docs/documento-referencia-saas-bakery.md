# Documento de Referência — SaaS de Produção e Distribuição Centralizada

**Projeto:** Projeto Bakery
**Escopo deste documento:** Web software (SaaS) que opera junto com o app mobile já existente
**Status:** Planejamento — base para início de desenvolvimento

> **Nota de versão:** este é o documento de planejamento original (06/10/2026), mantido sem alterações no corpo. O estado atual do desenvolvimento, as divergências entre este texto e o código, as decisões em aberto e o log de decisões posteriores ficam em [`STATUS.md`](STATUS.md). **Em caso de conflito entre os dois, `STATUS.md` prevalece.**

> **Atualizações posteriores ao planejamento (o corpo abaixo NÃO foi reescrito):**
> - **2026-10-13 — Nome do produto: Frescor.** "Bakery" era provisório. Onde o texto diz "Projeto Bakery", leia Frescor.
> - **2026-10-13 — Escopo ampliado para outros perecíveis.** Além da padaria, o sistema deve atender outros perecíveis, incluindo **itens não produzidos** (só distribuídos/revendidos) e **itens produzidos para açougue e hortifruti**. O texto abaixo foi escrito pensando em padaria; os pontos do modelo de dados e das fases que isso pode afetar estão listados em `STATUS.md` (decisão D14). Nada foi implementado ainda.
> - **2026-10-15 — D14 decidida** (detalhes em `STATUS.md`): cada central de produção atende **uma seção só** (padaria, açougue, hortifruti são centrais separadas, com a mesma lógica), registrada na central; o produto tem **tipo de abastecimento** `produzido` (ordem de produção → distribuição) ou `distribuído` (a central só distribui), os dois com previsão — substitui a ideia de `tem_producao_propria` e o "sai direto do estoque central" da §4.5; **cada loja continua com uma central** (loja atendida por várias centrais é trabalho futuro); primeiro cliente só padaria.

---

## 1. Contexto e objetivo de negócio

O produto é vendido como **uma solução única** — app + SaaS — para redes de supermercado que operam padaria própria em cada loja (ex: perfil Pão de Açúcar, BH). Não são dois produtos separados: são duas portas de entrada para o mesmo sistema multi-tenant.

**App (já concluído):** usado pelas lojas para contagem de estoque (inventário).

**SaaS (objeto deste documento):** usado pela produção/distribuição centralizada da rede. Compila a demanda de todas as lojas, decide o que produzir, e organiza a distribuição para cada loja.

**Objetivo central do SaaS:** usar inventário por loja, parâmetros de estoque, e dados de venda para gerar automaticamente a necessidade de reposição de cada produto em cada loja — e a partir disso, gerar ordens de produção centralizadas e planos de distribuição — reduzindo ruptura (falta) e perda (sobra/validade vencida), aumentando venda e otimizando resultado.

**Modelo comercial:** SaaS comercial multi-tenant de verdade — múltiplos clientes pagantes (redes de supermercado diferentes), cada um com ambiente de dados isolado, rodando na mesma base de código. Escala esperada: poucos clientes grandes (algumas dezenas), não milhares de clientes pequenos.

---

## 2. O que já existe (base herdada do app)

O backend (`FastAPI + PostgreSQL`) e o frontend do app (`React + Vite PWA`) já estão implementados e validados em produção. Peças 100% reaproveitáveis:

| Peça já existente | Onde está | Reaproveitamento no SaaS |
|---|---|---|
| Isolamento multiempresa via JWT (`negocio_id`/`loja_id` nunca vêm de parâmetro, sempre do token) | `app/core/dependencies.py` | Mesma regra de segurança se aplica ao SaaS — é o alicerce do multi-tenant |
| Auth JWT (access 1h + refresh 30 dias) | `app/api/auth.py`, `app/core/security.py` | Reaproveitado integralmente, só muda o perfil de quem loga |
| Modelo de estoque de campo duplo (`quantidade_inventariada` rascunho vs `estoque_atual_calculado` real) | `models/estoque_atual.py` | É a fonte do "estoque atual" usado no cálculo de necessidade |
| Zeragem diária com snapshot preservado (`historico_contagens`) | `services/zeragem_service.py` | Fonte de histórico de estoque ao longo do tempo |
| Classificação multi-nível (até 4 níveis por negócio) | `models/nivel_classificacao.py`, `produto_classificacao.py` | Reaproveitado — já pensado para ser gerenciado pelo software web |
| Hierarquia `negocio → lojas → usuarios/produtos` | `models/negocio.py`, `loja.py` | Base da hierarquia, precisa ser estendida (ver seção 3) |

**MVP validado (single-store, sem distribuição):** já provou na prática conceitos-chave deste documento — estoque mínimo/máximo calculado (não digitado), calendário de produção por dia da semana, dias de validade como campo do produto, e a necessidade de uma tela de "perdas potenciais". Esse MVP não deve ser usado como base de código (feito para validação, não produção), mas suas decisões de modelagem foram incorporadas aqui.

---

## 3. Modelo de dados completo

### 3.1 Hierarquia multi-tenant estendida

```
negocio (tenant / cliente pagante)
  └─ central_producao (1 ou mais por negócio)
        └─ loja (N lojas, cada uma vinculada a exatamente 1 central)
              └─ usuario (operador de loja, escopo = 1 loja)
  └─ usuario (gestor da central, escopo = negócio/central inteiro — não tem loja fixa)
  └─ produto (catálogo do negócio, gerenciado pelo SaaS)
        └─ produto_loja (habilitação + parâmetros por loja)
```

**Alteração necessária em `loja.py`:** adicionar `central_producao_id` (FK).

**Alteração necessária em `usuario.py`:** hoje cada usuário pertence a **uma loja fixa** (modelo do app). O SaaS introduz um segundo perfil — o gestor da central, que não tem loja fixa, e sim escopo sobre o negócio/central inteiro. Sugestão de campo: `tipo_usuario` (`operador_loja` | `gestor_central`), com `loja_id` opcional (nulo para gestor central) e `central_producao_id` opcional (preenchido para gestor central).

### 3.2 Nova entidade: `central_producao`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| negocio_id | FK | |
| nome | string | |
| ativa | bool | |

### 3.3 Alterações em `produto`

| Campo novo | Tipo | Propósito |
|---|---|---|
| tem_producao_propria | bool | Diferencia item produzido na central (passa por ordem de produção) de item só distribuído (sai direto do estoque central) |
| dias_validade | int | Trava de segurança contra overprodução — usado para checar se a cobertura necessária excede a validade |
| margem_maxima_percentual | decimal | Único parâmetro manual de "apetite de risco" — substitui a antiga ideia de estoque_máximo fixo |
| data_inicio_vigencia | date, opcional | Nulo = produto permanente. Preenchido = produto sazonal (repete anualmente) ou descontinuado |
| data_fim_vigencia | date, opcional | Se repete todo ano (mesma data, ano após ano) = sazonal. Se não repete = descontinuado a partir dessa data |
| ciclo_previsao | enum | `semanal` (baseline = últimas semanas) ou `sazonal` (baseline = mesmo período do ano anterior) |

> **Observação de modelagem:** vigência sazonal e descontinuação **não são tratadas como exceção no código** — ambas usam o mesmo par de campos de vigência, e o motor de cálculo simplesmente filtra "este produto está vigente hoje?" antes de considerar qualquer item, seja ele permanente, sazonal ou descontinuado.

### 3.4 Alterações em `produto_loja` (relação já existente)

| Campo | Tipo | Observação |
|---|---|---|
| ativo | bool | Liga/desliga o produto **por loja individualmente**, sem afetar as demais lojas |
| estoque_minimo | — | **Deixa de ser armazenado como config fixa.** Passa a ser **calculado diariamente** a partir da previsão (ver seção 4) |
| estoque_maximo | — | Idem — calculado como `estoque_mínimo_do_dia × (1 + margem_maxima_percentual)` |

### 3.5 Nova entidade: `calendario_producao`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| produto_id | FK | |
| dia_semana | enum | seg/ter/qua/qui/sex/sab/dom |

Define em quais dias da semana aquele item é produzido. Editável pelo gestor da central. Exemplo: bolo produzido seg/qua/sex.

### 3.6 Nova entidade: `venda_diaria`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| loja_id | FK | |
| produto_id | FK | |
| data | date | |
| quantidade_vendida | decimal | |
| origem | enum | `api` (integração com PDV) ou `manual` (carga temporária enquanto API não existe) |

Alimentada por um job que consulta a API do sistema de PDV/estoque interno da rede (sistema único por rede, confirmado pelo usuário — não há necessidade de múltiplos adaptadores de integração por loja).

### 3.7 Nova entidade: `perda_diaria`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| loja_id | FK | |
| produto_id | FK | |
| data | date | |
| quantidade_perdida | decimal | |
| origem | enum | `api`, `manual`, ou `inferida` (ver seção 4.6) |

Mesma via de integração de `venda_diaria` — provavelmente o mesmo sistema, endpoint/campo diferente (a confirmar na integração real).

### 3.8 Nova entidade: `ordem_producao`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| central_producao_id | FK | |
| data | date | |
| tipo | enum | `programada` (ciclo normal) ou `emergencial` (reativa) |
| status | enum | `gerada`, `em_producao`, `concluida` |

### 3.9 Nova entidade: `ordem_producao_item`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| ordem_producao_id | FK | |
| produto_id | FK | |
| quantidade_planejada | decimal | Soma da necessidade de todas as lojas ativas daquela central |
| quantidade_produzida | decimal, opcional | Preenchido após a produção real — pode divergir do planejado |

### 3.10 Nova entidade: `romaneio`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| central_producao_id | FK | |
| data | date | |
| status | enum | `planejado`, `expedido`, `entregue` |

### 3.11 Nova entidade: `romaneio_item`

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| romaneio_id | FK | |
| loja_id | FK | |
| produto_id | FK | |
| quantidade_sugerida | decimal | Calculada pelo sistema (proporcional à necessidade, quando há escassez) |
| quantidade_final | decimal | Editável pelo gestor — decisão manual sempre que produção real < necessidade total |

---

## 4. Motor de cálculo — regras de negócio detalhadas

### 4.1 Previsão de venda (baseline)

Combina dois horizontes, evitando tanto o ruído de curto prazo quanto a lentidão de reação de uma média longa parada:

**Passo 1 — base sazonal por dia da semana:** média de venda daquele produto naquele dia da semana específico, olhando as últimas 6-8 semanas (ex: média dos últimos 6-8 sábados). **Implementado (D18 e D25, `docs/STATUS.md`): mediana dos últimos 6 sábados**, que não se deixa levar por um dia de pico; no teste no passado, empata com a média em dado limpo e é bem melhor com picos.

**Passo 2 — fator de tendência recente:** razão entre venda real dos últimos 7 dias e o que a base sazonal previa para esses mesmos dias. Captura mudanças recentes (tendência de alta/baixa, efeito de promoção não cadastrada). **Implementado (D19 e D31, `docs/STATUS.md`): mediana das razões diárias real ÷ base dos últimos 7 dias**, limitada a 0,7–1,3 e com no mínimo 5 dias comparáveis (a fórmula abaixo, soma contra soma, era a versão inicial; um pico isolado entrava inteiro nela).

```
fator_tendência = venda_real_últimos_7_dias / venda_esperada_últimos_7_dias (base sazonal)
previsão_dia = média_sazonal_do_dia_da_semana × fator_tendência
```

**Produto de ciclo sazonal (`ciclo_previsao = sazonal`):** a base não vem das últimas semanas (produto sazonal tem venda zero fora da janela — isso não é sazonalidade, é ausência). A base vem do **mesmo período do ano anterior**, se existir histórico de pelo menos uma temporada passada, aplicando o mesmo princípio de fator de tendência.

### 4.2 Cold start (produto novo ou loja nova)

Mecanismo único para os dois casos — transição gradual, sem corte abrupto:

```
previsão = (peso_real × previsão_calculada_com_dado_próprio) + (peso_proxy × estimativa_proxy)
```

- `peso_real` cresce de 0% (primeira semana) até 100% (após 6-8 semanas de histórico próprio)
- **Produto novo:** proxy = estimativa informada pelo gestor no cadastro, ou média de produto similar da mesma categoria
- **Loja nova:** proxy = média da rede (ou de lojas de porte/perfil parecido)
- Durante o cold start, a margem (`margem_maxima_percentual`) deveria ser sugerida mais generosa por padrão — risco de ruptura em lançamento é pior que sobra pontual

### 4.3 Calendário de eventos (datas atípicas)

Nova entidade não detalhada na seção 3 mas necessária — **a ser adicionada**:

```
evento: id, negocio_id, central_producao_id, nome, data_inicio, data_fim,
        escopo_loja (todas as lojas DA CENTRAL / lojas específicas),
        escopo_produto (todos / produtos específicos),
        tipo_ajuste (multiplicador ou valor fixo informado)
```

Cadastrado pelo gestor com antecedência (antes do job noturno rodar). No cálculo diário, o motor primeiro checa se existe evento ativo para aquele produto/loja/data — se sim, substitui ou multiplica a previsão normal.

Regras do ajuste (D26, `docs/STATUS.md`): o valor fixo é a previsão **diária** de cada loja + produto do escopo, substitui a previsão (mesmo sem histórico) e vence qualquer multiplicador; entre valores fixos no mesmo dia, vale o último cadastrado; multiplicadores no mesmo dia se multiplicam. O ajuste é aplicado depois do cold start (§4.2). O evento pertence a uma central (D27): "todas as lojas" = lojas da central do evento.

**Regra crítica:** dias marcados como evento devem ser **excluídos do cálculo da média sazonal normal** dos meses seguintes, para não distorcer a baseline de dias normais.

### 4.4 Cálculo de necessidade (mínimo/máximo dinâmico)

O mínimo não é mais configurado manualmente — é a própria previsão. O máximo é o mínimo mais uma margem de crescimento.

```
estoque_mínimo_do_dia = previsão_ajustada (sazonalidade + tendência + cold start + evento, se houver)
estoque_máximo_do_dia = estoque_mínimo_do_dia × (1 + margem_maxima_percentual)
```

**Janela de cobertura:** não é um número fixo de dias — é a **distância até a próxima data de produção daquele item**, conforme `calendario_producao`. A necessidade soma a previsão de cada dia individual até a próxima produção (não multiplica uma média por N, já que dias diferentes da semana têm previsões diferentes):

```
necessidade_loja_produto = Σ(previsão de cada dia até a próxima produção) 
                            + estoque_segurança 
                            - estoque_atual_calculado
```

respeitando `estoque_mínimo_do_dia` e `estoque_máximo_do_dia`, e considerando apenas lojas com `produto_loja.ativo = true` e produto vigente na data (`data_inicio_vigencia`/`data_fim_vigencia`).

**Alerta de validade:** se a cobertura necessária (dias até a próxima produção) exceder `dias_validade` do produto, o sistema deve sinalizar — sugestão de ajuste no calendário de produção daquele item.

### 4.5 Agregação e ordem de produção

Para produtos com `tem_producao_propria = true`: soma a `necessidade_loja_produto` de todas as lojas ativas vinculadas àquela `central_producao`, gerando `ordem_producao_item.quantidade_planejada`.

Para produtos sem produção própria: necessidade sai direto do estoque central (sem passar por ordem de produção).

**Cada central roda seu próprio ciclo, independente das demais** (cálculo, produção e distribuição em paralelo por central).

### 4.6 Perda inferida (cruzamento de consistência)

Mesmo com venda e perda reais vindas da API, pode haver diferença entre o que a matemática prevê que deveria sobrar e o que o estoque físico mostra. Essa diferença é sinal de algo não capturado pelas APIs oficiais (quebra não registrada, furto, erro de contagem):

```
perda_inferida = estoque_esperado (entrada - venda_api - perda_api) - estoque_real_atual
```

Persistida em `perda_diaria` com `origem = inferida`. Se consistentemente alta, funciona como alerta de anomalia operacional.

### 4.7 Produção emergencial (válvula de segurança)

Além do ciclo diário noturno, uma checagem intradiária leve (algumas vezes ao dia) compara `estoque_atual_calculado × estoque_mínimo_do_dia`. Se cruzar a linha antes da hora, gera `ordem_producao` com `tipo = emergencial`.

**Não é sintoma de previsão ruim** — é rede de segurança para o imprevisível (evento não cadastrado, pico atípico). Deve ser mantida como módulo permanente, mas a **frequência de itens emergenciais é uma métrica de qualidade do motor de previsão** — deve cair conforme o modelo amadurece.

### 4.8 Distribuição com escassez

Quando `quantidade_produzida < quantidade_planejada` (produção real ficou abaixo do calculado), o sistema sugere rateio **proporcional à necessidade de cada loja** como ponto de partida, mas a decisão final é sempre manual do gestor — o sistema não decide sozinho quem recebe menos.

### 4.9 Autoajuste de margem (V1.5 — gestão por exceção)

Para escalar em redes grandes (20+ lojas) sem depender de vigilância manual constante:

1. Sistema mede perda e ruptura recentes por loja/produto
2. Ajusta `margem_maxima_percentual` automaticamente, dentro de limites seguros pré-definidos (ex: nunca fora de 10%-40%)
3. Se o ajuste calculado cabe dentro do limite → aplica sozinho, silenciosamente
4. Se pede para sair do limite seguro → vira alerta de exceção para o gestor (sinal de problema estrutural que o algoritmo não deve resolver sozinho)

Isso reduz o volume de decisão manual à fila curta de exceções genuínas, mesmo com milhares de combinações produto×loja.

---

## 5. Módulo analítico (BI) — sem dado de custo no V1

Por decisão de escopo, o V1 não trabalha com custo/margem financeira — foco em **quantidade e eficiência operacional**:

- **Taxa de perda** = perda / produção
- **Índice de crescimento** = venda do período vs. mesmo período anterior
- **Índice de ruptura** = frequência de zeragem de estoque antes da próxima produção
- **Balanço perda vs. ruptura** — cruzamento que indica se a margem está mal calibrada (não o volume)
- **Ranking comparativo entre lojas** — mesma métrica, lojas diferentes, para achar outliers de execução local

Custo/margem financeira fica para uma fase futura, como camada adicional multiplicando essas mesmas métricas de quantidade — sem precisar redesenhar o módulo.

---

## 6. Isolamento multi-tenant — decisão de infraestrutura

Dado o perfil de "poucos clientes grandes" (não milhares de tenants pequenos), a recomendação é **isolamento por schema (ou banco) por cliente**, em vez do padrão mais comum de tabela compartilhada com `tenant_id`:

- Isolamento estrutural — impossível vazar dado entre clientes por erro de código
- Cada cliente pode ser escalado/otimizado independentemente
- Custo: mais complexidade operacional em migrações (gerenciável, dado o número reduzido de clientes)

Essa é uma decisão de implementação técnica — não muda nada do modelo de dados já desenhado, que já assume isolamento por `negocio` em todas as tabelas.

---

## 7. Estrutura de pastas (monorepo)

```
Projeto Bakery/
├── backend/                    # já existe — recebe os módulos novos
│   └── app/
│       ├── models/
│       │   ├── central_producao.py        # novo
│       │   ├── venda_diaria.py             # novo
│       │   ├── perda_diaria.py             # novo
│       │   ├── calendario_producao.py      # novo
│       │   ├── evento.py                    # novo
│       │   ├── ordem_producao.py           # novo
│       │   ├── ordem_producao_item.py      # novo
│       │   ├── romaneio.py                  # novo
│       │   ├── romaneio_item.py             # novo
│       │   ├── loja.py                       # alterar — + central_producao_id
│       │   ├── usuario.py                    # alterar — + tipo_usuario
│       │   └── produto.py                    # alterar — + campos da seção 3.3
│       └── services/
│           ├── previsao_service.py          # novo
│           ├── necessidade_service.py       # novo
│           ├── producao_service.py          # novo
│           ├── distribuicao_service.py      # novo
│           └── sync_vendas_service.py       # novo
├── frontend/                   # já existe — app da loja (PWA)
├── frontend-saas/              # novo — painel web da central
├── shared/                     # opcional — criar quando a duplicação de código entre os 2 frontends aparecer
└── docs/                       # novo — este documento e futuros registros de decisão
```

---

## 8. Roteiro de construção — fase a fase

### Fase 1 — Fundação de dados

**Objetivo:** preparar o schema para tudo que vem depois, sem lógica de negócio ainda.

**Tarefas:**
- Criar migração Alembic: tabela `central_producao`
- Criar migração: `loja.central_producao_id` (FK)
- Criar migração: `usuario.tipo_usuario`, tornar `loja_id` opcional, adicionar `central_producao_id` opcional
- Criar migração: campos novos em `produto` (seção 3.3)
- Criar migração: `produto_loja.ativo`, remover/migrar `estoque_minimo`/`estoque_maximo` fixos
- Criar migração: `calendario_producao`
- Criar migração: `evento`
- Atualizar seeds (`seed_dev.py`, `seed_produtos.py`) para incluir uma central de produção de teste
- **Critério de aceite:** `alembic upgrade head` roda sem erro; seed cria negócio com 1 central e 2+ lojas vinculadas a ela

### Fase 2 — Ingestão de vendas e perdas

**Objetivo:** ter dado real de venda/perda fluindo, mesmo antes da API do PDV estar disponível.

**Tarefas:**
- Criar modelos `venda_diaria` e `perda_diaria`
- Criar endpoint temporário de carga manual/CSV (`POST /vendas/importar`, `POST /perdas/importar`) para uso enquanto a integração real não existe
- Criar `sync_vendas_service.py` como job stub (interface pronta, implementação real da chamada de API a definir quando a integração do PDV for especificada)
- **Critério de aceite:** é possível importar um CSV de vendas de teste e consultar `GET /vendas?loja_id=&produto_id=&data_inicio=&data_fim=`

### Fase 3 — Motor de previsão

**Objetivo:** `previsao_service` funcionando isoladamente, testável com dado histórico real.

**Tarefas:**
- Implementar cálculo de base sazonal por dia da semana (seção 4.1, passo 1)
- Implementar fator de tendência recente (seção 4.1, passo 2)
- Implementar branch de `ciclo_previsao = sazonal` (baseline = ano anterior)
- Implementar cold start com peso gradual (seção 4.2)
- Implementar checagem de `evento` ativo, sobrepondo a previsão padrão quando aplicável
- Escrever testes unitários com dados sintéticos cobrindo: produto com histórico completo, produto novo, produto sazonal em primeira temporada, produto sazonal com histórico do ano anterior, produto com evento cadastrado
- **Critério de aceite:** dado um produto/loja/data, o serviço retorna uma previsão numérica coerente para cada um dos cenários de teste acima

### Fase 4 — Necessidade e produção

**Objetivo:** primeira decisão de negócio automatizada do sistema.

**Tarefas:**
- Implementar `necessidade_service`: cálculo de `estoque_mínimo_do_dia` e `estoque_máximo_do_dia` (seção 4.4)
- Implementar janela de cobertura dinâmica baseada em `calendario_producao` (distância até a próxima produção)
- Implementar alerta de validade (cobertura necessária vs. `dias_validade`)
- Implementar `producao_service`: agregação de `necessidade_loja_produto` por `central_producao`, geração de `ordem_producao` + `ordem_producao_item`
- Implementar filtro de vigência (produto sazonal/descontinuado) e de `produto_loja.ativo`
- Endpoint: `POST /producao/gerar-ordem-do-dia` (dispara o cálculo do dia para uma central)
- Endpoint: `GET /producao/ordens?central_id=&data=`
- **Critério de aceite:** rodar `gerar-ordem-do-dia` numa central de teste com 2+ lojas produz uma `ordem_producao` com itens agregados corretamente, respeitando produtos inativos/fora de vigência

### Fase 5 — Distribuição

**Objetivo:** transformar a ordem de produção (ou estoque central de produtos sem produção própria) em um plano de entrega por loja.

**Tarefas:**
- Implementar `distribuicao_service`: geração de `romaneio` + `romaneio_item` com `quantidade_sugerida`
- Implementar lógica de rateio proporcional para o cenário de escassez (`quantidade_produzida < quantidade_planejada`), preenchendo `quantidade_sugerida` como ponto de partida editável
- Endpoint: `PATCH /romaneio/{id}/itens/{item_id}` (edição manual de `quantidade_final` pelo gestor)
- Endpoint: `POST /romaneio/{id}/confirmar-expedicao`
- **Critério de aceite:** gerar romaneio a partir de uma ordem de produção com produção parcial (menor que planejado) e confirmar que o rateio proporcional aparece corretamente como sugestão editável

### Fase 6 — Frontend do SaaS

**Objetivo:** painel web funcional cobrindo os módulos das fases 1-5. Construído em paralelo, não depois — cada módulo de backend ganha sua tela assim que sai do forno.

**Telas mínimas:**
- Login (gestor da central)
- Cadastro de central de produção
- Cadastro/edição de produto (com vigência, validade, margem, calendário de produção)
- Ativação/desativação de produto por loja
- Cadastro de eventos
- Visão da ordem de produção do dia (por central)
- Tela de romaneio com edição manual de quantidade
- Importação manual de vendas/perdas (enquanto fase 2 não tem API real)

**Critério de aceite:** um gestor consegue, sem acessar o banco diretamente, cadastrar um produto, ver a ordem de produção gerada, e ajustar/confirmar um romaneio.

### Fase 7 — Validação com dado real

**Objetivo:** reduzir risco antes de confiar no automático.

**Tarefas:**
- Rodar o sistema em paralelo com a decisão manual do gestor por um período definido (sugestão: 4-6 semanas)
- Registrar divergência entre sugestão do sistema e decisão humana em cada ciclo
- Revisar e recalibrar parâmetros do motor de previsão com base nessas divergências
- **Critério de aceite:** divergência entre sugestão e decisão humana estabiliza dentro de uma margem aceitável definida junto com o cliente piloto

### Fase 8 — Camadas de refino (V1.5)

**Objetivo:** só após o núcleo validado com dado real.

**Tarefas:**
- Implementar loop de autoajuste de margem (seção 4.9)
- Implementar cálculo de perda inferida (seção 4.6)
- Implementar checagem intradiária e geração de ordem de produção emergencial (seção 4.7)
- Implementar módulo analítico/BI (seção 5)

---

## 9. Fora do escopo do V1 (decisão consciente)

| Item | Motivo |
|---|---|
| Custo de produção / margem financeira real | Priorizado quantidade e perda primeiro; custo entra como camada futura |
| Explosão de insumos/matéria-prima | Módulo futuro a oferecer, fora do escopo atual |
| Roteirização/logística de entrega | Objetivo é entregar o que cada loja necessita; rotas/caminhões fora do escopo |
| Conferência de recebimento na loja (o que foi enviado x o que chegou) | Não é ponto a tratar agora |
| Capacidade física de produção (limite de forno/mão de obra) | Não é prioridade no momento |
| Canal de alerta (push/e-mail) | Sem canal de alerta nesse momento — alertas ficam só no painel |
| Permissões granulares | V1 assume perfil único (gestor da central) com acesso total — múltiplos perfis é evolução futura |

---

## 10. Decisões já tomadas (registro para não retrabalhar)

- Rateio em escassez de produção: **decisão manual do gestor**, sistema só sugere
- PDV: **sistema único por rede** (não múltiplos adaptadores por loja)
- Previsão de perecíveis: **combinação de venda recente + sazonalidade**, não um só dos dois
- Cada loja pertence a **exatamente uma** central de produção
- SaaS é **comercial multi-cliente**, cada cliente com ambiente isolado
- Isolamento recomendado: **schema/banco separado por cliente**, dado o perfil de poucos clientes grandes
- Estrutura de repositório: **monorepo**, backend compartilhado entre app e SaaS
