"""
Integração de vendas com o sistema do cliente (D108). Substitui o stub da
Fase 2 (P7).

Por que existe: a venda diária por produto passa a chegar sozinha, sem CSV
no dia a dia (D107). O sistema do cliente ainda não foi definido, então o
conector é genérico (ver `models/integracao_vendas.py`):
- `envio`: o sistema do cliente manda as vendas (POST /integracao/vendas,
  com a chave do negócio);
- `busca`: o Frescor busca de madrugada a venda de ontem e rebusca os dias
  anteriores (o PDV corrige vendas depois).
Quando a documentação do sistema real chegar, entra um adaptador que
converte a resposta dele para `LinhaRecebida`; o resto não muda.

Formato do Frescor (envio e busca), uma linha por loja + produto + dia:
    {"data": "2026-11-10", "loja": "001", "produto": "7891234", "quantidade": "12.5"}
`loja` = `lojas.codigo`; `produto` = `produtos.codigo_pdv` ou, sem ele, o
`codigo`. Quantidade com ponto decimal (texto ou número).

Regras ao gravar (as mesmas da importação de CSV, D12/D13, onde cabem):
- linhas repetidas da mesma loja + produto + dia SOMAM (o PDV pode mandar
  uma linha por caixa);
- grava em `vendas_diarias` com origem `api`, substituindo o valor anterior
  da mesma origem (D5); a linha `api` vence a `manual` na leitura (D16);
- inválidas (data futura ou malformada, quantidade negativa, fração em
  produto UN, mais de 3 casas, loja inativa) não gravam e são contadas;
- loja ou produto desconhecido NÃO trava o resto: a linha vai para
  `pendencias_sync_vendas`, e é gravada quando o gestor diz qual produto é
  aquele código (`casar_produto`).
- O que o sistema não mandou não é apagado (uma resposta parcial não pode
  zerar a venda). Venda corrigida para zero tem de vir como 0.

`negocio_id` vem sempre da integração (chave do envio, job interno) ou do
gestor autenticado; nunca do corpo da requisição (regra de ouro 1).
"""

import hashlib
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.execucao_sync_vendas import ExecucaoSyncVendas, OrigemExecucaoSync, SituacaoExecucaoSync
from app.models.integracao_vendas import IntegracaoVendas, ModoIntegracaoVendas
from app.models.loja import Loja
from app.models.pendencia_sync_vendas import MotivoPendenciaSync, PendenciaSyncVendas
from app.models.produto import Produto, UnidadeMedida
from app.models.venda_diaria import OrigemVenda, VendaDiaria

FUSO = "America/Sao_Paulo"
MAX_LINHAS_POR_ENVIO = 50_000
CASAS_DECIMAIS = 3
TIMEOUT_BUSCA_S = 60
PREFIXO_CHAVE = "frv_"
_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class IntegracaoNaoConfigurada(Exception):
    pass


class ChaveInvalida(Exception):
    pass


class EnvioInvalido(Exception):
    pass


class CasamentoInvalido(Exception):
    pass


@dataclass(frozen=True)
class LinhaRecebida:
    data: date
    codigo_loja: str
    codigo_produto: str
    quantidade: Decimal


@dataclass
class Leitura:
    linhas: list[LinhaRecebida] = field(default_factory=list)
    invalidas: list[str] = field(default_factory=list)


def agora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoje_local(agora: datetime | None = None) -> date:
    agora = agora or agora_utc()
    return agora.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(FUSO)).date()


# ------------------------------------------------------------------ chave

def gerar_chave() -> tuple[str, str, str]:
    """Nova chave de envio: (chave para mostrar UMA vez, hash para guardar, prefixo para reconhecer)."""
    chave = PREFIXO_CHAVE + secrets.token_urlsafe(32)
    return chave, hash_chave(chave), chave[:12]


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def integracao_pela_chave(db: Session, chave: str | None) -> IntegracaoVendas:
    if not chave:
        raise ChaveInvalida("Informe a chave da integração no cabeçalho X-Chave-Frescor.")
    integ = db.query(IntegracaoVendas).filter(IntegracaoVendas.chave_hash == hash_chave(chave.strip())).first()
    if integ is None or not integ.ativa:
        raise ChaveInvalida("Chave da integração inválida ou desativada.")
    return integ


