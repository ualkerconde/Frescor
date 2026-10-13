"""
Endpoints de autenticação do SaaS web (gestor de central): login e refresh.

Separados de propósito das rotas do app mobile (app/api/auth.py), que não
foram alteradas: o app continua usando /auth/login e /auth/refresh, e o
SaaS usa /auth/web/login e /auth/web/refresh (decisões D1 e D10 em
docs/STATUS.md).

Diferenças em relação às rotas do app:
- Exigem as regras do gestor de central (validar_gestor_central), as
  mesmas que a dependency obter_gestor_central aplica a cada requisição.
- Os tokens emitidos levam a claim "porta": "web". O app recusa esses
  tokens, e o SaaS recusa os tokens do app.

Logout não tem rota própria: como no app, os tokens são JWT sem estado no
servidor, e "sair" é o cliente apagar os tokens. Revogação de acesso vale
na próxima requisição ou renovação, porque as regras são conferidas no
banco a cada vez.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import carregar_usuario_do_token, validar_gestor_central
from app.core.security import (
    PORTA_WEB,
    criar_access_token,
    criar_refresh_token,
    verificar_senha,
)
from app.db.session import get_db
from app.models.usuario import Usuario
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login_web(dados: LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica um gestor de central por e-mail e senha.

    - 401: e-mail ou senha incorretos (sem revelar qual dos dois, como no app).
    - 403: credenciais corretas, mas sem permissão para o SaaS (bloqueado,
      sem tem_acesso_web, não é gestor de central, central inválida ou
      inativa), com a mesma mensagem que a dependency daria.
    """
    usuario = db.query(Usuario).filter(Usuario.email == dados.email).first()

    if usuario is None or not verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    validar_gestor_central(usuario, db)

    return TokenResponse(
        access_token=criar_access_token(usuario.id, usuario.negocio_id, porta=PORTA_WEB),
        refresh_token=criar_refresh_token(usuario.id, usuario.negocio_id, porta=PORTA_WEB),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_web(dados: RefreshRequest, db: Session = Depends(get_db)):
    """
    Troca um refresh token do SaaS por um novo access token.

    - 401: token inválido, expirado, que não é refresh, ou que não é do SaaS.
    - 403: o usuário perdeu a permissão depois do login (as regras são
      conferidas de novo no banco), com a mensagem do motivo.
    """
    usuario = carregar_usuario_do_token(dados.refresh_token, db, tipo="refresh", porta=PORTA_WEB)
    validar_gestor_central(usuario, db)

    return AccessTokenResponse(
        access_token=criar_access_token(usuario.id, usuario.negocio_id, porta=PORTA_WEB),
    )
