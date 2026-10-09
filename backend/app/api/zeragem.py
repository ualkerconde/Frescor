"""
Endpoint para disparo manual da rotina de zeragem.

Dois usos legítimos para isto existir:
1. Teste/desenvolvimento: forçar a zeragem sem esperar o horário configurado.
2. Operacional: um gerente de loja poder, em uma situação excepcional,
   forçar a zeragem da própria loja antes do horário automático.

Importante: este endpoint só zera a LOJA do usuário autenticado (extraída
do token) — nunca uma loja arbitrária informada pelo cliente, seguindo a
mesma regra de isolamento do restante da API.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import UsuarioAutenticado, obter_usuario_autenticado
from app.db.session import get_db
from app.models.loja import Loja
from app.schemas.zeragem import ExecutarZeragemResponse, ResultadoZeragemLoja
from app.services.zeragem_service import ja_zerou_hoje, zerar_loja

router = APIRouter()


@router.post("/zeragem/executar-agora", response_model=ExecutarZeragemResponse)
def executar_zeragem_manual(
    forcar: bool = False,
    db: Session = Depends(get_db),
    atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
):
    """
    Executa a zeragem imediatamente para a loja do usuário autenticado,
    sem esperar o horário agendado.

    Por padrão, respeita a mesma regra "não zerar duas vezes no mesmo
    dia" usada pelo agendador automático. Use `forcar=true` (query param)
    para ignorar essa checagem e zerar mesmo que já tenha zerado hoje —
    útil em testes, mas use com cautela em uso operacional real, já que
    isso descarta a contagem atual sem gerar um novo snapshot intermediário
    além do que já existe.
    """
    loja = db.get(Loja, atual.loja_id)
    if loja is None or not loja.ativo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loja não encontrada ou inativa.",
        )

    agora = datetime.now()

    if not forcar and ja_zerou_hoje(db, loja.id, agora):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Esta loja já foi zerada hoje. Use o parâmetro forcar=true "
                "para executar novamente mesmo assim."
            ),
        )

    produtos_processados = zerar_loja(db, loja, agora)

    return ExecutarZeragemResponse(
        lojas_processadas=1,
        detalhes=[
            ResultadoZeragemLoja(
                loja_id=loja.id,
                loja_nome=loja.nome,
                produtos_processados=produtos_processados,
            )
        ],
    )
