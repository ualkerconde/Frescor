"""
Modelo da tabela `integracoes_vendas` (D108, migration 0027).

Por que existe: a venda diária por produto vem do sistema do cliente (ERP
ou PDV), sem CSV no dia a dia (D107). Como o sistema ainda não foi
definido, o conector é genérico e tem dois modos:

- `envio` (push): o sistema do cliente chama POST /integracao/vendas com a
  chave do negócio. Só o hash SHA-256 da chave fica aqui (e o prefixo, para
  reconhecer qual chave é); a chave em si aparece uma vez, na criação.
- `busca` (pull): o Frescor busca no `url_busca` do cliente, no
  `horario_busca` (hora de Brasília), a venda de ontem e rebusca os
  `dias_rebusca` anteriores (correções do PDV). A credencial NÃO fica no
  banco: fica na variável de ambiente do servidor chamada
  `variavel_credencial`.

Uma integração por negócio. Configurada na implantação
(`scripts/configurar_integracao_vendas.py`); o gestor vê o estado, as
execuções e as pendências no SaaS.
"""

import enum
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ModoIntegracaoVendas(str, enum.Enum):
    ENVIO = "envio"
    BUSCA = "busca"


class IntegracaoVendas(Base):
    __tablename__ = "integracoes_vendas"
    __table_args__ = (
        UniqueConstraint("negocio_id", name="uq_integracao_vendas_negocio"),
        UniqueConstraint("chave_hash", name="uq_integracao_vendas_chave"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False)
    modo: Mapped[ModoIntegracaoVendas] = mapped_column(
        Enum(ModoIntegracaoVendas, name="modointegracaovendas",
             values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sistema = mapped_column(String(60), nullable=True)  # nome do ERP/PDV, só para mostrar
    url_busca = mapped_column(String(500), nullable=True)
    variavel_credencial = mapped_column(String(100), nullable=True)
    horario_busca: Mapped[time] = mapped_column(Time, nullable=False, server_default="05:00")
    dias_rebusca: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    chave_hash = mapped_column(String(64), nullable=True)
    chave_prefixo = mapped_column(String(12), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    atualizado_em = mapped_column(DateTime, nullable=True)
