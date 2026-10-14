"""
Geração e gravação das previsões de uma central (Fase 3 / F7, D22).

`gerar_previsoes` calcula a previsão dos próximos dias (horizonte de 7,
D22) para todas as lojas ativas da central, com o motor completo
(`prever_central`), e grava em `previsoes_diarias` SUBSTITUINDO a geração
anterior daqueles dias na central.

Regras:
- Tudo ou nada: calcula os 7 dias primeiro, depois apaga e grava na mesma
  transação. Se qualquer passo falhar, nada muda (a geração anterior fica).
- Substituição: apaga as previsões da central nos dias do horizonte, não
  só as que serão regravadas. Assim some a linha de produto que deixou de
  receber previsão (desabilitado, inativo, fora da vigência) ou de loja
  desativada.
- Duas gerações simultâneas da mesma central (dois cliques, dois gestores)
  não se atropelam: a segunda espera a primeira terminar (trava da central
  no PostgreSQL, `pg_advisory_xact_lock`, liberada no fim da transação).
- `negocio_id`, `central_producao_id` e `usuario_id` vêm do gestor
  autenticado (a rota da F8 passa os dados de `obter_gestor_central`).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.previsao_diaria import EstatisticaBase, MetodoPrevisao, OrigemProxy, PrevisaoDiaria
from app.services.previsao_calculo import ESTATISTICA_PADRAO
from app.services.previsao_service import PrevisaoProduto, lojas_ativas_da_central, prever_central

HORIZONTE_DIAS = 7  # D22
# Identifica o método que gerou o número. Mudou uma regra do motor (base,
# tendência, cold start, eventos, sazonal), muda a versão.
# v1: base mediana (D25), tendência pela soma (D19).
# v2 (2026-10-14): tendência pela mediana das razões diárias (D31).
VERSAO_METODO = "2026.10-v2"
# Primeiro inteiro da trava: separa as travas deste serviço de outras que
# venham a usar pg_advisory_xact_lock(int, int) com o id da central.
_TRAVA_GERACAO = 3001


@dataclass(frozen=True)
class ResultadoGeracao:
    data_referencia: date
    data_inicio: date
    data_fim: date
    gravadas: int
    sem_previsao: int
    substituidas: int


def _linha(x: PrevisaoProduto, negocio_id: int, central_producao_id: int, data_referencia: date,
           estatistica: str, usuario_id: int | None) -> PrevisaoDiaria:
    c = x.componentes
    return PrevisaoDiaria(
        negocio_id=negocio_id,
        central_producao_id=central_producao_id,
        loja_id=x.loja_id,
        produto_id=x.produto_id,
        data=x.data_alvo,
        data_referencia=data_referencia,
        previsao=x.previsao,
        previsao_sem_evento=x.previsao_sem_evento,
        previsao_propria=x.previsao_propria,
        metodo=MetodoPrevisao(c.metodo),
        estatistica=EstatisticaBase(estatistica),
        base=c.base,
        semanas_na_base=c.semanas_na_base,
        tendencia=c.tendencia,
        tendencia_bruta=c.tendencia_bruta,
        dias_na_tendencia=c.dias_na_tendencia,
        inicio_historico=x.inicio_historico,
        peso_historico=x.peso_historico,
        proxy=x.proxy,
        origem_proxy=OrigemProxy(x.origem_proxy) if x.origem_proxy else None,
        eventos=[
            {"id": e.id, "nome": e.nome, "tipo_ajuste": e.tipo_ajuste.value, "valor_ajuste": str(e.valor_ajuste)}
            for e in x.eventos
        ],
        versao_metodo=VERSAO_METODO,
        gerado_por_usuario_id=usuario_id,
    )


def gerar_previsoes(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    data_referencia: date,
    usuario_id: int | None = None,
    dias: int = HORIZONTE_DIAS,
    estatistica: str = ESTATISTICA_PADRAO,
) -> ResultadoGeracao:
    """
    Calcula e grava as previsões de `data_referencia + 1` a
    `data_referencia + dias` para a central, substituindo as anteriores.
    `data_referencia` é o último dia com dado (normalmente ontem).
    """
    if not 1 <= dias <= HORIZONTE_DIAS:
        raise ValueError(f"O horizonte da previsão vai de 1 a {HORIZONTE_DIAS} dias.")
    inicio = data_referencia + timedelta(days=1)
    fim = data_referencia + timedelta(days=dias)
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": _TRAVA_GERACAO, "b": central_producao_id})
        previsoes: list[PrevisaoProduto] = []
        for k in range(dias):
            previsoes.extend(
                prever_central(db, negocio_id, central_producao_id, data_referencia, inicio + timedelta(days=k),
                               estatistica)
            )
        lojas = lojas_ativas_da_central(db, negocio_id, central_producao_id)
        substituidas = (
            db.query(PrevisaoDiaria)
            .filter(
                PrevisaoDiaria.negocio_id == negocio_id,
                PrevisaoDiaria.data >= inicio,
                PrevisaoDiaria.data <= fim,
                or_(PrevisaoDiaria.central_producao_id == central_producao_id, PrevisaoDiaria.loja_id.in_(lojas)),
            )
            .delete(synchronize_session=False)
        )
        db.add_all(
            _linha(x, negocio_id, central_producao_id, data_referencia, estatistica, usuario_id) for x in previsoes
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ResultadoGeracao(
        data_referencia=data_referencia,
        data_inicio=inicio,
        data_fim=fim,
        gravadas=len(previsoes),
        sem_previsao=sum(1 for x in previsoes if x.previsao is None),
        substituidas=substituidas,
    )
