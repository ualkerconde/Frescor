"""
Agendador da rotina de zeragem diária, usando APScheduler.

APScheduler roda DENTRO do próprio processo da API (não exige
infraestrutura externa como Redis/RabbitMQ, ao contrário de Celery) — opção
adequada para o estágio atual do projeto, com poucas lojas e baixo volume.

Limitação a ter em mente para o futuro: como o agendamento vive na memória
do processo da API, se você rodar múltiplas instâncias da API ao mesmo
tempo (ex.: em produção, atrás de um load balancer com 2+ processos), cada
instância teria seu próprio agendador rodando em paralelo, o que poderia
disparar a verificação mais de uma vez ao mesmo tempo. Isso não chega a
duplicar a zeragem em si (a checagem "já zerou hoje" em
zeragem_service.py impede isso), mas é um desperdício de execução. Se/quando
o projeto crescer para múltiplas instâncias, migrar para Celery + Beat (ou
travar a execução com um lock externo) resolve isso de forma mais robusta.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.zeragem_service import executar_zeragem_lojas_pendentes

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler()


def _job_verificar_zeragem():
    try:
        executar_zeragem_lojas_pendentes()
    except Exception:
        # Captura qualquer erro inesperado para que uma falha em uma
        # execução não derrube o agendador inteiro (ele continuaria
        # tentando nas próximas execuções agendadas).
        logger.exception("Erro ao executar a verificação de zeragem de lojas.")


def iniciar_agendador():
    """Chamado uma única vez, na inicialização da aplicação (ver app/main.py)."""
    if scheduler.running:
        return
    # Verifica a cada 1 minuto se alguma loja atingiu seu horário de
    # zeragem. Esse intervalo é o que define a "janela de tolerância"
    # mínima necessária em executar_zeragem_lojas_pendentes.
    scheduler.add_job(_job_verificar_zeragem, "interval", minutes=1, id="verificar_zeragem")
    scheduler.start()
    logger.info("Agendador de zeragem iniciado (verificação a cada 1 minuto).")


def parar_agendador():
    """Chamado no encerramento da aplicação, para liberar recursos de forma limpa."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
