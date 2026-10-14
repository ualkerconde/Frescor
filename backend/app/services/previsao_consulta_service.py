"""
Consulta das previsões gravadas e da qualidade do motor, para o SaaS web
(Fase 3 / F8). A geração fica em `previsao_gravacao.py`.

Escopo (D8): tudo é da central do gestor, filtrado também por negócio. A
loja, quando informada, é validada antes (app/api/escopo.py -> 404); este
serviço filtra pela central de qualquer forma, como segunda barreira.

1. `listar_previsoes`: as previsões gravadas de um dia, com os componentes
   (para a tela explicar cada número), a venda do mesmo dia da semana
   passada ao lado (D16/D17, para comparação) e totais por unidade (UN e KG
   não se somam).
2. `avaliar_qualidade`: teste no passado sob demanda (mesmo método do F6):
   para cada dia do período, prevê com o que se sabia até a véspera e
   compara com o real. WAPE e viés do motor e do ingênuo (mesmo dia da
   semana passada), sobre o mesmo conjunto de pares, por unidade. Período
   de no máximo 28 dias (as "últimas 4 semanas" do plano) para limitar o
   custo: cada dia é um cálculo completo da central.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.loja import Loja
from app.models.previsao_diaria import PrevisaoDiaria
from app.models.produto import Produto
from app.services.previsao_metricas import Metricas, medir, previsao_ingenua
from app.services.previsao_service import prever_central
from app.services.serie_vendas_service import series_da_loja

PERIODO_MAXIMO_QUALIDADE = 28


class ConsultaInvalida(ValueError):
    """Parâmetro de consulta inválido; a mensagem vai para o usuário."""


# ---------------------------------------------------------------- previsões


@dataclass
class ItemPrevisao:
    registro: PrevisaoDiaria
    loja_codigo: str | None
    loja_nome: str
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    venda_semana_passada: Decimal | None


@dataclass
class TotalPrevisto:
    unidade: str
    previsto: Decimal
    vendido_semana_passada: Decimal


@dataclass
class ResultadoPrevisoes:
    itens: list[ItemPrevisao]
    totais: list[TotalPrevisto]


def listar_previsoes(
    db: Session, gestor: GestorCentralAutenticado, dia: date, loja_id: int | None, produto_id: int | None
) -> ResultadoPrevisoes:
    consulta = (
        db.query(PrevisaoDiaria, Loja.codigo, Loja.nome, Produto.codigo, Produto.nome, Produto.unidade_medida)
        .join(Loja, Loja.id == PrevisaoDiaria.loja_id)
        .join(Produto, Produto.id == PrevisaoDiaria.produto_id)
        .filter(
            PrevisaoDiaria.negocio_id == gestor.negocio_id,
            PrevisaoDiaria.central_producao_id == gestor.central_producao_id,
            Loja.central_producao_id == gestor.central_producao_id,
            PrevisaoDiaria.data == dia,
        )
    )
    if loja_id is not None:
        consulta = consulta.filter(PrevisaoDiaria.loja_id == loja_id)
    if produto_id is not None:
        consulta = consulta.filter(PrevisaoDiaria.produto_id == produto_id)
    linhas = consulta.order_by(Loja.codigo.asc().nulls_last(), Loja.id, Produto.codigo.asc().nulls_last(),
                               Produto.id).all()

    # Venda do mesmo dia da semana passada, pelas regras da série (D16/D17).
    semana_passada = dia - timedelta(days=7)
    vendas: dict[tuple[int, int], Decimal | None] = {}
    for lid in {r.loja_id for r, *_ in linhas}:
        for pid, serie in series_da_loja(db, gestor.negocio_id, lid, semana_passada, semana_passada).items():
            vendas[(lid, pid)] = serie[semana_passada]

    itens = [
        ItemPrevisao(
            registro=r,
            loja_codigo=loja_codigo,
            loja_nome=loja_nome,
            produto_codigo=produto_codigo,
            produto_nome=produto_nome,
            unidade=unidade.value,
            venda_semana_passada=vendas.get((r.loja_id, r.produto_id)),
        )
        for r, loja_codigo, loja_nome, produto_codigo, produto_nome, unidade in linhas
    ]
    totais: dict[str, TotalPrevisto] = {}
    for i in itens:
        t = totais.setdefault(i.unidade, TotalPrevisto(i.unidade, Decimal("0"), Decimal("0")))
        if i.registro.previsao is not None:
            t.previsto += i.registro.previsao
        if i.venda_semana_passada is not None:
            t.vendido_semana_passada += i.venda_semana_passada
    return ResultadoPrevisoes(itens=itens, totais=[totais[u] for u in sorted(totais)])


# ---------------------------------------------------------------- qualidade


@dataclass
class QualidadeUnidade:
    unidade: str
    motor: Metricas
    ingenuo: Metricas

    @property
    def vence_ingenuo(self) -> bool | None:
        if self.motor.wape is None or self.ingenuo.wape is None:
            return None
        return self.motor.wape < self.ingenuo.wape


@dataclass
class ResultadoQualidade:
    data_inicio: date
    data_fim: date
    por_unidade: list[QualidadeUnidade]


def validar_periodo_qualidade(data_inicio: date, data_fim: date, hoje: date) -> None:
    if data_inicio > data_fim:
        raise ConsultaInvalida("A data inicial não pode ser depois da final.")
    if data_fim >= hoje:
        raise ConsultaInvalida("A qualidade só pode ser medida até ontem (o dia de hoje ainda não fechou).")
    if (data_fim - data_inicio).days + 1 > PERIODO_MAXIMO_QUALIDADE:
        raise ConsultaInvalida(f"O período da qualidade pode ter no máximo {PERIODO_MAXIMO_QUALIDADE} dias.")


def avaliar_qualidade(
    db: Session,
    gestor: GestorCentralAutenticado,
    data_inicio: date,
    data_fim: date,
    loja_id: int | None,
    produto_id: int | None,
    hoje: date,
) -> ResultadoQualidade:
    validar_periodo_qualidade(data_inicio, data_fim, hoje)
    dias = [data_inicio + timedelta(days=k) for k in range((data_fim - data_inicio).days + 1)]
    previstos: dict[tuple[int, int, date], Decimal | None] = {}
    for dia in dias:
        for x in prever_central(db, gestor.negocio_id, gestor.central_producao_id, dia - timedelta(days=1), dia):
            previstos[(x.loja_id, x.produto_id, dia)] = x.previsao

    lojas = {lid for lid, _, _ in previstos if loja_id is None or lid == loja_id}
    reais = {
        (lid, pid): serie
        for lid in lojas
        for pid, serie in series_da_loja(
            db, gestor.negocio_id, lid, data_inicio - timedelta(days=7), data_fim
        ).items()
        if produto_id is None or pid == produto_id
    }
    unidades = dict(
        db.query(Produto.id, Produto.unidade_medida).filter(
            Produto.negocio_id == gestor.negocio_id, Produto.id.in_({pid for _, pid in reais} or {0})
        )
    )

    pares: dict[str, list[tuple[Decimal, Decimal, Decimal]]] = defaultdict(list)
    for (lid, pid), serie in reais.items():
        for dia in dias:
            real, previsto, ingenuo = serie.get(dia), previstos.get((lid, pid, dia)), previsao_ingenua(serie, dia)
            if real is None or previsto is None or ingenuo is None:
                continue
            pares[unidades[pid].value].append((real, previsto, ingenuo))
    return ResultadoQualidade(
        data_inicio=data_inicio,
        data_fim=data_fim,
        por_unidade=[
            QualidadeUnidade(
                unidade=u,
                motor=medir((r, p) for r, p, _ in pares[u]),
                ingenuo=medir((r, i) for r, _, i in pares[u]),
            )
            for u in sorted(pares)
        ],
    )
