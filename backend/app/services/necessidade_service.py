"""
Necessidade de todas as lojas + produtos de uma central para uma data de
produção (Fase 4 / N4). Lê do banco o que o cálculo puro
(`necessidade_calculo.py`, N3) precisa e devolve uma linha por loja +
produto, com os componentes e os avisos.

De onde vem cada entrada:
- previsão: a GRAVADA em `previsoes_diarias` (Fase 3), nunca recalculada
  aqui, para o número da ordem ser o mesmo que o gestor viu na tela de
  previsão e poder ser rastreado (versão do método gravada na previsão);
- calendário (`calendario_producao`), validade, margem, tipo de
  abastecimento e unidade, do produto;
- prazo de entrega, da central (D32); horário de fechamento, da loja (D44);
- contagem: `estoque_atual` (valor e hora do último lançamento do app);
- trânsito (D43): linhas de ordens aprovadas sem recebimento confirmado.
  As tabelas de ordem nascem no N5; por isso o trânsito chega por um
  provedor injetável (`ProvedorTransito`), ligado no N6. Sem provedor, não
  há trânsito.

Quais linhas entram (data de produção D):
- só lojas ATIVAS da central; produto ATIVO no catálogo e habilitado e
  ativo na loja (as mesmas regras de quem recebe previsão, Fase 3);
- produto com calendário entra só se D é dia de produção dele (os outros
  dias são de outra ordem); produto SEM calendário entra com o aviso
  "sem calendário" (D42) para o gestor ver e corrigir;
- produto fora da vigência em todos os dias da cobertura fica fora; dia da
  cobertura fora da vigência conta venda 0 (o produto não é vendido nesse
  dia), não "sem previsão".

Isolamento (regra de ouro 1): `negocio_id` e `central_producao_id` vêm do
gestor autenticado (a rota passa os dados de `obter_gestor_central`); toda
consulta filtra pelo negócio e pelas lojas da central.

Indicador de perda (D35): perda ÷ venda das 4 semanas até D−1, pelos
registros efetivos (D16). Só informa; não entra na conta.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.calendario_producao import CalendarioProducao, DiaSemana
from app.models.central_producao import CentralProducao
from app.models.estoque_atual import EstoqueAtual
from app.models.loja import Loja
from app.models.perda_diaria import PerdaDiaria
from app.models.previsao_diaria import PrevisaoDiaria
from app.models.produto import Produto
from app.models.produto_loja import ProdutoLoja
from app.models.venda_diaria import VendaDiaria
from app.services.necessidade_calculo import (
    FUSO_PADRAO,
    Contagem,
    EntradaNecessidade,
    LoteTransito,
    ResultadoNecessidade,
    calcular_cobertura,
    calcular_necessidade,
    produz_no_dia,
)
from app.services.previsao_calculo import vigente
from app.services.registros_efetivos import condicao_registro_efetivo

# Indicador de perda (D35): janela até D−1.
DIAS_INDICADOR_PERDA = 28
# A cobertura vai, no máximo, de D + prazo até 6 dias depois (calendário
# semanal: a próxima produção é no máximo 7 dias depois).
_DIAS_MAXIMOS_COBERTURA = 7
_DIA_SEMANA = {d: i for i, d in enumerate(DiaSemana)}  # segunda = 0 (date.weekday)

Par = tuple[int, int]  # (loja_id, produto_id)
ProvedorTransito = Callable[[Session, int, Sequence[int], date], Mapping[Par, Sequence[LoteTransito]]]


class CentralNaoEncontrada(LookupError):
    """Central inexistente ou de outro negócio."""


@dataclass(frozen=True)
class ItemNecessidade:
    loja_id: int
    loja_codigo: str | None
    loja_nome: str
    produto_id: int
    produto_codigo: str | None
    produto_nome: str
    unidade: str
    tipo_abastecimento: str
    # Algum dia da cobertura com previsão de pouco histórico (peso < 1, F4).
    pouco_historico: bool
    # Perda ÷ venda nas 4 semanas até D−1; None se não houve venda.
    taxa_perda: Decimal | None
    resultado: ResultadoNecessidade


@dataclass(frozen=True)
class NecessidadesCentral:
    data_producao: date
    prazo_entrega_dias: int
    itens: list[ItemNecessidade]
    # Data de referência mais antiga entre as previsões usadas (None = nenhuma).
    referencia_previsao: date | None
    # D41: previsão gerada com referência anterior a ontem (ou inexistente).
    previsao_desatualizada: bool


def _sem_transito(db: Session, negocio_id: int, lojas: Sequence[int], data_producao: date) -> dict:
    return {}


def _taxas_perda(db: Session, negocio_id: int, lojas: list[int], data_producao: date) -> dict[Par, Decimal | None]:
    inicio = data_producao - timedelta(days=DIAS_INDICADOR_PERDA)
    fim = data_producao - timedelta(days=1)
    somas: dict[Par, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for indice, modelo in enumerate((VendaDiaria, PerdaDiaria)):
        linhas = (
            db.query(modelo.loja_id, modelo.produto_id, func.sum(modelo.quantidade))
            .filter(
                modelo.negocio_id == negocio_id,
                modelo.loja_id.in_(lojas),
                modelo.data >= inicio,
                modelo.data <= fim,
                condicao_registro_efetivo(modelo),
            )
            .group_by(modelo.loja_id, modelo.produto_id)
        )
        for loja_id, produto_id, total in linhas:
            somas[(loja_id, produto_id)][indice] = Decimal(total)
    return {par: (perda / venda if venda > 0 else None) for par, (venda, perda) in somas.items()}


def calcular_necessidades(
    db: Session,
    negocio_id: int,
    central_producao_id: int,
    data_producao: date,
    hoje: date,
    provedor_transito: ProvedorTransito | None = None,
) -> NecessidadesCentral:
    central = (
        db.query(CentralProducao)
        .filter(CentralProducao.negocio_id == negocio_id, CentralProducao.id == central_producao_id)
        .one_or_none()
    )
    if central is None:
        raise CentralNaoEncontrada("Central de produção não encontrada.")
    prazo = central.prazo_entrega_dias

    lojas = {
        loja.id: loja
        for loja in db.query(Loja).filter(
            Loja.negocio_id == negocio_id, Loja.central_producao_id == central_producao_id, Loja.ativo.is_(True)
        )
    }
    if not lojas:
        return NecessidadesCentral(data_producao, prazo, [], None, True)
    ids_lojas = sorted(lojas)
    produtos = {
        p.id: p for p in db.query(Produto).filter(Produto.negocio_id == negocio_id, Produto.ativo.is_(True))
    }
    # ProdutoLoja não tem negocio_id: o negócio vem das lojas (já filtradas).
    pares = sorted(
        (loja_id, produto_id)
        for loja_id, produto_id in db.query(ProdutoLoja.loja_id, ProdutoLoja.produto_id).filter(
            ProdutoLoja.loja_id.in_(ids_lojas), ProdutoLoja.ativo.is_(True)
        )
        if produto_id in produtos
    )
    calendario: dict[int, set[int]] = defaultdict(set)
    for produto_id, dia_semana in db.query(CalendarioProducao.produto_id, CalendarioProducao.dia_semana).filter(
        CalendarioProducao.negocio_id == negocio_id
    ):
        calendario[produto_id].add(_DIA_SEMANA[dia_semana])

    fim_horizonte = data_producao + timedelta(days=prazo + _DIAS_MAXIMOS_COBERTURA - 1)
    previsoes: dict[Par, dict[date, PrevisaoDiaria]] = defaultdict(dict)
    for linha in db.query(PrevisaoDiaria).filter(
        PrevisaoDiaria.negocio_id == negocio_id,
        PrevisaoDiaria.loja_id.in_(ids_lojas),
        PrevisaoDiaria.data >= data_producao,
        PrevisaoDiaria.data <= fim_horizonte,
    ):
        previsoes[(linha.loja_id, linha.produto_id)][linha.data] = linha

    estoques = {
        (e.loja_id, e.produto_id): e
        for e in db.query(EstoqueAtual).filter(
            EstoqueAtual.negocio_id == negocio_id, EstoqueAtual.loja_id.in_(ids_lojas)
        )
    }
    taxas = _taxas_perda(db, negocio_id, ids_lojas, data_producao)
    transito = (provedor_transito or _sem_transito)(db, negocio_id, ids_lojas, data_producao)

    itens: list[ItemNecessidade] = []
    referencias: list[date] = []
    for loja_id, produto_id in pares:
        loja, produto = lojas[loja_id], produtos[produto_id]
        dias_producao = frozenset(calendario.get(produto_id, ()))

        def esta_vigente(dia: date, p: Produto = produto) -> bool:
            return vigente(dia, p.data_inicio_vigencia, p.data_fim_vigencia, p.vigencia_recorrente)

        if dias_producao:
            if not produz_no_dia(data_producao, dias_producao):
                continue
            cobertura = calcular_cobertura(data_producao, prazo, dias_producao, produto.dias_validade)
            dias_vigencia = cobertura.dias or (cobertura.chegada,)
            dias_usados = tuple(data_producao + timedelta(days=k) for k in range(prazo)) + cobertura.dias
        else:
            dias_vigencia = (data_producao,)
            dias_usados = ()
        if not any(esta_vigente(d) for d in dias_vigencia):
            continue

        linhas_par = previsoes.get((loja_id, produto_id), {})
        valores: dict[date, Decimal | None] = {}
        for dia in dias_usados:
            if not esta_vigente(dia):
                valores[dia] = Decimal(0)
            else:
                linha = linhas_par.get(dia)
                valores[dia] = Decimal(linha.previsao) if linha is not None and linha.previsao is not None else None
                if linha is not None:
                    referencias.append(linha.data_referencia)
        pouco_historico = any(
            linhas_par[d].peso_historico < 1 for d in dias_usados if d in linhas_par and esta_vigente(d)
        )
        estoque = estoques.get((loja_id, produto_id))
        contagem = (
            Contagem(quantidade=Decimal(estoque.estoque_atual_calculado), atualizado_em_utc=estoque.atualizado_em)
            if estoque is not None else None
        )
        resultado = calcular_necessidade(EntradaNecessidade(
            data_producao=data_producao,
            prazo_entrega_dias=prazo,
            dias_producao=dias_producao,
            dias_validade=produto.dias_validade,
            margem_produto=Decimal(produto.margem_maxima_percentual)
            if produto.margem_maxima_percentual is not None else None,
            unidade=produto.unidade_medida.value,
            previsoes=valores,
            pouco_historico=pouco_historico,
            contagem=contagem,
            transito=tuple(transito.get((loja_id, produto_id), ())),
            horario_fechamento=loja.horario_fechamento,
            fuso=FUSO_PADRAO,
        ))
        itens.append(ItemNecessidade(
            loja_id=loja_id, loja_codigo=loja.codigo, loja_nome=loja.nome,
            produto_id=produto_id, produto_codigo=produto.codigo, produto_nome=produto.nome,
            unidade=produto.unidade_medida.value, tipo_abastecimento=produto.tipo_abastecimento.value,
            pouco_historico=pouco_historico, taxa_perda=taxas.get((loja_id, produto_id)), resultado=resultado,
        ))

    itens.sort(key=lambda i: (i.loja_codigo or "", i.loja_id, i.produto_codigo or "", i.produto_id))
    referencia = min(referencias) if referencias else None
    desatualizada = referencia is None or referencia < hoje - timedelta(days=1)
    return NecessidadesCentral(data_producao, prazo, itens, referencia, desatualizada)