# ------------------------------------------------------------------ leitura

def _quantidade(valor) -> Decimal:
    if isinstance(valor, bool) or valor is None:
        raise ValueError("quantidade vazia")
    try:
        q = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ValueError(f"quantidade inválida '{valor}'") from None
    if not q.is_finite():
        raise ValueError(f"quantidade inválida '{valor}'")
    if q < 0:
        raise ValueError(f"quantidade negativa '{valor}'")
    if q != q.quantize(Decimal(1).scaleb(-CASAS_DECIMAIS)):
        raise ValueError(f"quantidade '{valor}' com mais de {CASAS_DECIMAIS} casas decimais")
    return q


def ler_linhas(itens) -> Leitura:
    """Lista de dicionários no formato do Frescor -> linhas válidas + descrição das inválidas."""
    leitura = Leitura()
    if not isinstance(itens, list):
        raise EnvioInvalido("Mande uma lista de vendas.")
    if len(itens) > MAX_LINHAS_POR_ENVIO:
        raise EnvioInvalido(f"No máximo {MAX_LINHAS_POR_ENVIO} linhas por envio. Divida em partes.")
    for n, item in enumerate(itens, start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("linha não é um objeto")
            texto_data = str(item.get("data", "")).strip()
            if not _RE_DATA.match(texto_data):
                raise ValueError(f"data inválida '{texto_data}' (use AAAA-MM-DD)")
            dia = date.fromisoformat(texto_data)
            loja = str(item.get("loja", "") or "").strip()
            produto = str(item.get("produto", "") or "").strip()
            if not loja or not produto:
                raise ValueError("loja ou produto vazio")
            if len(loja) > 60 or len(produto) > 60:
                raise ValueError("código de loja ou produto com mais de 60 caracteres")
            leitura.linhas.append(LinhaRecebida(dia, loja, produto, _quantidade(item.get("quantidade"))))
        except ValueError as erro:
            leitura.invalidas.append(f"linha {n}: {erro}")
    return leitura


# ------------------------------------------------------------------ gravação

@dataclass
class Aplicacao:
    gravadas: int = 0
    pendentes: int = 0
    invalidas: list[str] = field(default_factory=list)


def _mapas(db: Session, negocio_id: int):
    lojas = {lj.codigo: lj for lj in db.query(Loja).filter(Loja.negocio_id == negocio_id, Loja.codigo.isnot(None))}
    produtos: dict[str, Produto] = {}
    todos = db.query(Produto).filter(Produto.negocio_id == negocio_id).all()
    # O `codigo` vale quando nenhum produto usa aquele texto como código no PDV.
    for p in todos:
        if p.codigo:
            produtos.setdefault(p.codigo, p)
    for p in todos:
        if p.codigo_pdv:
            produtos[p.codigo_pdv] = p
    return lojas, produtos


def aplicar(db: Session, negocio_id: int, linhas: list[LinhaRecebida], execucao_id: int | None,
            hoje: date | None = None) -> Aplicacao:
    """Grava as linhas (sem commit). Pendências guardadas; inválidas contadas."""
    hoje = hoje or hoje_local()
    lojas, produtos = _mapas(db, negocio_id)
    resultado = Aplicacao()
    somas: dict[tuple[int, int, date], Decimal] = defaultdict(Decimal)
    resolvidas: set[tuple[date, str, str]] = set()
    pendentes: dict[tuple[date, str, str], list] = {}

    for linha in linhas:
        chave = (linha.data, linha.codigo_loja, linha.codigo_produto)
        if linha.data > hoje:
            resultado.invalidas.append(f"{linha.data} loja {linha.codigo_loja} produto {linha.codigo_produto}: data futura")
            continue
        loja = lojas.get(linha.codigo_loja)
        produto = produtos.get(linha.codigo_produto)
        if loja is None or produto is None:
            motivo = MotivoPendenciaSync.LOJA_DESCONHECIDA if loja is None else MotivoPendenciaSync.PRODUTO_DESCONHECIDO
            atual = pendentes.get(chave)
            pendentes[chave] = [motivo, (atual[1] if atual else Decimal(0)) + linha.quantidade]
            continue
        if not loja.ativo:
            resultado.invalidas.append(f"{linha.data} loja {linha.codigo_loja}: loja inativa")
            continue
        if produto.unidade_medida == UnidadeMedida.UN and linha.quantidade != linha.quantidade.to_integral_value():
            resultado.invalidas.append(
                f"{linha.data} produto {linha.codigo_produto}: contado por unidade, quantidade {linha.quantidade} não é inteira")
            continue
        somas[(loja.id, produto.id, linha.data)] += linha.quantidade
        resolvidas.add(chave)

    if somas:
        valores = [dict(negocio_id=negocio_id, loja_id=lj, produto_id=pr, data=d, quantidade=q, origem=OrigemVenda.API)
                   for (lj, pr, d), q in somas.items()]
        for i in range(0, len(valores), 1000):
            stmt = pg_insert(VendaDiaria).values(valores[i:i + 1000])
            stmt = stmt.on_conflict_do_update(constraint="uq_venda_loja_produto_data_origem",
                                              set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()})
            db.execute(stmt)
        resultado.gravadas = len(somas)

    # Linha que casou agora deixa de ser pendência.
    for d, cl, cp in resolvidas:
        db.query(PendenciaSyncVendas).filter(
            PendenciaSyncVendas.negocio_id == negocio_id, PendenciaSyncVendas.data == d,
            PendenciaSyncVendas.codigo_loja == cl, PendenciaSyncVendas.codigo_produto == cp,
        ).delete(synchronize_session=False)

    if pendentes:
        valores = [dict(negocio_id=negocio_id, motivo=m, data=d, codigo_loja=cl, codigo_produto=cp, quantidade=q,
                        execucao_id=execucao_id) for (d, cl, cp), (m, q) in pendentes.items()]
        stmt = pg_insert(PendenciaSyncVendas).values(valores)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_pendencia_sync_negocio_data_loja_produto",
            set_={"quantidade": stmt.excluded.quantidade, "motivo": stmt.excluded.motivo,
                  "execucao_id": stmt.excluded.execucao_id, "atualizada_em": func.now()},
        )
        db.execute(stmt)
        resultado.pendentes = len(pendentes)
    return resultado


