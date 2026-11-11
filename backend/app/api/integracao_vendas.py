"""
Integração de vendas (D108). Routers finos sobre `sync_vendas_service`.

Sistema do cliente (sem usuário; o negócio vem da CHAVE, nunca do corpo):
- POST /integracao/vendas   cabeçalho X-Chave-Frescor; corpo {"vendas": [...]}

SaaS web (gestor):
- GET  /web/integracao/vendas                    estado, últimas execuções e pendências
- POST /web/integracao/vendas/buscar             "Buscar agora" (só no modo busca)
- POST /web/integracao/vendas/pendencias/casar   diz qual produto é um código do sistema de vendas

A configuração (modo, endereço, chave) é feita na implantação, por
`scripts/configurar_integracao_vendas.py`: chave e credencial não passam
pela tela.
"""

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central
from app.db.session import get_db
from app.models.execucao_sync_vendas import ExecucaoSyncVendas, OrigemExecucaoSync
from app.models.integracao_vendas import IntegracaoVendas, ModoIntegracaoVendas
from app.models.loja import Loja
from app.models.pendencia_sync_vendas import MotivoPendenciaSync, PendenciaSyncVendas
from app.services import sync_vendas_service as svc
from app.services.escopo_service import ids_lojas_do_gestor

router = APIRouter()
MAX_DIAS_BUSCA = 31


class ExecucaoResponse(BaseModel):
    id: int
    origem: str
    situacao: str
    data_inicio: date | None
    data_fim: date | None
    iniciada_em: datetime
    terminada_em: datetime | None
    linhas_recebidas: int
    linhas_gravadas: int
    linhas_pendentes: int
    linhas_invalidas: int
    mensagem: str | None


class PendenciaResponse(BaseModel):
    motivo: str
    codigo: str  # código do produto (produto desconhecido) ou da loja (loja desconhecida)
    linhas: int
    primeira_data: date
    ultima_data: date
    lojas: list[str]


class IntegracaoResponse(BaseModel):
    configurada: bool
    modo: str | None = None
    ativa: bool | None = None
    sistema: str | None = None
    horario_busca: time | None = None
    dias_rebusca: int | None = None
    chave_prefixo: str | None = None
    execucoes: list[ExecucaoResponse] = []
    pendencias: list[PendenciaResponse] = []


class BuscarAgora(BaseModel):
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None


class CasarProduto(BaseModel):
    codigo_produto: str = Field(min_length=1, max_length=60)
    produto_id: int


class CasarResponse(BaseModel):
    gravadas: int
    pendentes: int
    invalidas: list[str]


def _execucao(ex: ExecucaoSyncVendas) -> ExecucaoResponse:
    return ExecucaoResponse(
        id=ex.id, origem=ex.origem.value, situacao=ex.situacao.value, data_inicio=ex.data_inicio,
        data_fim=ex.data_fim, iniciada_em=ex.iniciada_em, terminada_em=ex.terminada_em,
        linhas_recebidas=ex.linhas_recebidas, linhas_gravadas=ex.linhas_gravadas,
        linhas_pendentes=ex.linhas_pendentes, linhas_invalidas=ex.linhas_invalidas, mensagem=ex.mensagem,
    )


# ------------------------------------------------------------------ sistema do cliente

