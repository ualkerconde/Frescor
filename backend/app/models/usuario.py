"""
Modelo da tabela `usuarios`.

Cada usuário pertence a uma loja fixa (loja_id) — não escolhe nem troca de
loja dentro do app. O negocio_id também é mantido aqui, de forma
redundante em relação à loja (toda loja já pertence a um negócio): isso é
intencional, como uma segunda camada de proteção para o isolamento
multiempresa (ver app/models/produto_loja.py para o racional completo).

Login é individual via e-mail + senha. Duas flags independentes controlam
as duas portas de entrada do produto (decisão D1 em docs/STATUS.md):
- `tem_acesso_app`: pode autenticar no aplicativo móvel (PWA) das lojas.
- `tem_acesso_web`: pode autenticar no SaaS web da central de produção.
São separadas para que o gestor de central não precise ganhar acesso ao
app só para entrar no SaaS, e vice-versa.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class StatusUsuario(str, enum.Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"


class TipoUsuario(str, enum.Enum):
    OPERADOR_LOJA = "operador_loja"
    GESTOR_CENTRAL = "gestor_central"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Chave estrangeira que define a qual negócio este usuário pertence.
    # index=True porque esta coluna é usada em praticamente todo filtro
    # multiempresa (ver regra de isolamento na especificação, seção 3).
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocios.id"), nullable=False, index=True)

    # Regra de integridade entre tipo_usuario, loja_id e central_producao_id:
    #   operador_loja  -> loja_id obrigatório, central_producao_id nulo
    #   gestor_central -> central_producao_id obrigatório, loja_id nulo
    # Verificada na camada de serviço; um check constraint de banco é
    # adicionado na migração 0009 para garantia adicional.
    tipo_usuario: Mapped[TipoUsuario] = mapped_column(
        Enum(TipoUsuario, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=TipoUsuario.OPERADOR_LOJA,
        nullable=False,
    )

    # Nullable: preenchido apenas quando tipo_usuario = operador_loja.
    loja_id = mapped_column(ForeignKey("lojas.id"), nullable=True, index=True)

    # Nullable: preenchido apenas quando tipo_usuario = gestor_central.
    central_producao_id = mapped_column(ForeignKey("centrais_producao.id"), nullable=True, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    # E-mail é o identificador de login. Único em toda a base (não só por negócio),
    # pois é usado diretamente no formulário de login sem informar o negócio.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # values_callable força o SQLAlchemy a usar os VALORES do enum Python
    # ("ativo", "bloqueado") em vez dos NOMES ("ATIVO", "BLOQUEADO") ao
    # montar o SQL — sem isso, o INSERT falha contra o tipo enum criado no
    # PostgreSQL (que usa os valores em minúsculo).
    status: Mapped[StatusUsuario] = mapped_column(
        Enum(StatusUsuario, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=StatusUsuario.ATIVO,
        nullable=False,
    )

    # Define se este usuário pode autenticar no app móvel.
    tem_acesso_app: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Define se este usuário pode autenticar no SaaS web (migration 0014).
    # server_default igual ao da migration: usuários existentes ficam sem acesso.
    tem_acesso_web: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    negocio = relationship("Negocio", back_populates="usuarios")
    loja = relationship("Loja", back_populates="usuarios")
    central_producao = relationship("CentralProducao", back_populates="usuarios")
