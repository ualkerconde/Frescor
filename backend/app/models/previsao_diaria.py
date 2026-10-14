"""
Modelo da tabela `previsoes_diarias` (Fase 3 / F7, decisão D22).

Previsão de venda de cada loja + produto para cada dia do horizonte (7
dias), gravada para que a central consulte o mesmo número que vai usar na
ordem de produção (Fase 4) e para que a tela explique de onde ele veio.

Por que gravar, e não calcular na hora: o número precisa ser estável entre
a consulta e a ordem de produção, auditável ("o que o sistema previu na
segunda?") e barato de ler. O cálculo é sob demanda por enquanto (o gestor
pede); o job noturno vem depois de validado (D22).

Uma linha por loja + produto + dia previsto (uq). Gerar de novo SUBSTITUI a
geração anterior daqueles dias na central (o serviço apaga e grava na mesma
transação, ver `previsao_gravacao.py`).

Os componentes ficam gravados ao lado do número (base, tendência, peso do
histórico, proxy, eventos), junto com a versão do método, para a tela
explicar cada linha e para comparar versões do motor no futuro.

`previsao` NULL = não havia como prever (produto sem histórico e sem
proxy). A linha existe para a tela mostrar "sem previsão" em vez de sumir
com o produto.

Precisão: Numeric(14, 4). A previsão não é arredondada para a unidade
(D21); só a gravação guarda 4 casas decimais (0,0001 un ou kg).

Isolamento (D2): `negocio_id` + FKs compostas para loja, produto e central
do mesmo negócio.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MetodoPrevisao(str, enum.Enum):
    SEMANAL = "semanal"  # últimas 6 semanas (D18)
    SAZONAL = "sazonal"  # mesmo período do ano anterior (F5)


class EstatisticaBase(str, enum.Enum):
    MEDIANA = "mediana"  # padrão (D25)
    MEDIA = "media"
    MEDIA_APARADA = "media_aparada"


class OrigemProxy(str, enum.Enum):
    OUTRAS_LOJAS = "outras_lojas"  # loja nova (D20)
    CATEGORIA = "categoria"  # produto novo: mesma categoria e unidade (D20)
    UNIDADE = "unidade"  # produto novo: mesma unidade (D20, D29)


def _enum(cls, nome):
    return Enum(cls, name=nome, values_callable=lambda enum_cls: [e.value for e in enum_cls])


class PrevisaoDiaria(Base):
    __tablename__ = "previsoes_diarias"
    __table_args__ = (
        UniqueConstraint("loja_id", "produto_id", "data", name="uq_previsao_loja_produto_data"),
        CheckConstraint("previsao IS NULL OR previsao >= 0", name="ck_previsao_nao_negativa"),
        CheckConstraint("peso_historico >= 0 AND peso_historico <= 1", name="ck_previsao_peso_0_a_1"),
        CheckConstraint("data > data_referencia", name="ck_previsao_data_depois_da_referencia"),
        ForeignKeyConstraint(["negocio_id", "loja_id"], ["lojas.negocio_id", "lojas.id"], name="fk_previsao_negocio_loja"),
        ForeignKeyConstraint(
            ["negocio_id", "produto_id"], ["produtos.negocio_id", "produtos.id"], name="fk_previsao_negocio_produto"
        ),
        ForeignKeyConstraint(
            ["negocio_id", "central_producao_id"],
            ["centrais_producao.negocio_id", "centrais_producao.id"],
            name="fk_previsao_negocio_central",
        ),
        # Consulta típica: previsões da central num período.
        Index("ix_previsoes_central_data", "negocio_id", "central_producao_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    central_producao_id: Mapped[int] = mapped_column(ForeignKey("centrais_producao.id"), nullable=False)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    # Dia previsto e último dia de dado usado no cálculo (normalmente a véspera da geração).
    data: Mapped[date] = mapped_column(Date, nullable=False)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)

    # Número final (depois do cold start e do evento) e as etapas até ele.
    previsao = mapped_column(Numeric(14, 4), nullable=True)
    previsao_sem_evento = mapped_column(Numeric(14, 4), nullable=True)
    previsao_propria = mapped_column(Numeric(14, 4), nullable=True)

    # Componentes da previsão própria (F2/F5).
    metodo: Mapped[MetodoPrevisao] = mapped_column(_enum(MetodoPrevisao, "metodoprevisao"), nullable=False)
    estatistica: Mapped[EstatisticaBase] = mapped_column(_enum(EstatisticaBase, "estatisticabase"), nullable=False)
    base = mapped_column(Numeric(14, 4), nullable=True)
    semanas_na_base: Mapped[int] = mapped_column(Integer, nullable=False)
    tendencia: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    tendencia_bruta = mapped_column(Numeric(14, 4), nullable=True)
    dias_na_tendencia: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cold start (F4).
    inicio_historico = mapped_column(Date, nullable=True)
    peso_historico: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    proxy = mapped_column(Numeric(14, 4), nullable=True)
    origem_proxy = mapped_column(_enum(OrigemProxy, "origemproxy"), nullable=True)

    # Eventos que mexeram no número (F3): [{"id", "nome", "tipo_ajuste", "valor_ajuste"}].
    eventos: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    versao_metodo: Mapped[str] = mapped_column(String(32), nullable=False)
    gerado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # Quem pediu a geração (NULL quando vier do job noturno).
    gerado_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
