"""Esquemas do lançamento de perda (D110)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LancarPerdaApp(BaseModel):
    """App: a loja vem do token."""

    produto_id: int
    quantidade: Decimal
    motivo: str
    observacao: str | None = None
    data: date | None = Field(default=None, description="Hoje (padrão) ou ontem.")


class LancarPerdaWeb(LancarPerdaApp):
    """SaaS: o gestor escolhe a loja (conferida contra a própria central) e o dia."""

    loja_id: int
    data: date


class AlterarPerda(BaseModel):
    quantidade: Decimal
    motivo: str
    observacao: str | None = None


class LancamentoPerdaResponse(BaseModel):
    id: int
    data: date
    loja: dict
    produto: dict
    unidade: str
    quantidade: Decimal
    motivo: str
    observacao: str | None
    lancado_por: str
    lancado_em: datetime
    alterado_por: str | None
    alterado_em: datetime | None
    loja_pode_alterar: bool
