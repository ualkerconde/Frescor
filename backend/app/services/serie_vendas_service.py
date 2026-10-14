"""
Série diária de vendas por loja + produto: a matéria-prima do motor de
previsão (Fase 3 / F1).

O motor não lê `vendas_diarias` direto. Ele recebe, para cada produto
habilitado na loja, um valor por dia da janela pedida, já com duas regras
aplicadas aqui (e só aqui):

- D16: com linha `api` e `manual` para a mesma loja + produto + data, vale
  a `api` (critério de `registros_efetivos`). Sem isso, o dia contaria em
  dobro e a previsão sairia inflada.
- D17: dia sem linha do produto vale ZERO se a loja tem alguma venda
  importada naquele dia (os dados do dia chegaram e o produto não vendeu),
  e fica FALTANTE (`None`) se a loja não tem nenhuma venda no dia (os dados
  não chegaram). Dia faltante fica fora da média e da tendência; tratá-lo
  como zero puxaria a previsão para baixo a cada falha de importação.

Produto não habilitado na loja (sem linha em `produtos_lojas`, ou com
`ativo = False`) e produto inativo no catálogo (`produtos.ativo = False`)
não recebem série, logo não recebem previsão (decisões de 2026-10-13).

Toda consulta filtra por `negocio_id`, que vem do usuário autenticado.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.produto import Produto
from app.models.produto_loja import ProdutoLoja
from app.models.venda_diaria import VendaDiaria
from app.services.registros_efetivos import condicao_registro_efetivo

# Valor de um dia da série: quantidade vendida (na unidade do produto) ou
# None quando o dia é faltante (D17).
SerieDiaria = dict[date, Decimal | None]


def _dias(inicio: date, fim: date) -> list[date]:
    if inicio > fim:
        raise ValueError("A data inicial da série não pode ser depois da final.")
    return [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]


def produtos_habilitados(db: Session, negocio_id: int, loja_id: int) -> list[int]:
    """Ids dos produtos ativos do negócio habilitados (e ativos) na loja."""
    linhas = (
        db.query(ProdutoLoja.produto_id)
        .join(Produto, Produto.id == ProdutoLoja.produto_id)
        .filter(
            Produto.negocio_id == negocio_id,
            Produto.ativo.is_(True),
            ProdutoLoja.loja_id == loja_id,
            ProdutoLoja.ativo.is_(True),
        )
        .order_by(ProdutoLoja.produto_id)
        .all()
    )
    return [produto_id for (produto_id,) in linhas]


def dias_com_vendas_na_loja(db: Session, negocio_id: int, loja_id: int, inicio: date, fim: date) -> set[date]:
    """Dias da janela em que a loja tem pelo menos uma venda importada (qualquer produto e origem)."""
    linhas = (
        db.query(VendaDiaria.data)
        .filter(
            VendaDiaria.negocio_id == negocio_id,
            VendaDiaria.loja_id == loja_id,
            VendaDiaria.data >= inicio,
            VendaDiaria.data <= fim,
        )
        .distinct()
        .all()
    )
    return {dia for (dia,) in linhas}


def series_da_loja(
    db: Session,
    negocio_id: int,
    loja_id: int,
    inicio: date,
    fim: date,
    produto_ids: list[int] | None = None,
) -> dict[int, SerieDiaria]:
    """
    Série diária de cada produto habilitado na loja, de `inicio` a `fim`
    (inclusive). `produto_ids` restringe a lista; produto pedido e não
    habilitado fica de fora do resultado.

    Uma consulta para as vendas e outra para os dias com dados, para a
    loja inteira: a geração da previsão (F7) chama isso uma vez por loja.
    """
    dias = _dias(inicio, fim)
    habilitados = produtos_habilitados(db, negocio_id, loja_id)
    if produto_ids is not None:
        pedidos = set(produto_ids)
        habilitados = [p for p in habilitados if p in pedidos]
    if not habilitados:
        return {}

    vendidos: dict[tuple[int, date], Decimal] = {
        (produto_id, dia): total
        for produto_id, dia, total in (
            db.query(VendaDiaria.produto_id, VendaDiaria.data, func.sum(VendaDiaria.quantidade))
            .filter(
                VendaDiaria.negocio_id == negocio_id,
                VendaDiaria.loja_id == loja_id,
                VendaDiaria.produto_id.in_(habilitados),
                VendaDiaria.data >= inicio,
                VendaDiaria.data <= fim,
                condicao_registro_efetivo(VendaDiaria),
            )
            .group_by(VendaDiaria.produto_id, VendaDiaria.data)
            .all()
        )
    }
    com_dados = dias_com_vendas_na_loja(db, negocio_id, loja_id, inicio, fim)

    series: dict[int, SerieDiaria] = {}
    for produto_id in habilitados:
        serie: SerieDiaria = {}
        for dia in dias:
            if (produto_id, dia) in vendidos:
                serie[dia] = vendidos[(produto_id, dia)]
            elif dia in com_dados:
                serie[dia] = Decimal("0")
            else:
                serie[dia] = None
        series[produto_id] = serie
    return series


def serie_diaria(
    db: Session, negocio_id: int, loja_id: int, produto_id: int, inicio: date, fim: date
) -> SerieDiaria | None:
    """Série de um produto; None se o produto não está habilitado na loja."""
    return series_da_loja(db, negocio_id, loja_id, inicio, fim, [produto_id]).get(produto_id)