@router.post("/integracao/vendas", response_model=ExecucaoResponse, tags=["Integração de vendas (sistema do cliente)"])
def receber(
    corpo: dict = Body(..., examples=[{"vendas": [{"data": "2026-11-10", "loja": "001", "produto": "7891234",
                                                   "quantidade": "12.5"}]}]),
    x_chave_frescor: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Recebe a venda diária por loja e produto. O negócio vem da chave."""
    try:
        integ = svc.integracao_pela_chave(db, x_chave_frescor)
    except svc.ChaveInvalida as erro:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(erro)) from erro
    if integ.modo != ModoIntegracaoVendas.ENVIO:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Esta integração está no modo busca: o Frescor busca as vendas.")
    try:
        ex = svc.receber_envio(db, integ, corpo.get("vendas") if isinstance(corpo, dict) else None)
    except svc.EnvioInvalido as erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
    return _execucao(ex)


# ------------------------------------------------------------------ SaaS

def _pendencias(db: Session, gestor: GestorCentralAutenticado) -> list[PendenciaResponse]:
    """
    Produto desconhecido: só as linhas das lojas do gestor. Loja desconhecida:
    todas (não se sabe de que central é).
    """
    codigos_lojas = [c for (c,) in db.query(Loja.codigo).filter(Loja.id.in_(ids_lojas_do_gestor(db, gestor)),
                                                                  Loja.codigo.isnot(None))]
    saida = []
    for motivo, coluna in ((MotivoPendenciaSync.PRODUTO_DESCONHECIDO, PendenciaSyncVendas.codigo_produto),
                           (MotivoPendenciaSync.LOJA_DESCONHECIDA, PendenciaSyncVendas.codigo_loja)):
        q = db.query(coluna, func.count(), func.min(PendenciaSyncVendas.data), func.max(PendenciaSyncVendas.data),
                     func.array_agg(func.distinct(PendenciaSyncVendas.codigo_loja))).filter(
            PendenciaSyncVendas.negocio_id == gestor.negocio_id, PendenciaSyncVendas.motivo == motivo)
        if motivo == MotivoPendenciaSync.PRODUTO_DESCONHECIDO:
            q = q.filter(PendenciaSyncVendas.codigo_loja.in_(codigos_lojas or [""]))
        for codigo, linhas, primeira, ultima, lojas in q.group_by(coluna).order_by(func.count().desc(), coluna):
            saida.append(PendenciaResponse(motivo=motivo.value, codigo=codigo, linhas=linhas, primeira_data=primeira,
                                           ultima_data=ultima, lojas=sorted(lojas or [])))
    return saida


@router.get("/web/integracao/vendas", response_model=IntegracaoResponse, tags=["Integração de vendas (SaaS web)"])
def estado(db: Session = Depends(get_db), gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    integ = db.query(IntegracaoVendas).filter(IntegracaoVendas.negocio_id == gestor.negocio_id).first()
    if integ is None:
        return IntegracaoResponse(configurada=False, pendencias=_pendencias(db, gestor))
    execucoes = (db.query(ExecucaoSyncVendas).filter(ExecucaoSyncVendas.negocio_id == gestor.negocio_id)
                 .order_by(ExecucaoSyncVendas.iniciada_em.desc(), ExecucaoSyncVendas.id.desc()).limit(20).all())
    return IntegracaoResponse(
        configurada=True, modo=integ.modo.value, ativa=integ.ativa, sistema=integ.sistema,
        horario_busca=integ.horario_busca if integ.modo == ModoIntegracaoVendas.BUSCA else None,
        dias_rebusca=integ.dias_rebusca if integ.modo == ModoIntegracaoVendas.BUSCA else None,
        chave_prefixo=integ.chave_prefixo if integ.modo == ModoIntegracaoVendas.ENVIO else None,
        execucoes=[_execucao(e) for e in execucoes], pendencias=_pendencias(db, gestor),
    )


@router.post("/web/integracao/vendas/buscar", response_model=ExecucaoResponse,
             tags=["Integração de vendas (SaaS web)"])
def buscar_agora(corpo: BuscarAgora, db: Session = Depends(get_db),
                 gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    integ = db.query(IntegracaoVendas).filter(IntegracaoVendas.negocio_id == gestor.negocio_id).first()
    hoje = svc.hoje_local()
    if integ is not None:
        padrao_inicio, padrao_fim = svc.periodo_padrao(integ, hoje)
    else:
        padrao_inicio = padrao_fim = hoje - timedelta(days=1)
    inicio, fim = corpo.data_inicio or padrao_inicio, corpo.data_fim or padrao_fim
    if fim < inicio:
        raise HTTPException(status_code=422, detail="A data final não pode ser antes da inicial.")
    if fim > hoje:
        raise HTTPException(status_code=422, detail="Não dá para buscar venda de um dia que ainda não chegou.")
    if (fim - inicio).days + 1 > MAX_DIAS_BUSCA:
        raise HTTPException(status_code=422, detail=f"Busque até {MAX_DIAS_BUSCA} dias de cada vez.")
    try:
        ex = svc.buscar(db, gestor.negocio_id, inicio, fim, OrigemExecucaoSync.MANUAL, usuario_id=gestor.usuario_id)
    except svc.IntegracaoNaoConfigurada as erro:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro
    return _execucao(ex)


@router.post("/web/integracao/vendas/pendencias/casar", response_model=CasarResponse,
             tags=["Integração de vendas (SaaS web)"])
def casar(corpo: CasarProduto, db: Session = Depends(get_db),
          gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    try:
        r = svc.casar_produto(db, gestor.negocio_id, corpo.codigo_produto, corpo.produto_id)
    except svc.CasamentoInvalido as erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
    return CasarResponse(gravadas=r.gravadas, pendentes=r.pendentes, invalidas=r.invalidas[:20])
