"""
Lógica de negócio da rotina de zeragem diária, executada POR LOJA.

IMPORTANTE (ajustado após a separação rascunho/estoque real): a zeragem
afeta SOMENTE o rascunho de contagem (estoque_atual.quantidade_inventariada).
O valor real de estoque (estoque_atual.estoque_atual_calculado) NUNCA é
tocado por esta rotina — ele só muda quando há um novo lançamento (via
app/services/estoque_service.py), preservando o último valor real
conhecido mesmo enquanto o rascunho está zerado aguardando a próxima
contagem.

Fluxo, em uma única transação atômica por loja:
1. Copia o estado atual de estoque_atual (quantidade_inventariada E
   estoque_atual_calculado, ambos) para historico_contagens, com a
   data/hora de referência — preservando os dois valores no snapshot.
2. Zera APENAS quantidade_inventariada de todos os produtos daquela loja
   em estoque_atual. estoque_atual_calculado permanece como estava.

Controle de "já rodou hoje": antes de zerar, verificamos se já existe um
snapshot de historico_contagens para esta loja com data_referencia no dia
de hoje. Se já existir, pulamos — isso evita zerar duas vezes a mesma loja
no mesmo dia, mesmo que o agendador rode com mais frequência do que uma
vez por dia (ex.: verificação a cada minuto) ou que o processo seja
reiniciado.
"""

from datetime import datetime, time, timedelta
import logging

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.estoque_atual import EstoqueAtual
from app.models.historico_contagem import HistoricoContagem
from app.models.loja import Loja

logger = logging.getLogger("zeragem")


def ja_zerou_hoje(db: Session, loja_id: int, agora: datetime) -> bool:
    """
    Confirma se já existe um snapshot de historico_contagens para esta
    loja com data_referencia dentro do dia corrente (de 00:00 até agora).

    Usada tanto pela verificação automática do agendador quanto pelo
    endpoint manual de zeragem (app/api/zeragem.py), por isso é uma
    função pública do módulo (sem underscore).
    """
    inicio_do_dia = datetime.combine(agora.date(), time.min)
    existe = (
        db.query(HistoricoContagem.id)
        .filter(
            HistoricoContagem.loja_id == loja_id,
            HistoricoContagem.data_referencia >= inicio_do_dia,
        )
        .first()
    )
    return existe is not None


def zerar_loja(db: Session, loja: Loja, agora: datetime) -> int:
    """
    Executa a zeragem de uma única loja: snapshot para histórico (com os
    dois valores, rascunho e calculado), depois zera SOMENTE o rascunho
    (quantidade_inventariada) em estoque_atual. O valor real
    (estoque_atual_calculado) permanece intocado. Retorna a quantidade de
    produtos processados.

    Mesmo que uma loja não tenha nenhum produto com estoque lançado ainda
    (estoque_atual vazio para ela), a função roda normalmente e retorna 0
    — a checagem de "já rodou hoje" (ja_zerou_hoje) depende da existência
    de QUALQUER snapshot no histórico para o dia, então uma loja sem
    nenhum item de estoque nunca vai gerar um snapshot e, por isso, a
    verificação "já zerou hoje" sempre retornará False para ela. Isso é
    um comportamento aceitável: uma loja sem nenhum produto contado ainda
    não tem o que zerar de fato.
    """
    itens_estoque = db.query(EstoqueAtual).filter(EstoqueAtual.loja_id == loja.id).all()

    for item in itens_estoque:
        db.add(
            HistoricoContagem(
                produto_id=item.produto_id,
                loja_id=item.loja_id,
                negocio_id=item.negocio_id,
                quantidade_inventariada=item.quantidade_inventariada,
                estoque_atual_calculado=item.estoque_atual_calculado,
                peso_informado_kg=item.peso_informado_kg,
                data_referencia=agora,
            )
        )
        # Zera APENAS o rascunho. estoque_atual_calculado NÃO é alterado
        # aqui — ele continua representando o último valor real conhecido
        # até que uma nova contagem seja lançada.
        item.quantidade_inventariada = 0

    db.commit()
    return len(itens_estoque)


def executar_zeragem_lojas_pendentes(janela_tolerancia_minutos: int = 5) -> list[dict]:
    """
    Ponto de entrada chamado pelo agendador (ver app/core/scheduler.py).

    Verifica TODAS as lojas ativas e, para cada uma cujo horario_zeragem
    já tenha passado no dia de hoje (dentro de uma janela de tolerância,
    para não depender de o agendador rodar no segundo exato) e que ainda
    não tenha sido zerada hoje, executa a zeragem.

    `janela_tolerancia_minutos` existe porque o agendador roda em
    intervalos discretos (ex.: a cada 1 minuto); sem essa janela, uma
    pequena diferença de horário poderia fazer a loja nunca ser
    encontrada "exatamente" no horário configurado.

    Retorna uma lista de resultados (uma entrada por loja processada),
    útil tanto para logging quanto para o endpoint manual de teste.
    """
    db = SessionLocal()
    resultados = []
    try:
        agora = datetime.now()
        lojas_ativas = db.query(Loja).filter(Loja.ativo.is_(True)).all()

        for loja in lojas_ativas:
            horario_zeragem_hoje = datetime.combine(agora.date(), loja.horario_zeragem)
            dentro_da_janela = (
                horario_zeragem_hoje
                <= agora
                <= horario_zeragem_hoje + timedelta(minutes=janela_tolerancia_minutos)
            )

            if not dentro_da_janela:
                continue

            if ja_zerou_hoje(db, loja.id, agora):
                continue

            produtos_processados = zerar_loja(db, loja, agora)
            logger.info(
                "Zeragem executada para loja '%s' (id=%s): %s produto(s) processado(s).",
                loja.nome,
                loja.id,
                produtos_processados,
            )
            resultados.append(
                {
                    "loja_id": loja.id,
                    "loja_nome": loja.nome,
                    "produtos_processados": produtos_processados,
                }
            )

        return resultados
    finally:
        db.close()