def _nova_execucao(db, negocio_id, origem, inicio=None, fim=None, usuario_id=None) -> ExecucaoSyncVendas:
    ex = ExecucaoSyncVendas(negocio_id=negocio_id, origem=origem, situacao=SituacaoExecucaoSync.FALHOU,
                            data_inicio=inicio, data_fim=fim, iniciada_em=agora_utc(),
                            iniciada_por_usuario_id=usuario_id)
    db.add(ex)
    db.flush()
    return ex


def _fechar(ex: ExecucaoSyncVendas, recebidas: int, aplicacao: Aplicacao, invalidas_leitura: list[str]) -> None:
    invalidas = invalidas_leitura + aplicacao.invalidas
    ex.linhas_recebidas = recebidas
    ex.linhas_gravadas = aplicacao.gravadas
    ex.linhas_pendentes = aplicacao.pendentes
    ex.linhas_invalidas = len(invalidas)
    ex.situacao = SituacaoExecucaoSync.PARCIAL if (invalidas or aplicacao.pendentes) else SituacaoExecucaoSync.SUCESSO
    ex.mensagem = ("; ".join(invalidas[:5]) + (" …" if len(invalidas) > 5 else ""))[:500] if invalidas else None
    ex.terminada_em = agora_utc()


def receber_envio(db: Session, integ: IntegracaoVendas, itens, hoje: date | None = None) -> ExecucaoSyncVendas:
    """Envio (push) do sistema do cliente. Commita e devolve a execução."""
    leitura = ler_linhas(itens)
    datas = [l.data for l in leitura.linhas]
    ex = _nova_execucao(db, integ.negocio_id, OrigemExecucaoSync.ENVIO, min(datas, default=None),
                        max(datas, default=None))
    aplicacao = aplicar(db, integ.negocio_id, leitura.linhas, ex.id, hoje)
    _fechar(ex, len(itens), aplicacao, leitura.invalidas)
    db.commit()
    return ex


