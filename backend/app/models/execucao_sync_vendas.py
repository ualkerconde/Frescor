"""
Modelo da tabela `execucoes_sync_vendas` (D108, migration 0027).

Por que existe: a venda chega sozinha, de madrugada; se falhar, ninguém vê.
Cada busca (agendada ou "Buscar agora") e cada envio do sistema do cliente
fica registrado com o resultado (linhas recebidas, gravadas, pendentes e
inválidas, e a mensagem de erro), e o gestor acompanha na tela de
integração. Datas e horas em UTC sem fuso, como o resto do backend.
"""

import enum
from datetime import datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrigemExecucaoSync(str, enum.Enum):
    AGENDADA = "agendada"
    MANUAL = "manual"
    ENVIO = "envio"


class SituacaoExecucaoSync(str, enum.Enum):
    SUCESSO = "sucesso"
    PARCIAL = "parcial"  # gravou, mas sobrou pendência ou linha inválida
    FALHOU = "falhou"


def _enum(classe, nome):
    return Enum(classe, name=nome, values_callable=lambda enum_cls: [e.value for e in enum_cls])


class ExecucaoSyncVendas(Base):
    __tablename__ = "execucoes_sync_vendas"
    __table_args__ = (Index("ix_execucoes_sync_vendas_negocio_iniciada", "negocio_id", "iniciada_em"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    origem: Mapped[OrigemExecucaoSync] = mapped_column(_enum(OrigemExecucaoSync, "origemexecucaosync"),
                                                       nullable=False)
    situacao: Mapped[SituacaoExecucaoSync] = mapped_column(_enum(SituacaoExecucaoSync, "situacaoexecucaosync"),
                                                           nullable=False)
    data_inicio = mapped_column(Date, nullable=True)
    data_fim = mapped_column(Date, nullable=True)
    iniciada_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    terminada_em = mapped_column(DateTime, nullable=True)
    linhas_recebidas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    linhas_gravadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    linhas_pendentes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    linhas_invalidas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    mensagem = mapped_column(String(500), nullable=True)
    iniciada_por_usuario_id = mapped_column(ForeignKey("usuarios.id"), nullable=True)
