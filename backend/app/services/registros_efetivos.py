"""
Qual registro de venda/perda "vale" quando há mais de uma origem para o
mesmo dia (decisão D16 em docs/STATUS.md).

A D5 permite que um mesmo loja + produto + data tenha uma linha `manual`
(importação de CSV) e uma `api` (integração com o PDV), para comparar as
duas na transição. Mas, para qualquer número de negócio (consulta, totais,
motor de previsão da Fase 3), só UMA delas pode valer -- senão o dia conta
em dobro.

Regra (D16): vale a `api`. A `manual` do mesmo loja + produto + data fica
como reserva: continua gravada, mas não entra na listagem nem nas somas.
Sem `api` para aquele dia, a `manual` vale normalmente.

A origem `inferida` (perdas calculadas, Fase 8) é outro conceito -- não é
"a mesma informação vinda de outra fonte" -- e não é afetada por esta regra.

Este módulo é o ÚNICO lugar do critério: toda leitura de vendas/perdas para
números de negócio deve aplicar `condicao_registro_efetivo`.
"""

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.perda_diaria import OrigemPerda, PerdaDiaria
from app.models.venda_diaria import OrigemVenda, VendaDiaria

_ORIGENS = {
    VendaDiaria: (OrigemVenda.API, OrigemVenda.MANUAL),
    PerdaDiaria: (OrigemPerda.API, OrigemPerda.MANUAL),
}


def condicao_registro_efetivo(modelo: type[VendaDiaria] | type[PerdaDiaria]) -> ColumnElement[bool]:
    """
    Condição SQL (para usar num .filter) que deixa de fora a linha `manual`
    quando existe uma linha `api` para a mesma loja + produto + data.
    """
    api, manual = _ORIGENS[modelo]
    outra = aliased(modelo)
    existe_api_no_mesmo_dia = exists().where(
        and_(
            outra.loja_id == modelo.loja_id,
            outra.produto_id == modelo.produto_id,
            outra.data == modelo.data,
            outra.origem == api,
        )
    )
    return or_(modelo.origem != manual, ~existe_api_no_mesmo_dia)