# ------------------------------------------------------------------ busca

Buscador = Callable[[str, dict[str, str], date, date], object]


def buscar_http(url: str, cabecalhos: dict[str, str], inicio: date, fim: date):
    """GET {url}?data_inicio=&data_fim= ; resposta JSON: lista ou {"vendas": [...]}."""
    separador = "&" if urllib.parse.urlparse(url).query else "?"
    endereco = f"{url}{separador}{urllib.parse.urlencode({'data_inicio': inicio.isoformat(), 'data_fim': fim.isoformat()})}"
    pedido = urllib.request.Request(endereco, headers={"Accept": "application/json", **cabecalhos})
    with urllib.request.urlopen(pedido, timeout=TIMEOUT_BUSCA_S) as resposta:  # noqa: S310 (URL vem da configuração)
        return json.loads(resposta.read().decode("utf-8"))


def buscar(db: Session, negocio_id: int, inicio: date, fim: date, origem: OrigemExecucaoSync,
           usuario_id: int | None = None, buscador: Buscador | None = None,
           hoje: date | None = None) -> ExecucaoSyncVendas:
    """Busca (pull) no sistema do cliente. Falha vira execução `falhou` com a mensagem, nunca exceção."""
    integ = db.query(IntegracaoVendas).filter(IntegracaoVendas.negocio_id == negocio_id).first()
    if integ is None or not integ.ativa or integ.modo != ModoIntegracaoVendas.BUSCA:
        raise IntegracaoNaoConfigurada(
            "A busca automática não está configurada para este negócio. "
            "Se o sistema de vendas envia os dados, eles chegam sozinhos.")
    ex = _nova_execucao(db, negocio_id, origem, inicio, fim, usuario_id)
    db.commit()
    try:
        cabecalhos = {}
        if integ.variavel_credencial:
            credencial = os.environ.get(integ.variavel_credencial)
            if not credencial:
                raise RuntimeError(f"credencial ausente no servidor (variável {integ.variavel_credencial})")
            cabecalhos["Authorization"] = f"Bearer {credencial}"
        corpo = (buscador or buscar_http)(integ.url_busca, cabecalhos, inicio, fim)
        itens = corpo.get("vendas") if isinstance(corpo, dict) else corpo
        leitura = ler_linhas(itens)
        fora = [l for l in leitura.linhas if not inicio <= l.data <= fim]
        linhas = [l for l in leitura.linhas if inicio <= l.data <= fim]
        aplicacao = aplicar(db, negocio_id, linhas, ex.id, hoje)
        _fechar(ex, len(itens), aplicacao,
                leitura.invalidas + [f"{l.data}: fora do período pedido" for l in fora])
    except Exception as erro:  # noqa: BLE001 - qualquer falha da busca vira registro, não derruba o job
        db.rollback()
        ex = db.get(ExecucaoSyncVendas, ex.id)
        ex.situacao = SituacaoExecucaoSync.FALHOU
        ex.mensagem = f"Falha na busca: {erro}"[:500]
        ex.terminada_em = agora_utc()
    db.commit()
    return ex


