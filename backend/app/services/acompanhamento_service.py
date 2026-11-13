"""
Acompanhamento (dashboard, D115/D116): previsto × solicitado × produzido ×
enviado × vendido × perda, por dia e por produto, nas lojas do gestor.

Por que existe: o Ualker quer "verificar as previsões, o que foi solicitado,
o produzido e a venda real" num lugar só. Cada número já existe em outra
tabela; aqui eles só são lidos e somados, nada é gravado.

De onde vem cada coluna (sempre filtrado por negócio e pelas lojas do
gestor, regra de ouro 1):
- previsto: `previsoes_diarias.previsao` do dia (a última gerada para ele).
  O banco já garante que ela foi feita antes do dia
  (`ck_previsao_data_depois_da_referencia`); o filtro repete a regra aqui
  porque o erro da previsão só vale para previsão feita antes.
- sugerido e final (D115): linhas das ordens de produção APROVADAS, pelo dia
  de ENTREGA (o dia em que o produto chega à loja). Rascunho não conta.
- produzido: `quantidade_produzida` dos itens dessas ordens, pelo dia de
  entrega. É da central inteira, não por loja: com filtro de loja, fica
  de fora (`produzido_disponivel = False`).
- enviado: itens dos romaneios cuja entrega saiu da central (`expedido_em`
  preenchido), pelo dia de entrega, na quantidade final do romaneio.
- vendido e perda: `vendas_diarias` e `perdas_diarias` efetivas (a linha
  `api` vence a `manual`, D16), do próprio dia.

Erro da previsão (D116): só nas células loja × produto × dia que têm
previsão E venda registrada.
- WAPE = Σ|previsto − vendido| ÷ Σ vendido  (0,15 = errou 15% do vendido)
- viés = (Σ previsto − Σ vendido) ÷ Σ vendido  (+ = previu a mais)
Sem venda nas células comparadas, os dois ficam None.

Produção × venda NÃO se compara dia a dia (o que chega num dia vende nos
seguintes): o painel mostra os dias lado a lado e compara os totais do
período. "Sobra" = enviado − vendido − perda lançada no período: inclui o
que ainda está na prateleira, por isso não é perda.

Perda sem registro e ruptura (D111): pela contagem do fechamento, em
`perda_sem_registro_service`; só nas células em que dá para fazer o
balanço (as duas contagens e venda registrada na loja no dia). `balancos`
diz em quantas células, para a tela não mostrar 0 quando não houve conta.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.ordem_producao_linha import OrdemProducaoLinha
from app.models.perda_diaria import PerdaDiaria
from app.models.previsao_diaria import PrevisaoDiaria
from app.models.produto import Produto
from app.models.romaneio import Romaneio
from app.models.romaneio_entrega import RomaneioEntrega
from app.models.romaneio_item import RomaneioItem
from app.models.venda_diaria import VendaDiaria
from app.services import perda_sem_registro_service
from app.services.registros_efetivos import condicao_registro_efetivo

PERIODO_PADRAO_DIAS = 7
PERIODO_MAXIMO_DIAS = 28
# sem_registro (D111): perda sem registro pela contagem, só nas células com balanço
# (perda_sem_registro_service).
METRICAS = ("previsto", "sugerido", "final", "produzido", "enviado", "vendido", "perda", "sem_registro")

Celula = tuple[int, int, date]  # loja, produto, dia


@dataclass
class Erro:
    wape: Decimal | None
    vies: Decimal | None
    celulas: int


@dataclass
class Linha:
    """Valores somados de um dia ou de um produto. None = nenhum registro daquela métrica."""

    valores: dict[str, Decimal | None] = field(default_factory=lambda: {m: None for m in METRICAS})

    def somar(self, metrica: str, valor) -> None:
        atual = self.valores[metrica]
        self.valores[metrica] = (atual or Decimal(0)) + Decimal(valor)


@dataclass
class SerieUnidade:
    unidade: str
    totais: Linha
    erro: Erro
    dias: dict[date, Linha]
    # D111: células loja × produto × dia com balanço da contagem, e quantas delas acabaram (ruptura).
    balancos: int = 0
    rupturas: int = 0


@dataclass
class LinhaProduto:
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    totais: Linha
    erro: Erro
    sobra: Decimal | None
    balancos: int = 0
    rupturas: int = 0


@dataclass
class Acompanhamento:
    data_inicio: date
    data_fim: date
    produzido_disponivel: bool
    unidades: list[SerieUnidade]
    produtos: list[LinhaProduto]


class PeriodoInvalido(Exception):
    pass


def validar_periodo(inicio: date, fim: date) -> None:
    if fim < inicio:
        raise PeriodoInvalido("A data final não pode ser antes da inicial.")
    if (fim - inicio).days + 1 > PERIODO_MAXIMO_DIAS:
        raise PeriodoInvalido(f"O período pode ter até {PERIODO_MAXIMO_DIAS} dias.")


def calcular_erro(pares: list[tuple[Decimal, Decimal]]) -> Erro:
    """`pares` = (previsto, vendido) das células com os dois."""
    if not pares:
        return Erro(None, None, 0)
    vendido = sum((v for _, v in pares), Decimal(0))
    if vendido <= 0:
        return Erro(None, None, len(pares))
    absoluto = sum((abs(p - v) for p, v in pares), Decimal(0))
    previsto = sum((p for p, _ in pares), Decimal(0))
    return Erro(absoluto / vendido, (previsto - vendido) / vendido, len(pares))


# ------------------------------------------------------------------ leitura

def _por_celula(linhas) -> dict[Celula, Decimal]:
    saida: dict[Celula, Decimal] = defaultdict(Decimal)
    for loja_id, produto_id, dia, valor in linhas:
        if valor is not None:
            saida[(loja_id, produto_id, dia)] += Decimal(valor)
    return saida


def _diarios(db, modelo, negocio_id, lojas, inicio, fim, produto_id):
    q = (
        db.query(modelo.loja_id, modelo.produto_id, modelo.data, func.sum(modelo.quantidade))
        .filter(modelo.negocio_id == negocio_id, modelo.loja_id.in_(lojas), modelo.data >= inicio,
                modelo.data <= fim, condicao_registro_efetivo(modelo))
    )
    if produto_id is not None:
        q = q.filter(modelo.produto_id == produto_id)
    return _por_celula(q.group_by(modelo.loja_id, modelo.produto_id, modelo.data))


def _previsoes(db, negocio_id, lojas, inicio, fim, produto_id):
    q = db.query(PrevisaoDiaria.loja_id, PrevisaoDiaria.produto_id, PrevisaoDiaria.data, PrevisaoDiaria.previsao).filter(
        PrevisaoDiaria.negocio_id == negocio_id, PrevisaoDiaria.loja_id.in_(lojas), PrevisaoDiaria.data >= inicio,
        PrevisaoDiaria.data <= fim, PrevisaoDiaria.data_referencia < PrevisaoDiaria.data,
        PrevisaoDiaria.previsao.isnot(None),
    )
    if produto_id is not None:
        q = q.filter(PrevisaoDiaria.produto_id == produto_id)
    return _por_celula(q)


def _ordens(db, negocio_id, central_id, lojas, inicio, fim, produto_id):
    base = (
        db.query(OrdemProducaoLinha.loja_id, OrdemProducaoItem.produto_id, OrdemProducao.data_entrega,
                 OrdemProducaoLinha.quantidade_sugerida, OrdemProducaoLinha.quantidade_final)
        .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
        .join(OrdemProducao, OrdemProducao.id == OrdemProducaoItem.ordem_id)
        .filter(OrdemProducao.negocio_id == negocio_id, OrdemProducao.central_producao_id == central_id,
                OrdemProducao.status == StatusOrdemProducao.APROVADA, OrdemProducao.data_entrega >= inicio,
                OrdemProducao.data_entrega <= fim, OrdemProducaoLinha.negocio_id == negocio_id,
                OrdemProducaoLinha.loja_id.in_(lojas))
    )
    if produto_id is not None:
        base = base.filter(OrdemProducaoItem.produto_id == produto_id)
    linhas = base.all()
    sugerido = _por_celula((l, p, d, s) for l, p, d, s, _ in linhas)
    final = _por_celula((l, p, d, f) for l, p, d, _, f in linhas)
    return sugerido, final


def _produzido(db, negocio_id, central_id, inicio, fim, produto_id) -> dict[tuple[int, date], Decimal]:
    q = (
        db.query(OrdemProducaoItem.produto_id, OrdemProducao.data_entrega,
                 func.sum(OrdemProducaoItem.quantidade_produzida))
        .join(OrdemProducao, OrdemProducao.id == OrdemProducaoItem.ordem_id)
        .filter(OrdemProducao.negocio_id == negocio_id, OrdemProducao.central_producao_id == central_id,
                OrdemProducao.status == StatusOrdemProducao.APROVADA, OrdemProducao.data_entrega >= inicio,
                OrdemProducao.data_entrega <= fim, OrdemProducaoItem.quantidade_produzida.isnot(None))
    )
    if produto_id is not None:
        q = q.filter(OrdemProducaoItem.produto_id == produto_id)
    return {(p, d): Decimal(t) for p, d, t in q.group_by(OrdemProducaoItem.produto_id, OrdemProducao.data_entrega)}


def _enviado(db, negocio_id, central_id, lojas, inicio, fim, produto_id):
    q = (
        db.query(RomaneioEntrega.loja_id, RomaneioItem.produto_id, Romaneio.data_entrega,
                 func.sum(RomaneioItem.quantidade_final))
        .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
        .join(Romaneio, Romaneio.id == RomaneioEntrega.romaneio_id)
        .filter(Romaneio.negocio_id == negocio_id, Romaneio.central_producao_id == central_id,
                Romaneio.data_entrega >= inicio, Romaneio.data_entrega <= fim,
                RomaneioEntrega.loja_id.in_(lojas), RomaneioEntrega.expedido_em.isnot(None))
    )
    if produto_id is not None:
        q = q.filter(RomaneioItem.produto_id == produto_id)
    return _por_celula(q.group_by(RomaneioEntrega.loja_id, RomaneioItem.produto_id, Romaneio.data_entrega))


# ------------------------------------------------------------------ montagem

def montar(
    inicio: date,
    fim: date,
    produtos: dict[int, Produto],
    celulas: dict[str, dict[Celula, Decimal]],
    produzido: dict[tuple[int, date], Decimal] | None,
    rupturas: dict[Celula, bool] | None = None,
) -> Acompanhamento:
    """
    Junta as leituras (função pura, testável sem banco). `rupturas`: célula
    com balanço da contagem (D111) -> acabou no dia.
    """
    dias = [inicio + timedelta(days=k) for k in range((fim - inicio).days + 1)]
    unidade = {pid: p.unidade_medida.value for pid, p in produtos.items()}

    series: dict[str, SerieUnidade] = {}
    por_produto: dict[int, Linha] = defaultdict(Linha)
    pares_unidade: dict[str, list] = defaultdict(list)
    pares_produto: dict[int, list] = defaultdict(list)

    def serie(u: str) -> SerieUnidade:
        if u not in series:
            series[u] = SerieUnidade(u, Linha(), Erro(None, None, 0), {d: Linha() for d in dias})
        return series[u]

    for metrica, valores in celulas.items():
        for (_loja, pid, dia), valor in valores.items():
            if pid not in unidade:
                continue
            s = serie(unidade[pid])
            s.dias[dia].somar(metrica, valor)
            s.totais.somar(metrica, valor)
            por_produto[pid].somar(metrica, valor)
    if produzido is not None:
        for (pid, dia), valor in produzido.items():
            if pid not in unidade:
                continue
            s = serie(unidade[pid])
            s.dias[dia].somar("produzido", valor)
            s.totais.somar("produzido", valor)
            por_produto[pid].somar("produzido", valor)

    previsto, vendido = celulas.get("previsto", {}), celulas.get("vendido", {})
    for celula, p in previsto.items():
        v = vendido.get(celula)
        if v is None or celula[1] not in unidade:
            continue
        pares_unidade[unidade[celula[1]]].append((p, v))
        pares_produto[celula[1]].append((p, v))
    for u, s in series.items():
        s.erro = calcular_erro(pares_unidade[u])

    contagem_produto: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # balanços, rupturas
    for (_loja, pid, _dia), acabou in (rupturas or {}).items():
        if pid not in unidade:
            continue
        s = serie(unidade[pid])
        s.balancos += 1
        s.rupturas += int(acabou)
        contagem_produto[pid][0] += 1
        contagem_produto[pid][1] += int(acabou)

    linhas_produto = []
    for pid, totais in por_produto.items():
        p = produtos[pid]
        t = totais.valores
        sobra = None
        if t["enviado"] is not None and t["vendido"] is not None:
            sobra = t["enviado"] - t["vendido"] - (t["perda"] or Decimal(0))
        balancos, n_rupturas = contagem_produto.get(pid, (0, 0))
        linhas_produto.append(LinhaProduto(pid, p.codigo, p.nome, unidade[pid], totais,
                                           calcular_erro(pares_produto[pid]), sobra, balancos, n_rupturas))
    linhas_produto.sort(key=lambda l: (l.produto_nome.lower(), l.produto_id))
    ordem_unidades = sorted(series.values(), key=lambda s: (s.unidade != "UN", s.unidade))
    return Acompanhamento(inicio, fim, produzido is not None, ordem_unidades, linhas_produto)


def acompanhamento(
    db: Session,
    negocio_id: int,
    central_id: int,
    lojas: list[int],
    inicio: date,
    fim: date,
    produto_id: int | None = None,
    *,
    por_loja: bool = False,
) -> Acompanhamento:
    """`por_loja` = o gestor filtrou uma loja: a produção (da central) fica de fora."""
    validar_periodo(inicio, fim)
    if not lojas:
        return Acompanhamento(inicio, fim, not por_loja, [], [])
    celulas = {
        "previsto": _previsoes(db, negocio_id, lojas, inicio, fim, produto_id),
        "vendido": _diarios(db, VendaDiaria, negocio_id, lojas, inicio, fim, produto_id),
        "perda": _diarios(db, PerdaDiaria, negocio_id, lojas, inicio, fim, produto_id),
        "enviado": _enviado(db, negocio_id, central_id, lojas, inicio, fim, produto_id),
    }
    celulas["sugerido"], celulas["final"] = _ordens(db, negocio_id, central_id, lojas, inicio, fim, produto_id)
    balancos = perda_sem_registro_service.calcular(db, negocio_id, lojas, inicio, fim, produto_id)
    celulas["sem_registro"] = {c: b.sem_registro for c, b in balancos.items()}
    produzido = None if por_loja else _produzido(db, negocio_id, central_id, inicio, fim, produto_id)

    ids = {c[1] for valores in celulas.values() for c in valores} | {p for p, _ in (produzido or {})}
    produtos = {}
    if ids:
        produtos = {p.id: p for p in db.query(Produto).filter(Produto.negocio_id == negocio_id, Produto.id.in_(ids))}
    return montar(inicio, fim, produtos, celulas, produzido, {c: b.ruptura for c, b in balancos.items()})
