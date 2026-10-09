"""
Endpoints de autenticação: login, refresh e logout.

Conforme a especificação (seção 4.4): o login devolve um par de tokens
(access token de vida curta + refresh token de 30 dias). O access token
é usado em toda chamada à API; o refresh token serve só para obter um
novo access token sem pedir a senha de novo.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import (
    criar_access_token,
    criar_refresh_token,
    decodificar_token,
    verificar_senha,
)
from app.db.session import get_db
from app.models.usuario import StatusUsuario, Usuario
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(dados: LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica um usuário por e-mail e senha.

    Validações aplicadas, na ordem (ver especificação, seção 4.3):
    1. O usuário existe?
    2. A senha está correta?
    3. O usuário está ativo (não bloqueado)?
    4. O usuário tem permissão de acesso ao app (tem_acesso_app)?

    Cada falha gera uma mensagem específica, exceto usuário/senha — por
    segurança, não revelamos se o erro foi "e-mail não existe" ou "senha
    errada", para não ajudar tentativas de adivinhação de contas válidas.
    """
    usuario = db.query(Usuario).filter(Usuario.email == dados.email).first()

    if usuario is None or not verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    if usuario.status != StatusUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário bloqueado ou inativo. Fale com o administrador.",
        )

    if not usuario.tem_acesso_app:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não tem permissão para acessar o app. Fale com o administrador.",
        )

    access_token = criar_access_token(usuario_id=usuario.id, negocio_id=usuario.negocio_id)
    refresh_token = criar_refresh_token(usuario_id=usuario.id, negocio_id=usuario.negocio_id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(dados: RefreshRequest, db: Session = Depends(get_db)):
    """
    Troca um refresh token válido por um novo access token.

    Chamado automaticamente pelo app (em segundo plano, sem o usuário
    perceber) sempre que o access token atual expira, enquanto o refresh
    token de 30 dias continuar válido.
    """
    credenciais_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão expirada. Faça login novamente.",
    )

    try:
        payload = decodificar_token(dados.refresh_token)
    except JWTError:
        raise credenciais_invalidas

    if payload.get("tipo") != "refresh":
        raise credenciais_invalidas

    usuario_id_str = payload.get("sub")
    if usuario_id_str is None:
        raise credenciais_invalidas

    usuario = db.get(Usuario, int(usuario_id_str))

    if usuario is None or usuario.status != StatusUsuario.ATIVO or not usuario.tem_acesso_app:
        # Cobre o caso de revogação de acesso pelo admin depois que o
        # refresh token já tinha sido emitido: a próxima tentativa de
        # renovação já é bloqueada, mesmo com o token "fisicamente" válido.
        raise credenciais_invalidas

    novo_access_token = criar_access_token(usuario_id=usuario.id, negocio_id=usuario.negocio_id)

    return AccessTokenResponse(access_token=novo_access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    """
    Logout do usuário.

    Observação importante sobre a implementação atual: como os tokens são
    JWT "stateless" (a API não guarda uma lista de tokens emitidos), este
    endpoint não consegue invalidar um token já emitido no lado do
    servidor — ele serve como sinal para o app apagar os tokens salvos
    localmente no celular, o que já resolve o caso de uso comum (usuário
    aperta "Sair").

    Para revogação forçada (ex.: admin bloqueando um celular perdido), o
    mecanismo é outro: a verificação de status/tem_acesso_app feita em
    obter_usuario_autenticado e em /auth/refresh já bloqueia o uso, pois
    consulta o estado atual do usuário no banco a cada requisição.
    """
    return None
