"""
Sincronização de vendas e perdas com o PDV da rede (Fase 2 / P7) -- STUB.

A integração com o sistema de PDV ainda não está especificada (decisão D3
em aberto: cliente piloto e acesso aos dados). Enquanto isso, os dados
entram pela importação de CSV (importacao_service, origem `manual`). Este
módulo só fixa a INTERFACE que a integração real vai implementar, para que
o restante do sistema (e a Fase 3) já possa contar com ela.

Contrato da implementação futura:
- Busca no PDV as vendas e as perdas de UM negócio num dia e grava em
  `vendas_diarias`/`perdas_diarias` com origem `api`, substituindo o que já
  existir daquela origem (mesma regra da D5: INSERT ... ON CONFLICT DO
  UPDATE). As linhas `manual` do mesmo dia não são tocadas.
- Valida loja, produto e quantidade com as mesmas regras da importação
  (D6, D12, D13) e devolve o resultado (gravadas, erros).
- `negocio_id` é um parâmetro porque isto é um job interno, executado
  negócio por negócio. Nunca deve ser exposto como rota que receba o
  negócio do cliente (regra de ouro do CLAUDE.md).

Agendamento: NÃO está no agendador (app/core/scheduler.py). Registrar o job
só quando a integração existir; registrar o stub apenas encheria o log.
"""

import enum
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

MENSAGEM_NAO_CONFIGURADA = (
    "Integração com o PDV não configurada (decisão D3 em aberto). "
    "Use a importação de CSV (POST /vendas/importar e /perdas/importar)."
)


class SituacaoSync(str, enum.Enum):
    NAO_CONFIGURADA = "nao_configurada"
    CONCLUIDA = "concluida"  # reservado para a implementação real
    FALHOU = "falhou"  # reservado para a implementação real


@dataclass
class ResultadoSync:
    situacao: SituacaoSync
    mensagem: str
    negocio_id: int
    data: date
    vendas_gravadas: int = 0
    perdas_gravadas: int = 0


def sincronizar_vendas(db: Session, negocio_id: int, data: date) -> ResultadoSync:
    """
    Sincroniza com o PDV as vendas e perdas de um negócio num dia.

    STUB: não acessa o PDV nem grava nada; devolve "integração não
    configurada". `db` faz parte da interface para a implementação real.
    """
    return ResultadoSync(
        situacao=SituacaoSync.NAO_CONFIGURADA,
        mensagem=MENSAGEM_NAO_CONFIGURADA,
        negocio_id=negocio_id,
        data=data,
    )
