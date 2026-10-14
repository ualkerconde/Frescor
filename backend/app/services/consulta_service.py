"""
Consulta de vendas e perdas diárias para o SaaS web (Fase 2 / P6).

É o que o gestor usa para conferir o que foi importado e, mais adiante, o
que o motor de previsão vai ler. Por isso o escopo é o mesmo da importação:
só as lojas da central do gestor (D8), filtrado também por negócio.

Regras:
- Período obrigatório (data_inicio e data_fim, inclusive), no máximo
  PERIODO_MAXIMO_DIAS dias, para a consulta não varrer anos de dados.
- Filtros opcionais: loja e produto. A loja, quando informada, é validada
  contra o escopo ANTES de chegar aqui (app/api/escopo.py -> 404); este
  serviço filtra pelo escopo de qualquer forma, como segunda barreira.
  Produto de outro negócio simplesmente não retorna nada.
- Ordenação estável: data, loja, produto, origem e id (a origem e o id
  desempatam venda manual e via API do mesmo dia), para a paginação por
  limit/offset nunca repetir nem pular linha.
- Totais do período (frontend W7): soma das quantidades com os mesmos
  filtros, SEM paginação, separada por unidade (UN e KG não se somam).
- D16: quando um dia tem `manual` e `api` para a mesma loja + produto, vale
  a `api` -- a `manual` não aparece na listagem nem entra nos totais. O
  critério fica em registros_efetivos.py (único lugar; a Fase 3 usa o mesmo).
"""

import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.loja import Loja
from app.models.perda_diaria import PerdaDiaria
from app.models.produto import Produto
from app.models.venda_diaria import VendaDiaria
from app.services.escopo_service import consulta_lojas_do_gestor
from app.services.registros_efetivos import condicao_registro_efetivo

PERIODO_MAXIMO_DIAS = 366


class TipoConsulta(str, enum.Enum):
    VENDA = "venda"
    PERDA = "perda"


class PeriodoInvalido(ValueError):
    """Período de consulta inválido; a mensagem vai para o usuário."""


@dataclass
class TotalPorUnidade:
    unidade: str
    quantidade: Decimal


@dataclass
class ResultadoConsulta:
    total: int
    itens: list["ItemConsulta"]
    totais: list[TotalPorUnidade]


@dataclass
class ItemConsulta:
    data: date
    loja_id: int
    loja_codigo: Optional[str]
    produto_id: int
    produto_codigo: Optional[str]
    produto_nome: str
    quantidade: Decimal
    unidade: str
    origem: str


def validar_periodo(data_inicio: date, data_fim: date) -> None:
    if data_inicio > data_fim:
        raise PeriodoInvalido(
            f"data_inicio ({data_inicio:%d/%m/%Y}) é posterior a data_fim ({data_fim:%d/%m/%Y})."
        )
    dias = (data_fim - data_inicio).days + 1
    if dias > PERIODO_MAXIMO_DIAS:
        raise PeriodoInvalido(
            f"Período de {dias} dias; o máximo é {PERIODO_MAXIMO_DIAS}. Divida a consulta em períodos menores."
        )


def consultar(
    db: Session,
    gestor: GestorCentralAutenticado,
    tipo: TipoConsulta,
    data_inicio: date,
    data_fim: date,
    loja_id: Optional[int] = None,
    produto_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> ResultadoConsulta:
    """Total de linhas, itens da página e totais por unidade do período (sem paginação)."""
    validar_periodo(data_inicio, data_fim)
    modelo = VendaDiaria if tipo == TipoConsulta.VENDA else PerdaDiaria

    lojas_do_escopo = consulta_lojas_do_gestor(db, gestor).with_entities(Loja.id)
    consulta = (
        db.query(modelo, Loja, Produto)
        .join(Loja, Loja.id == modelo.loja_id)
        .join(Produto, Produto.id == modelo.produto_id)
        .filter(
            modelo.negocio_id == gestor.negocio_id,
            modelo.loja_id.in_(lojas_do_escopo),
            modelo.data >= data_inicio,
            modelo.data <= data_fim,
            condicao_registro_efetivo(modelo),  # D16: api prevalece sobre manual
        )
    )
    if loja_id is not None:
        consulta = consulta.filter(modelo.loja_id == loja_id)
    if produto_id is not None:
        consulta = consulta.filter(modelo.produto_id == produto_id)

    total = consulta.count()

    # Mesmos filtros, sem paginação, uma soma por unidade (UN antes de KG).
    somas = (
        consulta.with_entities(Produto.unidade_medida, func.sum(modelo.quantidade))
        .group_by(Produto.unidade_medida)
        .all()
    )
    ordem_unidades = {"UN": 0, "KG": 1}
    totais = sorted(
        (TotalPorUnidade(unidade=unidade.value, quantidade=soma) for unidade, soma in somas),
        key=lambda t: ordem_unidades.get(t.unidade, 9),
    )

    linhas = (
        consulta.order_by(modelo.data, modelo.loja_id, modelo.produto_id, modelo.origem, modelo.id)
        .limit(limit)
        .offset(offset)
        .all()
    )
    itens = [
        ItemConsulta(
            data=registro.data,
            loja_id=loja.id,
            loja_codigo=loja.codigo,
            produto_id=produto.id,
            produto_codigo=produto.codigo,
            produto_nome=produto.nome,
            quantidade=registro.quantidade,
            unidade=produto.unidade_medida.value,
            origem=registro.origem.value,
        )
        for registro, loja, produto in linhas
    ]
    return ResultadoConsulta(total=total, itens=itens, totais=totais)
