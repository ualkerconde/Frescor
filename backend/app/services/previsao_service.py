"""
Motor de previsão de venda (Fase 3): junta a série diária (F1), o núcleo
de cálculo (F2), os eventos (F3) e o cold start (F4) para todas as lojas
de uma central.

Por que por central, e não por loja: é a unidade de trabalho do gestor
(a ordem de produção da Fase 4 é da central), e o proxy de loja nova
precisa da previsão das outras lojas da mesma central.

Ordem do cálculo para cada loja + produto:
1. série de vendas efetivas (D16/D17), só produto ativo e habilitado;
   dias antes do início do histórico do produto na loja viram faltantes
   (os zeros da D17 de antes do lançamento não são venda zero). Início do
   histórico (D28): primeira linha de venda; se o produto nunca vendeu,
   a habilitação na loja;
2. dias de evento do produto ficam fora da base e da tendência;
3. previsão própria = base × tendência (D18/D19), sem arredondar (D21);
4. cold start (doc §4.2, D20): com menos de 6 semanas de histórico,
   previsão = peso × própria + (1 − peso) × proxy;
5. ajuste do evento que cobre o dia previsto (proposta D26).

Proxy (D20), calculado com as previsões próprias de quem já tem histórico
completo (peso 1), sem evento:
- loja nova (menos de 6 semanas de vendas na loja): média do mesmo
  produto nas outras lojas da central;
- produto novo (ou loja nova sem o produto em outra loja): média dos
  produtos da mesma categoria e unidade na loja. Categoria = valor do 1º
  nível da classificação. Produto sem 1º nível, ou sem nenhum par na
  categoria: média dos produtos da mesma unidade na loja.

Só lojas ativas recebem previsão (loja inativa não importa vendas, D12).
`negocio_id` e `central_producao_id` vêm do gestor autenticado.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.loja import Loja
from app.models.nivel_classificacao import NivelClassificacao
from app.models.produto import Produto, UnidadeMedida
from app.models.produto_classificacao import ProdutoClassificacao
from app.services.eventos_service import eventos_das_lojas
from app.services.previsao_calculo import (
    DIAS_HISTORICO_NECESSARIOS,
    ComponentesPrevisao,
    EventoAplicavel,
    aplicar_eventos,
    combinar_cold_start,
    eventos_do_produto,
    peso_historico_proprio,
    prever,
)
from app.services.serie_vendas_service import datas_habilitacao, inicio_historico, series_da_loja

ORIGEM_PROXY_OUTRAS_LOJAS = "outras_lojas"
ORIGEM_PROXY_CATEGORIA = "categoria"
ORIGEM_PROXY_UNIDADE = "unidade"


@dataclass(frozen=True)
class PrevisaoProduto:
    loja_id: int
    produto_id: int
    data_alvo: date
    # Base, tendência e previsão própria (só com o histórico do produto na loja).
    componentes: ComponentesPrevisao
    # Onde começa o histórico próprio (D28): primeira linha de venda do
    # produto na loja ou, se nunca vendeu, a habilitação.
    inicio_historico: date | None
    # Peso da previsão própria: 0 a 1 (1 = histórico completo, sem cold start).
    peso_historico: Decimal
    proxy: Decimal | None
    origem_proxy: str | None
    # Previsão depois do cold start e antes do evento.
    previsao_sem_evento: Decimal | None
    # Eventos que mexeram no número do dia previsto.
    eventos: tuple[EventoAplicavel, ...]
    previsao: Decimal | None

    @property
    def previsao_propria(self) -> Decimal | None:
        return self.componentes.previsao


@dataclass
class _Parcial:
    loja_id: int
    produto_id: int
    componentes: ComponentesPrevisao
    inicio_historico: date | None
    peso: Decimal
    eventos: list[EventoAplicavel]


def lojas_ativas_da_central(db: Session, negocio_id: int, central_producao_id: int) -> list[int]:
    return [
        loja_id
        for (loja_id,) in db.query(Loja.id)
        .filter(
            Loja.negocio_id == negocio_id,
            Loja.central_producao_id == central_producao_id,
            Loja.ativo.is_(True),
        )
        .order_by(Loja.id)
    ]


def _unidades_e_categorias(
    db: Session, negocio_id: int, produto_ids: set[int]
) -> tuple[dict[int, UnidadeMedida], dict[int, str]]:
    if not produto_ids:
        return {}, {}
    unidades = {
        pid: unidade
        for pid, unidade in db.query(Produto.id, Produto.unidade_medida).filter(
            Produto.negocio_id == negocio_id, Produto.id.in_(produto_ids)
        )
    }
    categorias = {
        pid: valor
        for pid, valor in db.query(ProdutoClassificacao.produto_id, ProdutoClassificacao.valor)
        .join(NivelClassificacao, NivelClassificacao.id == ProdutoClassificacao.nivel_id)
        .filter(
            NivelClassificacao.negocio_id == negocio_id,
            NivelClassificacao.ordem == 1,
            ProdutoClassificacao.produto_id.in_(produto_ids),
        )
    }
    return unidades, categorias


def _media(valores: list[Decimal]) -> Decimal | None:
    return sum(valores, Decimal("0")) / len(valores) if valores else None


def prever_central(
    db: Session, negocio_id: int, central_producao_id: int, data_referencia: date, data_alvo: date
) -> list[PrevisaoProduto]:
    """
    Previsão de `data_alvo` para cada produto de cada loja ativa da central,
    com o que se sabe até `data_referencia` (normalmente ontem).
    """
    if data_alvo <= data_referencia:
        raise ValueError("A data prevista tem de ser depois da data de referência.")
    loja_ids = lojas_ativas_da_central(db, negocio_id, central_producao_id)
    inicio = data_referencia - timedelta(days=DIAS_HISTORICO_NECESSARIOS)
    eventos = eventos_das_lojas(db, negocio_id, loja_ids, inicio, data_alvo)

    # 1ª passada: previsão própria e peso de cada loja + produto.
    parciais: list[_Parcial] = []
    peso_loja: dict[int, Decimal] = {}
    for loja_id in loja_ids:
        series = series_da_loja(db, negocio_id, loja_id, inicio, data_referencia)
        inicio_loja, inicio_produtos = inicio_historico(db, negocio_id, loja_id, data_referencia)
        peso_loja[loja_id] = peso_historico_proprio(inicio_loja, data_referencia)
        habilitacao = datas_habilitacao(db, negocio_id, loja_id)
        for produto_id, serie in series.items():
            # D28: o histórico começa na primeira linha de venda; produto que
            # nunca vendeu começa na habilitação (o proxy perde peso em 6
            # semanas e depois vale o histórico próprio, zero).
            comeco = inicio_produtos.get(produto_id)
            if comeco is None:
                comeco = habilitacao.get(produto_id)
            propria_serie = {d: (v if comeco is not None and d >= comeco else None) for d, v in serie.items()}
            evs = eventos_do_produto(eventos[loja_id], produto_id)
            parciais.append(
                _Parcial(
                    loja_id=loja_id,
                    produto_id=produto_id,
                    componentes=prever(propria_serie, data_referencia, data_alvo, evs),
                    inicio_historico=comeco,
                    peso=peso_historico_proprio(comeco, data_referencia),
                    eventos=evs,
                )
            )

    # Quem já tem histórico completo e previsão própria serve de referência.
    estabelecidos = [p for p in parciais if p.peso >= 1 and p.componentes.previsao is not None]
    unidades, categorias = _unidades_e_categorias(db, negocio_id, {p.produto_id for p in parciais})

    def proxy(p: _Parcial) -> tuple[Decimal | None, str | None]:
        if peso_loja[p.loja_id] < 1:
            media = _media([e.componentes.previsao for e in estabelecidos
                            if e.produto_id == p.produto_id and e.loja_id != p.loja_id])
            if media is not None:
                return media, ORIGEM_PROXY_OUTRAS_LOJAS
        pares = [e for e in estabelecidos
                 if e.loja_id == p.loja_id and e.produto_id != p.produto_id
                 and unidades.get(e.produto_id) == unidades.get(p.produto_id)]
        categoria = categorias.get(p.produto_id)
        if categoria is not None:
            media = _media([e.componentes.previsao for e in pares if categorias.get(e.produto_id) == categoria])
            if media is not None:
                return media, ORIGEM_PROXY_CATEGORIA
        media = _media([e.componentes.previsao for e in pares])
        return (media, ORIGEM_PROXY_UNIDADE) if media is not None else (None, None)

    # 2ª passada: cold start e evento.
    resultado: list[PrevisaoProduto] = []
    for p in parciais:
        valor_proxy, origem = proxy(p) if p.peso < 1 else (None, None)
        sem_evento = combinar_cold_start(p.componentes.previsao, p.peso, valor_proxy)
        previsao, aplicados = aplicar_eventos(sem_evento, p.eventos, data_alvo)
        resultado.append(
            PrevisaoProduto(
                loja_id=p.loja_id,
                produto_id=p.produto_id,
                data_alvo=data_alvo,
                componentes=p.componentes,
                inicio_historico=p.inicio_historico,
                peso_historico=p.peso,
                proxy=valor_proxy,
                origem_proxy=origem,
                previsao_sem_evento=sem_evento,
                eventos=aplicados,
                previsao=previsao,
            )
        )
    return resultado