def periodo_padrao(integ: IntegracaoVendas, hoje: date) -> tuple[date, date]:
    """Ontem e os `dias_rebusca` anteriores."""
    fim = hoje - timedelta(days=1)
    return fim - timedelta(days=integ.dias_rebusca), fim


def executar_agendadas(db: Session, agora: datetime | None = None,
                       buscador: Buscador | None = None) -> list[ExecucaoSyncVendas]:
    """Job: busca dos negócios cujo horário já passou hoje e que ainda não tiveram busca agendada hoje."""
    agora = agora or agora_utc()
    local = agora.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(FUSO))
    inicio_dia_utc = datetime.combine(local.date(), datetime.min.time(), ZoneInfo(FUSO)).astimezone(
        timezone.utc).replace(tzinfo=None)
    feitas = []
    integracoes = db.query(IntegracaoVendas).filter(IntegracaoVendas.ativa.is_(True),
                                                   IntegracaoVendas.modo == ModoIntegracaoVendas.BUSCA).all()
    for integ in integracoes:
        if local.time() < integ.horario_busca:
            continue
        ja = db.query(ExecucaoSyncVendas.id).filter(
            ExecucaoSyncVendas.negocio_id == integ.negocio_id,
            ExecucaoSyncVendas.origem == OrigemExecucaoSync.AGENDADA,
            ExecucaoSyncVendas.iniciada_em >= inicio_dia_utc,
        ).first()
        if ja:
            continue
        inicio, fim = periodo_padrao(integ, local.date())
        feitas.append(buscar(db, integ.negocio_id, inicio, fim, OrigemExecucaoSync.AGENDADA, buscador=buscador,
                             hoje=local.date()))
    return feitas


# ------------------------------------------------------------------ pendências

def casar_produto(db: Session, negocio_id: int, codigo_produto: str, produto_id: int,
                  hoje: date | None = None) -> Aplicacao:
    """
    O gestor diz que `codigo_produto` (código no sistema de vendas) é o
    produto `produto_id`: grava o `codigo_pdv` e aplica na hora as linhas
    pendentes daquele código. Commita.
    """
    codigo_produto = codigo_produto.strip()
    produto = db.query(Produto).filter(Produto.negocio_id == negocio_id, Produto.id == produto_id).first()
    if produto is None:
        raise CasamentoInvalido("Produto não encontrado.")
    outro = db.query(Produto).filter(Produto.negocio_id == negocio_id, Produto.codigo_pdv == codigo_produto,
                                     Produto.id != produto.id).first()
    if outro is not None:
        raise CasamentoInvalido(f"O código {codigo_produto} já é do produto {outro.nome}.")
    if produto.codigo_pdv and produto.codigo_pdv != codigo_produto:
        raise CasamentoInvalido(
            f"{produto.nome} já está ligado ao código {produto.codigo_pdv} do sistema de vendas. "
            "Um produto tem um código só; confira se é mesmo este produto.")
    pendencias = db.query(PendenciaSyncVendas).filter(
        PendenciaSyncVendas.negocio_id == negocio_id, PendenciaSyncVendas.codigo_produto == codigo_produto).all()
    if not pendencias:
        raise CasamentoInvalido("Não há venda pendente com este código.")
    produto.codigo_pdv = codigo_produto
    db.flush()
    linhas = [LinhaRecebida(p.data, p.codigo_loja, p.codigo_produto, Decimal(p.quantidade)) for p in pendencias]
    resultado = aplicar(db, negocio_id, linhas, None, hoje)
    # O que ainda está como "produto desconhecido" deste código foi recusado
    # agora (ex.: fração em produto UN): não volta a pendência, sai da lista.
    db.query(PendenciaSyncVendas).filter(
        PendenciaSyncVendas.negocio_id == negocio_id, PendenciaSyncVendas.codigo_produto == codigo_produto,
        PendenciaSyncVendas.motivo == MotivoPendenciaSync.PRODUTO_DESCONHECIDO,
    ).delete(synchronize_session=False)
    db.commit()
    return resultado
